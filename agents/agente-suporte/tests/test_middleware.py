"""Guards de fluxo com a POLÍTICA de chamados injetada (sem LLM).

Exercita os dois middlewares genéricos (`PreconditionMiddleware` e
`SequentialTurnMiddleware`) com o estado de domínio montado direto no dict de state.
A pré-condição recebe o ESTADO do agente.
"""

from __future__ import annotations

from contracts.middleware import PreconditionMiddleware, SequentialTurnMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent import _anuncia_proximo_passo
from app.tools import (
    SEQUENTIAL_TOOLS,
    WRITE_TOOLS,
    motivo_bloqueio_abertura,
    motivo_bloqueio_fechamento,
)


def _precond() -> PreconditionMiddleware:
    return PreconditionMiddleware(
        preconditions={
            "abrir_chamado": motivo_bloqueio_abertura,
            "fechar_chamado": motivo_bloqueio_fechamento,
        }
    )


def _seq() -> SequentialTurnMiddleware:
    return SequentialTurnMiddleware(
        write_tools=WRITE_TOOLS,
        sequential_tools=SEQUENTIAL_TOOLS,
        announce=_anuncia_proximo_passo,
    )


def _ai(tool_calls=None, content="") -> AIMessage:
    return AIMessage(content=content, tool_calls=tool_calls or [])


def _tc(name, args=None, id="x"):
    return {"name": name, "args": args or {}, "id": id}


def _chamado_com_detalhe(cid="c1") -> dict:
    """Um chamado aberto e com detalhe (pré-condição do fechamento satisfeita)."""
    return {
        cid: {
            "id": cid,
            "titulo": "Notebook",
            "categoria_id": "C1",
            "prioridade": "alta",
            "status": "aberto",
            "detalhes": ["reiniciei"],
        }
    }


def test_sem_tool_calls_nao_interfere():
    assert _precond().after_model({"messages": [_ai(content="oi")]}, None) is None


def test_abertura_sem_titulo_e_barrada():
    msgs = [HumanMessage(content="quero abrir um chamado"),
            _ai([_tc("abrir_chamado", {"titulo": "", "categoria_id": "C1", "prioridade": "alta"})])]
    out = _precond().after_model({"messages": msgs, "chamados": {}}, None)
    assert out["messages"][0].tool_calls == []  # abertura prematura barrada ANTES do card
    assert "título" in out["messages"][0].content


def test_abertura_com_categoria_invalida_e_barrada():
    msgs = [HumanMessage(content="abre"),
            _ai([_tc("abrir_chamado", {"titulo": "PC", "categoria_id": "ZZ", "prioridade": "alta"})])]
    out = _precond().after_model({"messages": msgs, "chamados": {}}, None)
    assert out["messages"][0].tool_calls == []
    assert "categoria" in out["messages"][0].content


def test_abertura_com_prioridade_invalida_e_barrada():
    msgs = [HumanMessage(content="abre"),
            _ai([_tc("abrir_chamado", {"titulo": "PC", "categoria_id": "C1", "prioridade": "urgente"})])]
    out = _precond().after_model({"messages": msgs, "chamados": {}}, None)
    assert out["messages"][0].tool_calls == []
    assert "prioridade" in out["messages"][0].content


def test_abertura_valida_passa():
    msgs = [HumanMessage(content="abre"),
            _ai([_tc("abrir_chamado", {"titulo": "Notebook", "categoria_id": "C1", "prioridade": "alta"})])]
    assert _precond().after_model({"messages": msgs, "chamados": {}}, None) is None


def test_fechamento_prematuro_e_barrado_com_motivo():
    msgs = [HumanMessage(content="fecha"), _ai([_tc("fechar_chamado", {"chamado_id": "nope"})])]
    out = _precond().after_model({"messages": msgs, "chamados": {}}, None)
    corrigida = out["messages"][0]
    assert corrigida.tool_calls == []  # ação removida -> não roda
    assert "Não existe um chamado" in corrigida.content


def test_abrir_e_detalhar_encadeiam_no_mesmo_turno():
    msgs = [
        HumanMessage(content="abre e detalha"),
        _ai([_tc("abrir_chamado", {"titulo": "X", "categoria_id": "C1", "prioridade": "alta"}, "a"),
             _tc("adicionar_detalhe", {"chamado_id": "c", "texto": "i"}, "b")]),
    ]
    assert _seq().after_model({"messages": msgs, "chamados": {}}, None) is None


def test_fechamento_segurado_para_turno_proprio_anuncia_proximo_passo():
    cid = "c1"
    msgs = [
        HumanMessage(content="detalha e fecha"),
        _ai([_tc("adicionar_detalhe", {"chamado_id": cid, "texto": "resolvido"}, "a")]),
        ToolMessage(content="Detalhe registrado.", name="adicionar_detalhe", tool_call_id="a"),
        _ai([_tc("fechar_chamado", {"chamado_id": cid}, "b")]),
    ]
    state = {"messages": msgs, "chamados": _chamado_com_detalhe(cid)}
    out = _seq().after_model(state, None)
    corrigida = out["messages"][0]
    assert corrigida.tool_calls == []  # fechamento segurado
    assert "próximo passo é: Fechar chamado" in corrigida.content
