"""Guards de fluxo com a POLÍTICA de despesas injetada (sem LLM).

Exercita os dois middlewares genéricos (`PreconditionMiddleware` e
`SequentialTurnMiddleware`) com o estado de domínio montado direto no dict de state.
A pré-condição recebe o ESTADO do agente (não mais um dict global).
"""

from __future__ import annotations

from contracts.middleware import PreconditionMiddleware, SequentialTurnMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent import _anuncia_proximo_passo
from app.tools import (
    SEQUENTIAL_TOOLS,
    WRITE_TOOLS,
    motivo_bloqueio_abertura,
    motivo_bloqueio_envio,
)


def _precond() -> PreconditionMiddleware:
    return PreconditionMiddleware(
        preconditions={
            "abrir_relatorio": motivo_bloqueio_abertura,
            "enviar_para_aprovacao": motivo_bloqueio_envio,
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


def _relatorio_com_item(rid="r1") -> dict:
    """Um relatório aberto e com item (pré-condição do envio satisfeita)."""
    return {
        rid: {
            "id": rid,
            "titulo": "Viagem",
            "tipo_id": "T1",
            "status": "aberto",
            "itens": [{"descricao": "Táxi", "valor": 45}],
        }
    }


def test_sem_tool_calls_nao_interfere():
    assert _precond().after_model({"messages": [_ai(content="oi")]}, None) is None


def test_abertura_sem_titulo_e_barrada():
    msgs = [HumanMessage(content="quero registrar uma despesa"),
            _ai([_tc("abrir_relatorio", {"titulo": "", "tipo_id": "T1"})])]
    out = _precond().after_model({"messages": msgs, "relatorios": {}}, None)
    corrigida = out["messages"][0]
    assert corrigida.tool_calls == []  # abertura prematura barrada ANTES do card
    assert "título" in corrigida.content


def test_abertura_com_tipo_invalido_e_barrada():
    msgs = [HumanMessage(content="abre"),
            _ai([_tc("abrir_relatorio", {"titulo": "Viagem", "tipo_id": "ZZ"})])]
    out = _precond().after_model({"messages": msgs, "relatorios": {}}, None)
    assert out["messages"][0].tool_calls == []
    assert "tipo" in out["messages"][0].content


def test_abertura_valida_passa():
    msgs = [HumanMessage(content="abre"),
            _ai([_tc("abrir_relatorio", {"titulo": "Viagem SP", "tipo_id": "T1"})])]
    # título presente + tipo válido -> pré-condição não interfere (segue p/ o card HITL)
    assert _precond().after_model({"messages": msgs, "relatorios": {}}, None) is None


def test_envio_prematuro_e_barrado_com_motivo():
    msgs = [HumanMessage(content="envia"), _ai([_tc("enviar_para_aprovacao", {"relatorio_id": "nope"})])]
    # estado sem relatórios -> pré-condição barra
    out = _precond().after_model({"messages": msgs, "relatorios": {}}, None)
    corrigida = out["messages"][0]
    assert corrigida.tool_calls == []  # ação removida -> não roda
    assert "Não existe um relatório" in corrigida.content


def test_abrir_e_adicionar_encadeiam_no_mesmo_turno():
    # nenhuma escrita anterior no turno -> nada é segurado (composição é permitida)
    msgs = [
        HumanMessage(content="abre e adiciona"),
        _ai([_tc("abrir_relatorio", {"titulo": "X", "tipo_id": "T1"}, "a"),
             _tc("adicionar_item", {"relatorio_id": "r", "descricao": "i", "valor": 1}, "b")]),
    ]
    assert _seq().after_model({"messages": msgs, "relatorios": {}}, None) is None


def test_envio_segurado_para_turno_proprio_anuncia_proximo_passo():
    rid = "r1"
    msgs = [
        HumanMessage(content="adiciona e envia"),
        _ai([_tc("adicionar_item", {"relatorio_id": rid, "descricao": "Café", "valor": 5}, "a")]),
        ToolMessage(content="Item adicionado.", name="adicionar_item", tool_call_id="a"),
        _ai([_tc("enviar_para_aprovacao", {"relatorio_id": rid}, "b")]),
    ]
    # houve write no turno -> envio é segurado para o próximo turno
    state = {"messages": msgs, "relatorios": _relatorio_com_item(rid)}
    out = _seq().after_model(state, None)
    corrigida = out["messages"][0]
    assert corrigida.tool_calls == []  # envio segurado
    assert "próximo passo é: Enviar para aprovação" in corrigida.content
