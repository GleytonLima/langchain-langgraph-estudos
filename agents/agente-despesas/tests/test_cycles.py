"""Ciclos de conversa ponta a ponta (chat -> resume -> history).

Usa o agente real (mesma fiação: HITL + guards de fluxo + tools) com a LLM
DUBLADA: cada AIMessage do roteiro define o que o modelo "decidiu" naquele passo.
Assim validamos a sequência completa de forma determinística — exatamente os ciclos
que antes eram testados na mão montando requests.
"""

from __future__ import annotations

import app.runtime as rt
from contracts import ChatStatus, ToolDecision
from langchain_core.messages import AIMessage, ToolMessage


def _tc(name, args=None, id="x"):
    return {"name": name, "args": args or {}, "id": id}


def _ai(tool_calls=None, content=""):
    return AIMessage(content=content, tool_calls=tool_calls or [])


def _relatorios(agent, thread_id="t1") -> dict:
    """Relatórios persistidos no ESTADO do grafo desta thread (não mais dict global)."""
    cfg = {"configurable": {"thread_id": thread_id}}
    return (agent.get_state(cfg).values or {}).get("relatorios", {})


def _only_report(agent, thread_id="t1"):
    """Único relatório criado na thread (id, dict)."""
    store = _relatorios(agent, thread_id)
    assert len(store) == 1, store
    return next(iter(store.items()))


# --------------------------------------------------------------------------- #
# Ciclo feliz: descobre tipo -> abre (HITL) -> aprova -> relatório criado com T1
# --------------------------------------------------------------------------- #


async def test_ciclo_abrir_relatorio_aprovado(use_agent):
    agent = use_agent([
        _ai([_tc("listar_tipos", id="l")]),
        _ai([_tc("abrir_relatorio", {"titulo": "Viagem SP", "tipo_id": "T1"}, "a")]),
        _ai(content="Pronto, relatório aberto."),
    ])

    r1 = await rt.run_chat("t1", "abrir um relatório de viagem chamado Viagem SP")
    assert r1.status == ChatStatus.interrupt
    [pend] = r1.tool_calls
    assert pend.tool_name == "abrir_relatorio"
    assert pend.tool_label == "Abrir relatório"
    # o de-para viaja junto p/ o seletor do card: nomes visíveis, ids gravados
    tipos = pend.field_options["tipo_id"]
    assert {"value": "T1", "label": "Viagem"} in [o.model_dump() for o in tipos]

    r2 = await rt.run_resume("t1", [ToolDecision(tool_call_id=pend.tool_call_id, action="approve")])
    assert r2.status == ChatStatus.final
    assert r2.text == "Pronto, relatório aberto."

    _, rel = _only_report(agent)
    assert rel["tipo_id"] == "T1" and rel["status"] == "aberto"

    # histórico: decisão HITL vira linha do usuário; resultado da tool fica fora do transcript
    linhas = [(m.role, m.text) for m in (await rt.run_history("t1")).messages]
    assert ("user", "aprovou Abrir relatório") in linhas
    assert not any(r == "assistant" and t.startswith("[") for r, t in linhas)


# --------------------------------------------------------------------------- #
# Editar o tipo no card antes de aprovar: grava o id editado (T2)
# --------------------------------------------------------------------------- #


async def test_ciclo_editar_tipo_no_card(use_agent):
    agent = use_agent([
        _ai([_tc("abrir_relatorio", {"titulo": "Viagem SP", "tipo_id": "T1"}, "a")]),
        _ai(content="Aberto com o tipo escolhido."),
    ])

    r1 = await rt.run_chat("t1", "abrir relatório")
    [pend] = r1.tool_calls
    await rt.run_resume(
        "t1",
        [ToolDecision(
            tool_call_id=pend.tool_call_id,
            action="approve",
            edited_args={"titulo": "Viagem SP", "tipo_id": "T2"},
        )],
    )
    _, rel = _only_report(agent)
    assert rel["tipo_id"] == "T2"  # gravou o id editado no card


# --------------------------------------------------------------------------- #
# Rejeitar: nada é criado
# --------------------------------------------------------------------------- #


async def test_ciclo_rejeitar_nao_cria_relatorio(use_agent):
    agent = use_agent([
        _ai([_tc("abrir_relatorio", {"titulo": "X", "tipo_id": "T1"}, "a")]),
        _ai(content="Ok, cancelado."),
    ])
    r1 = await rt.run_chat("t1", "abrir relatório")
    [pend] = r1.tool_calls
    await rt.run_resume("t1", [ToolDecision(tool_call_id=pend.tool_call_id, action="reject")])
    assert _relatorios(agent) == {}


# --------------------------------------------------------------------------- #
# Guard sequencial: após uma escrita no turno, o envio é segurado e o agente
# anuncia o próximo passo (em vez de enviar no mesmo turno).
# --------------------------------------------------------------------------- #


async def test_ciclo_envio_segurado_anuncia_proximo_passo(use_agent, monkeypatch):
    # id de relatório determinístico p/ referenciar no roteiro
    class _U:
        hex = "fixedid0" + "00000000"

    import app.tools as tools_mod

    monkeypatch.setattr(tools_mod.uuid, "uuid4", lambda: _U())
    rid = "fixedid0"

    agent = use_agent([
        _ai([_tc("abrir_relatorio", {"titulo": "Viagem", "tipo_id": "T1"}, "a")]),
        _ai(content="Relatório aberto."),
        _ai([_tc("adicionar_item", {"relatorio_id": rid, "descricao": "Táxi", "valor": 45}, "b")]),
        _ai(content="Item adicionado."),
        _ai([_tc("adicionar_item", {"relatorio_id": rid, "descricao": "Café", "valor": 5}, "c")]),
        _ai([_tc("enviar_para_aprovacao", {"relatorio_id": rid}, "d")]),  # será segurado
    ])

    # turno 1: abrir + aprovar
    p1 = (await rt.run_chat("t1", "abrir relatório de viagem")).tool_calls[0]
    await rt.run_resume("t1", [ToolDecision(tool_call_id=p1.tool_call_id, action="approve")])
    # turno 2: adicionar item + aprovar
    p2 = (await rt.run_chat("t1", "adicionar um táxi de 45")).tool_calls[0]
    await rt.run_resume("t1", [ToolDecision(tool_call_id=p2.tool_call_id, action="approve")])
    # turno 3: adicionar outro item e pedir envio no mesmo turno
    p3 = (await rt.run_chat("t1", "adiciona um café de 5 e já envia")).tool_calls[0]
    assert p3.tool_name == "adicionar_item"
    final = await rt.run_resume("t1", [ToolDecision(tool_call_id=p3.tool_call_id, action="approve")])

    assert final.status == ChatStatus.final
    assert "próximo passo é: Enviar para aprovação" in final.text
    _, rel = _only_report(agent)
    assert rel["status"] == "aberto"  # envio NÃO rodou
    assert len(rel["itens"]) == 2


# --------------------------------------------------------------------------- #
# ToolCallLimitMiddleware: modelo fraco em loop repetindo a MESMA tool é cortado
# no turno — a execução para em vez de rodar para sempre / estourar a recursão.
# --------------------------------------------------------------------------- #


async def test_tool_call_limit_corta_loop_de_modelo_fraco(use_agent):
    from app.agent import TOOL_CALL_RUN_LIMIT as limite

    # roteiro: a tool de leitura repetida MUITO além do necessário, e só então um texto
    agent = use_agent(
        [_ai([_tc("listar_tipos", id="l")]) for _ in range(limite + 2)]
        + [_ai(content="Pronto, listei os tipos.")]
    )

    r = await rt.run_chat("t1", "lista os tipos")  # não trava nem levanta exceção
    assert r.status == ChatStatus.final

    msgs = (agent.get_state({"configurable": {"thread_id": "t1"}}).values or {})["messages"]
    tms = [m for m in msgs if isinstance(m, ToolMessage) and m.name == "listar_tipos"]
    ok = [m for m in tms if m.status == "success"]
    barradas = [m for m in tms if m.status == "error"]
    assert len(ok) == limite  # executou no máximo o limite do turno
    assert len(barradas) >= 1  # as excedentes foram barradas deterministicamente
    assert "limit" in barradas[0].content.lower()
