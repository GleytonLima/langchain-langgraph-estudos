"""Execução síncrona do agente (request/response, sem streaming).

Roda o grafo com invoke; quando ele para, inspeciona o estado. Se o HITL
interrompeu antes de uma tool, retorna status=interrupt com as tool calls
pendentes. Caso contrário, retorna status=final com o texto do assistant.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from contracts import (
    ChatResponse,
    ChatStatus,
    FieldOption,
    HistoryMessage,
    HistoryResponse,
    PendingToolCall,
    ToolDecision,
)
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from .agent import get_agent, setup_checkpointer
from .presentation import present
from .settings import settings
from .tools import FIELD_LABELS, FIELD_OPTIONS, FIELD_READONLY, HITL_TOOLS, TOOL_LABELS


def _field_options(tool_name: str) -> dict[str, list[FieldOption]]:
    """Opções de seletor (de-para) dos args-referência desta tool, se houver."""
    providers = FIELD_OPTIONS.get(tool_name, {})
    return {arg: [FieldOption(**o) for o in provider()] for arg, provider in providers.items()}


@lru_cache
def _callbacks() -> list:
    """Handler do Langfuse (SDK v4). As credenciais vão por env (LANGFUSE_*);
    o get_client() valida a conexão. Falha barulhenta: se as chaves existem mas
    o handler não sobe, logamos — antes isso ficava mascarado e os traces sumiam.
    """
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return []
    # o SDK v4 lê as credenciais do ambiente; garantimos que estão lá
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
    os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
    os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)
    try:
        from langfuse import get_client
        from langfuse.langchain import CallbackHandler

        if not get_client().auth_check():
            logging.warning("Langfuse: auth_check falhou (chaves/host?). Traces desativados.")
            return []
        return [CallbackHandler()]
    except Exception:
        logging.exception("Langfuse: falha ao iniciar o CallbackHandler. Traces desativados.")
        return []


def _config(thread_id: str) -> dict:
    # metadata.langfuse_session_id agrupa os traces da mesma conversa na aba
    # Sessions do Langfuse. Usamos o thread_id (1 thread = 1 conversa = 1 sessão).
    return {
        "configurable": {"thread_id": thread_id},
        "callbacks": _callbacks(),
        "metadata": {"langfuse_session_id": thread_id},
    }


async def _pending_tool_calls(agent, config) -> list[PendingToolCall]:
    """Tool calls à espera de aprovação (última AIMessage do estado)."""
    state = await agent.aget_state(config)
    messages = state.values.get("messages", []) if state.values else []
    if not messages:
        return []
    last = messages[-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return [
            PendingToolCall(
                tool_call_id=tc["id"],
                tool_name=tc["name"],
                tool_label=TOOL_LABELS.get(tc["name"], tc["name"]),
                args=tc.get("args", {}),
                field_options=_field_options(tc["name"]),
                field_labels=FIELD_LABELS.get(tc["name"], {}),
                readonly_fields=FIELD_READONLY.get(tc["name"], []),
            )
            for tc in last.tool_calls
        ]
    return []


async def _last_text(agent, config) -> str:
    state = await agent.aget_state(config)
    messages = state.values.get("messages", []) if state.values else []
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return str(msg.content)
    return ""


def _build_history(messages) -> list[HistoryMessage]:
    """Converte mensagens do checkpointer no transcript exibido na UI.

    Resultados de tools (ToolMessage) não entram como falas do assistant — são
    log técnico; o modelo já resume em linguagem natural. Decisões HITL viram
    linhas do usuário (aprovou/rejeitou) para as pills no front.

    Modelos (sobretudo via tool-calling) às vezes repetem a MESMA fala em dois
    passos do loop no mesmo turno; colapsamos assistant consecutivos idênticos
    para não exibir a frase duplicada na tela.
    """
    history: list[HistoryMessage] = []
    for m in messages:
        if isinstance(m, HumanMessage):
            history.append(HistoryMessage(role="user", text=str(m.content)))
        elif isinstance(m, AIMessage) and m.content:
            texto = str(m.content)
            repetida = (
                history and history[-1].role == "assistant" and history[-1].text == texto
            )
            if not repetida:
                history.append(HistoryMessage(role="assistant", text=texto))
        elif isinstance(m, ToolMessage):
            nome = getattr(m, "name", None) or "tool"
            label = TOOL_LABELS.get(nome, nome)
            rejeitou = getattr(m, "status", None) == "error"
            if nome in HITL_TOOLS:
                verbo = "rejeitou" if rejeitou else "aprovou"
                history.append(HistoryMessage(role="user", text=f"{verbo} {label}"))
    return history


async def _result(agent, config) -> ChatResponse:
    state = await agent.aget_state(config)
    values = state.values or {}
    messages = values.get("messages", [])
    history = _build_history(messages)
    pending = await _pending_tool_calls(agent, config) if state.next else []
    suggestions, session = present(values.get("relatorios", {}), pending)
    if state.next:
        return ChatResponse(
            status=ChatStatus.interrupt,
            tool_calls=pending,
            messages=history,
            suggestions=suggestions,
            session=session,
        )
    return ChatResponse(
        status=ChatStatus.final,
        text=await _last_text(agent, config),
        messages=history,
        suggestions=suggestions,
        session=session,
    )


async def warmup() -> None:
    """Paga os custos de inicialização no boot, não na 1ª mensagem do usuário.

    Sem isto, o primeiro /chat dispara, de forma preguiçosa: build do agente,
    abertura do pool Postgres + setup das tabelas, e o auth_check do Langfuse.
    Por isso 'criar conversa é rápido, mas o primeiro oi demora'. Chamar aqui no
    startup move esse custo para fora do caminho do usuário.
    """
    get_agent()
    await setup_checkpointer()
    _callbacks()


async def run_chat(thread_id: str, user_input: str) -> ChatResponse:
    agent = get_agent()
    config = _config(thread_id)
    await agent.ainvoke({"messages": [{"role": "user", "content": user_input}]}, config)
    return await _result(agent, config)


async def _to_resume_payload(agent, config, decisions: list[ToolDecision]) -> dict:
    """Converte as decisões do usuário no formato do HumanInTheLoopMiddleware.

    O middleware espera `{"decisions": [Decision, ...]}`, uma Decision por tool
    call pendente e na mesma ordem. Tipos: "approve" | "reject" | "edit".
    """
    by_id = {d.tool_call_id: d for d in decisions}
    items: list[dict] = []
    for tc in await _pending_tool_calls(agent, config):
        d = by_id.get(tc.tool_call_id)
        if d is None or d.action == "reject":
            items.append({"type": "reject", "message": "Ação rejeitada pelo usuário."})
        elif d.edited_args is not None:
            items.append({"type": "edit", "edited_action": {"name": tc.tool_name, "args": d.edited_args}})
        else:
            items.append({"type": "approve"})
    return {"decisions": items}


async def run_resume(thread_id: str, decisions: list[ToolDecision]) -> ChatResponse:
    agent = get_agent()
    config = _config(thread_id)
    payload = await _to_resume_payload(agent, config, decisions)
    await agent.ainvoke(Command(resume=payload), config)
    return await _result(agent, config)


async def run_history(thread_id: str) -> HistoryResponse:
    """Transcript da thread (mensagens user/assistant) + HITL pendente, se houver."""
    agent = get_agent()
    config = _config(thread_id)
    state = await agent.aget_state(config)
    values = state.values or {}
    messages = values.get("messages", [])
    pending = await _pending_tool_calls(agent, config) if state.next else []
    suggestions, session = present(values.get("relatorios", {}), pending)
    return HistoryResponse(
        messages=_build_history(messages),
        pending=pending,
        suggestions=suggestions,
        session=session,
    )
