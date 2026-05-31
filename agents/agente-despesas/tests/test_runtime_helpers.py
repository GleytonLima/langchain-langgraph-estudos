"""Helpers do runtime: mapeamento de decisões HITL e reconstrução do histórico.

Não precisam de LLM nem grafo — recebem/usam um agente stub cujo get_state devolve
mensagens canônicas. Cobrem a tradução approve/edit/reject -> payload do middleware
e a reconstrução das decisões a partir dos ToolMessages no reopen.
"""

from __future__ import annotations

import app.runtime as rt
from contracts import ToolDecision
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


class _State:
    def __init__(self, messages, nxt=()):
        self.values = {"messages": messages}
        self.next = nxt


class _FakeAgent:
    def __init__(self, state):
        self._state = state

    async def aget_state(self, config):
        return self._state


_CFG = {"configurable": {"thread_id": "t1"}}


async def test_to_resume_payload_approve_edit_reject_em_ordem():
    pend = AIMessage(
        content="",
        tool_calls=[
            {"name": "abrir_relatorio", "args": {"titulo": "X", "tipo_id": "T1"}, "id": "a"},
            {"name": "adicionar_item", "args": {"valor": 1}, "id": "b"},
            {"name": "enviar_para_aprovacao", "args": {}, "id": "c"},
        ],
    )
    agent = _FakeAgent(_State([HumanMessage(content="oi"), pend]))
    decisions = [
        ToolDecision(tool_call_id="a", action="approve"),
        ToolDecision(tool_call_id="b", action="approve", edited_args={"valor": 99}),
        ToolDecision(tool_call_id="c", action="reject"),
    ]
    payload = await rt._to_resume_payload(agent, _CFG, decisions)
    assert payload["decisions"] == [
        {"type": "approve"},
        {"type": "edit", "edited_action": {"name": "adicionar_item", "args": {"valor": 99}}},
        {"type": "reject", "message": "Ação rejeitada pelo usuário."},
    ]


async def test_to_resume_payload_decisao_ausente_vira_reject():
    pend = AIMessage(content="", tool_calls=[{"name": "abrir_relatorio", "args": {}, "id": "a"}])
    agent = _FakeAgent(_State([pend]))
    payload = await rt._to_resume_payload(agent, _CFG, decisions=[])
    assert payload["decisions"] == [{"type": "reject", "message": "Ação rejeitada pelo usuário."}]


async def test_run_history_reconstrui_decisoes_e_pula_rejeicoes(monkeypatch):
    messages = [
        HumanMessage(content="abrir relatório de viagem"),
        AIMessage(content="Vou abrir o relatório."),
        AIMessage(content="", tool_calls=[{"name": "abrir_relatorio", "args": {}, "id": "a"}]),  # sem texto -> ignorada
        ToolMessage(content="Relatório criado.", name="abrir_relatorio", tool_call_id="a"),
        ToolMessage(content="Rejeitado.", name="enviar_para_aprovacao", tool_call_id="b", status="error"),
    ]
    monkeypatch.setattr(rt, "get_agent", lambda: _FakeAgent(_State(messages, nxt=())))
    hist = await rt.run_history("t1")
    linhas = [(m.role, m.text) for m in hist.messages]
    assert linhas == [
        ("user", "abrir relatório de viagem"),
        ("assistant", "Vou abrir o relatório."),
        ("user", "aprovou Abrir relatório"),
        ("user", "rejeitou Enviar para aprovação"),
    ]
    assert hist.pending == []


def test_build_history_colapsa_assistant_consecutivos_iguais():
    # modelo fraco às vezes repete a MESMA fala em dois passos do mesmo turno
    repetida = "Por favor, me informe a descrição do item."
    messages = [
        HumanMessage(content="quero adicionar um item"),
        AIMessage(content=repetida),
        AIMessage(content=repetida),  # duplicata -> deve ser colapsada
    ]
    linhas = [(m.role, m.text) for m in rt._build_history(messages)]
    assert linhas == [
        ("user", "quero adicionar um item"),
        ("assistant", repetida),
    ]


def test_build_history_nao_colapsa_assistant_iguais_nao_consecutivos():
    # mesma frase em turnos diferentes (com algo no meio) deve aparecer 2x
    repetida = "Algo deu errado, pode repetir?"
    messages = [
        AIMessage(content=repetida),
        HumanMessage(content="repetindo"),
        AIMessage(content=repetida),
    ]
    linhas = [(m.role, m.text) for m in rt._build_history(messages)]
    assert linhas == [
        ("assistant", repetida),
        ("user", "repetindo"),
        ("assistant", repetida),
    ]
