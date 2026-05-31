"""Middlewares de controle de fluxo genéricos (sem nenhum domínio).

Dois middlewares, uma responsabilidade cada:
- PreconditionMiddleware: barra tool por pré-condição (estado).
- SequentialTurnMiddleware: segura ação que exige turno próprio após uma escrita.
Aqui usamos tools fictícias e políticas mínimas para fixar o COMPORTAMENTO GENÉRICO.
"""

from __future__ import annotations

from contracts.middleware import PreconditionMiddleware, SequentialTurnMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def _ai(tool_calls=None, content="", id="ai1"):
    return AIMessage(id=id, content=content, tool_calls=tool_calls or [])


def _tc(name, args=None, id="x"):
    return {"name": name, "args": args or {}, "id": id}


# --------------------------------------------------------------------------- #
# PreconditionMiddleware
# --------------------------------------------------------------------------- #


def test_precond_sem_mensagens_nao_interfere():
    assert PreconditionMiddleware().after_model({"messages": []}, None) is None


def test_precond_ultima_nao_ai_nao_interfere():
    state = {"messages": [HumanMessage(content="oi")]}
    assert PreconditionMiddleware().after_model(state, None) is None


def test_precond_ai_sem_tool_calls_nao_interfere():
    state = {"messages": [_ai(content="resposta")]}
    assert PreconditionMiddleware().after_model(state, None) is None


def test_precond_tool_sem_politica_passa_livre():
    state = {"messages": [HumanMessage(content="x"), _ai([_tc("qualquer")])]}
    assert PreconditionMiddleware().after_model(state, None) is None


def test_precond_barra_e_remove_tool_com_motivo():
    guard = PreconditionMiddleware(preconditions={"perigosa": lambda state, args: "não pode agora"})
    state = {"messages": [HumanMessage(content="x"), _ai([_tc("perigosa")])]}
    out = guard.after_model(state, None)
    corrigida = out["messages"][0]
    assert corrigida.tool_calls == []
    assert "não pode agora" in corrigida.content
    assert corrigida.id == "ai1"  # mesmo id -> reducer substitui a AIMessage


def test_precond_satisfeita_mantem_tool():
    guard = PreconditionMiddleware(preconditions={"ok": lambda state, args: None})
    state = {"messages": [HumanMessage(content="x"), _ai([_tc("ok")])]}
    assert guard.after_model(state, None) is None


def test_precond_mistura_aviso_e_acao_mantida():
    """Uma tool barrada por pré-condição + uma tool ok: mantém só a ok."""
    guard = PreconditionMiddleware(preconditions={"bloqueada": lambda s, a: "motivo"})
    state = {
        "messages": [
            HumanMessage(content="x"),
            _ai([_tc("bloqueada", id="a"), _tc("livre", id="b")]),
        ]
    }
    out = guard.after_model(state, None)
    corrigida = out["messages"][0]
    assert [tc["name"] for tc in corrigida.tool_calls] == ["livre"]
    assert "motivo" in corrigida.content


# --------------------------------------------------------------------------- #
# SequentialTurnMiddleware
# --------------------------------------------------------------------------- #


def test_seq_sem_write_anterior_passa():
    guard = SequentialTurnMiddleware(write_tools=["w"], sequential_tools=["w"])
    state = {"messages": [HumanMessage(content="x"), _ai([_tc("w")])]}
    assert guard.after_model(state, None) is None


def test_seq_apos_write_e_segurada_e_anuncia():
    guard = SequentialTurnMiddleware(
        write_tools=["escrever", "enviar"],
        sequential_tools=["enviar"],
        announce=lambda seguradas: "próximo: " + ", ".join(seguradas),
    )
    state = {
        "messages": [
            HumanMessage(content="faz tudo"),
            _ai([_tc("escrever", id="a")]),
            ToolMessage(content="ok", name="escrever", tool_call_id="a"),
            _ai([_tc("enviar", id="b")]),
        ]
    }
    out = guard.after_model(state, None)
    corrigida = out["messages"][0]
    assert corrigida.tool_calls == []
    assert "próximo: enviar" in corrigida.content


def test_seq_announce_default_neutro_quando_nao_injetado():
    guard = SequentialTurnMiddleware(write_tools=["w"], sequential_tools=["s"])
    state = {
        "messages": [
            HumanMessage(content="x"),
            _ai([_tc("w", id="a")]),
            ToolMessage(content="ok", name="w", tool_call_id="a"),
            _ai([_tc("s", id="b")]),
        ]
    }
    out = guard.after_model(state, None)
    assert "próximo passo" in out["messages"][0].content.lower()


def test_seq_houve_write_para_na_human_message():
    """Write de um TURNO ANTERIOR (antes da última HumanMessage) não conta."""
    guard = SequentialTurnMiddleware(write_tools=["w"], sequential_tools=["s"])
    state = {
        "messages": [
            HumanMessage(content="turno antigo"),
            ToolMessage(content="ok", name="w", tool_call_id="a"),
            HumanMessage(content="turno novo"),
            _ai([_tc("s", id="b")]),
        ]
    }
    assert guard.after_model(state, None) is None


def test_seq_write_no_turno_mas_sem_sequential_passa():
    """Houve escrita, mas a tool atual não é sequential -> não segura."""
    guard = SequentialTurnMiddleware(write_tools=["w"], sequential_tools=["s"])
    state = {
        "messages": [
            HumanMessage(content="x"),
            _ai([_tc("w", id="a")]),
            ToolMessage(content="ok", name="w", tool_call_id="a"),
            _ai([_tc("outra", id="b")]),
        ]
    }
    assert guard.after_model(state, None) is None
