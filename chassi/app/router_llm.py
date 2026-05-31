"""Roteador: dada a pergunta do usuário, decide QUAIS agentes conseguem responder.

Não há roteamento automático entre agentes — isto é só uma sugestão para o usuário
escolher. Saída estruturada (Pydantic RouteDecision) força a LLM a citar apenas
ids que existem no registry (anti-alucinação). Quem decide é sempre o usuário.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from contracts import AgentMatch, RouteDecision
from langchain_openai import ChatOpenAI

from .registry import list_entries
from .settings import settings


def _llm() -> ChatOpenAI:
    return ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        temperature=0,
    )


@lru_cache
def _callbacks() -> list:
    """Handler do Langfuse (SDK v4) para tracear o roteador — mesmo padrão do
    agente. Sem chaves, roda sem traces. Falha barulhenta: se as chaves existem
    mas o handler não sobe, logamos em vez de mascarar.
    """
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return []
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


def _catalog(entries) -> str:
    linhas = []
    for e in entries:
        if not e.manifest:
            continue
        caps = "; ".join(e.manifest.capabilities)
        linhas.append(f"- id={e.id} | {e.manifest.name}: {e.manifest.description} | faz: {caps}")
    return "\n".join(linhas)


async def route(question: str) -> RouteDecision:
    entries = await list_entries()
    valid_ids = {e.id for e in entries if e.manifest}
    if not valid_ids:
        return RouteDecision(agents=[])

    catalog = _catalog(entries)
    structured = _llm().with_structured_output(RouteDecision)
    prompt = (
        "Você é o roteador de um call center de agentes. Dada a pergunta do "
        "usuário, indique quais agentes do catálogo conseguem respondê-la, com um "
        "score de 0 a 1 e o motivo. Use SOMENTE os ids do catálogo. Se nenhum "
        "servir, retorne lista vazia.\n\n"
        f"Catálogo:\n{catalog}\n\nPergunta do usuário: {question}"
    )
    try:
        decision = await structured.ainvoke(prompt, config={"callbacks": _callbacks()})
    except Exception:
        return RouteDecision(agents=[])

    # blindagem anti-alucinação: descarta ids que não existem no registry
    decision.agents = [
        AgentMatch(agent_id=a.agent_id, score=a.score, motivo=a.motivo)
        for a in decision.agents
        if a.agent_id in valid_ids
    ]
    decision.agents.sort(key=lambda a: a.score, reverse=True)
    return decision
