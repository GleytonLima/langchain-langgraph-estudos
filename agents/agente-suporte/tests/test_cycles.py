"""Ciclos de conversa ponta a ponta (chat -> resume -> history).

Usa o agente real (mesma fiação: HITL + guards de fluxo + tools) com a LLM
DUBLADA: cada AIMessage do roteiro define o que o modelo "decidiu" naquele passo.
Assim validamos a sequência completa de forma determinística.
"""

from __future__ import annotations

import app.runtime as rt
from contracts import ChatStatus, ToolDecision
from langchain_core.messages import AIMessage, ToolMessage


def _tc(name, args=None, id="x"):
    return {"name": name, "args": args or {}, "id": id}


def _ai(tool_calls=None, content=""):
    return AIMessage(content=content, tool_calls=tool_calls or [])


def _chamados(agent, thread_id="t1") -> dict:
    """Chamados persistidos no ESTADO do grafo desta thread."""
    cfg = {"configurable": {"thread_id": thread_id}}
    return (agent.get_state(cfg).values or {}).get("chamados", {})


def _only_chamado(agent, thread_id="t1"):
    """Único chamado criado na thread (id, dict)."""
    store = _chamados(agent, thread_id)
    assert len(store) == 1, store
    return next(iter(store.items()))


# --------------------------------------------------------------------------- #
# Ciclo feliz: lista categorias -> abre (HITL) -> aprova -> chamado criado
# --------------------------------------------------------------------------- #


async def test_ciclo_abrir_chamado_aprovado(use_agent):
    agent = use_agent([
        _ai([_tc("listar_categorias", id="l")]),
        _ai([_tc("abrir_chamado", {"titulo": "Notebook não liga", "categoria_id": "C1", "prioridade": "alta"}, "a")]),
        _ai(content="Pronto, chamado aberto."),
    ])

    r1 = await rt.run_chat("t1", "abrir um chamado: meu notebook não liga")
    assert r1.status == ChatStatus.interrupt
    [pend] = r1.tool_calls
    assert pend.tool_name == "abrir_chamado"
    assert pend.tool_label == "Abrir chamado"
    # DOIS seletores viajam juntos p/ o card: categoria (entidade) + prioridade (enum)
    cats = [o.model_dump() for o in pend.field_options["categoria_id"]]
    prios = [o.model_dump() for o in pend.field_options["prioridade"]]
    assert {"value": "C1", "label": "Hardware"} in cats
    assert {"value": "media", "label": "Média"} in prios

    r2 = await rt.run_resume("t1", [ToolDecision(tool_call_id=pend.tool_call_id, action="approve")])
    assert r2.status == ChatStatus.final
    assert r2.text == "Pronto, chamado aberto."

    _, ch = _only_chamado(agent)
    assert ch["categoria_id"] == "C1" and ch["prioridade"] == "alta" and ch["status"] == "aberto"

    linhas = [(m.role, m.text) for m in (await rt.run_history("t1")).messages]
    assert ("user", "aprovou Abrir chamado") in linhas


# --------------------------------------------------------------------------- #
# Editar categoria E prioridade no card antes de aprovar: grava os valores editados
# --------------------------------------------------------------------------- #


async def test_ciclo_editar_categoria_e_prioridade_no_card(use_agent):
    agent = use_agent([
        _ai([_tc("abrir_chamado", {"titulo": "X", "categoria_id": "C1", "prioridade": "alta"}, "a")]),
        _ai(content="Aberto com os valores escolhidos."),
    ])

    r1 = await rt.run_chat("t1", "abrir chamado")
    [pend] = r1.tool_calls
    await rt.run_resume(
        "t1",
        [ToolDecision(
            tool_call_id=pend.tool_call_id,
            action="approve",
            edited_args={"titulo": "X", "categoria_id": "C3", "prioridade": "baixa"},
        )],
    )
    _, ch = _only_chamado(agent)
    assert ch["categoria_id"] == "C3"  # gravou o id editado no card
    assert ch["prioridade"] == "baixa"  # gravou o enum editado no card


# --------------------------------------------------------------------------- #
# Rejeitar: nada é criado
# --------------------------------------------------------------------------- #


async def test_ciclo_rejeitar_nao_cria_chamado(use_agent):
    agent = use_agent([
        _ai([_tc("abrir_chamado", {"titulo": "X", "categoria_id": "C1", "prioridade": "alta"}, "a")]),
        _ai(content="Ok, cancelado."),
    ])
    r1 = await rt.run_chat("t1", "abrir chamado")
    [pend] = r1.tool_calls
    await rt.run_resume("t1", [ToolDecision(tool_call_id=pend.tool_call_id, action="reject")])
    assert _chamados(agent) == {}


# --------------------------------------------------------------------------- #
# Guard sequencial: após uma escrita no turno, o fechamento é segurado e o agente
# anuncia o próximo passo (em vez de fechar no mesmo turno).
# --------------------------------------------------------------------------- #


async def test_ciclo_fechamento_segurado_anuncia_proximo_passo(use_agent, monkeypatch):
    class _U:
        hex = "fixedid0" + "00000000"

    import app.tools as tools_mod

    monkeypatch.setattr(tools_mod.uuid, "uuid4", lambda: _U())
    cid = "fixedid0"

    agent = use_agent([
        _ai([_tc("abrir_chamado", {"titulo": "Notebook", "categoria_id": "C1", "prioridade": "alta"}, "a")]),
        _ai(content="Chamado aberto."),
        _ai([_tc("adicionar_detalhe", {"chamado_id": cid, "texto": "reiniciei"}, "b")]),
        _ai(content="Detalhe registrado."),
        _ai([_tc("adicionar_detalhe", {"chamado_id": cid, "texto": "resolvido"}, "c")]),
        _ai([_tc("fechar_chamado", {"chamado_id": cid}, "d")]),  # será segurado
    ])

    # turno 1: abrir + aprovar
    p1 = (await rt.run_chat("t1", "abrir chamado de hardware")).tool_calls[0]
    await rt.run_resume("t1", [ToolDecision(tool_call_id=p1.tool_call_id, action="approve")])
    # turno 2: detalhar + aprovar
    p2 = (await rt.run_chat("t1", "detalhe: reiniciei")).tool_calls[0]
    await rt.run_resume("t1", [ToolDecision(tool_call_id=p2.tool_call_id, action="approve")])
    # turno 3: detalhar de novo e pedir fechamento no mesmo turno
    p3 = (await rt.run_chat("t1", "detalhe: resolvido e já fecha")).tool_calls[0]
    assert p3.tool_name == "adicionar_detalhe"
    final = await rt.run_resume("t1", [ToolDecision(tool_call_id=p3.tool_call_id, action="approve")])

    assert final.status == ChatStatus.final
    assert "próximo passo é: Fechar chamado" in final.text
    _, ch = _only_chamado(agent)
    assert ch["status"] == "aberto"  # fechamento NÃO rodou
    assert len(ch["detalhes"]) == 2


# --------------------------------------------------------------------------- #
# ToolCallLimitMiddleware: modelo fraco em loop repetindo a MESMA tool é cortado
# no turno — a execução para em vez de rodar para sempre / estourar a recursão.
# --------------------------------------------------------------------------- #


async def test_tool_call_limit_corta_loop_de_modelo_fraco(use_agent):
    from app.agent import TOOL_CALL_RUN_LIMIT as limite

    # roteiro: a tool de leitura repetida MUITO além do necessário, e só então um texto
    agent = use_agent(
        [_ai([_tc("listar_categorias", id="l")]) for _ in range(limite + 2)]
        + [_ai(content="Pronto, listei as categorias.")]
    )

    r = await rt.run_chat("t1", "lista as categorias")  # não trava nem levanta exceção
    assert r.status == ChatStatus.final

    msgs = (agent.get_state({"configurable": {"thread_id": "t1"}}).values or {})["messages"]
    tms = [m for m in msgs if isinstance(m, ToolMessage) and m.name == "listar_categorias"]
    ok = [m for m in tms if m.status == "success"]
    barradas = [m for m in tms if m.status == "error"]
    assert len(ok) == limite  # executou no máximo o limite do turno
    assert len(barradas) >= 1  # as excedentes foram barradas deterministicamente
    assert "limit" in barradas[0].content.lower()
