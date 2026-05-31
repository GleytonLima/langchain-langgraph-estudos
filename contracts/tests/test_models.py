"""Modelos do protocolo compartilhado: defaults, validação e (de)serialização.

São o contrato único entre chassi e agentes — um default que muda em silêncio
quebraria os dois lados. Estes testes fixam os defaults e as regras de validação.
"""

from __future__ import annotations

import pytest
from contracts import (
    AgentMatch,
    ChatResponse,
    ChatStatus,
    FieldOption,
    HistoryMessage,
    HistoryResponse,
    Manifest,
    PendingToolCall,
    ResumeRequest,
    RouteDecision,
    SessionMeta,
    SessionStatus,
    Suggestion,
    ToolDecision,
)
from pydantic import ValidationError


def test_manifest_defaults():
    m = Manifest(agent_id="a", name="N", description="D")
    assert m.capabilities == []
    assert m.examples == []
    assert m.hitl_tools == []


def test_chat_response_defaults():
    r = ChatResponse(status=ChatStatus.final)
    assert r.text is None
    assert r.tool_calls == []
    assert r.messages == []
    assert r.suggestions == []
    assert isinstance(r.session, SessionMeta)
    assert r.session.title == ""
    assert r.session.status.tone == "neutral"


def test_chat_status_enum_values():
    assert ChatStatus.final == "final"
    assert ChatStatus.interrupt == "interrupt"


def test_pending_tool_call_defaults():
    p = PendingToolCall(tool_call_id="c", tool_name="t")
    assert p.tool_label == ""
    assert p.args == {}
    assert p.field_options == {}
    assert p.field_labels == {}
    assert p.readonly_fields == []


def test_field_option_roundtrip():
    o = FieldOption(value="T1", label="Viagem")
    assert o.model_dump() == {"value": "T1", "label": "Viagem"}


def test_suggestion_default_nao_primario():
    s = Suggestion(label="L", message="M")
    assert s.primary is False


def test_session_status_tone_invalido_rejeitado():
    with pytest.raises(ValidationError):
        SessionStatus(label="x", tone="explosivo")


def test_agent_match_score_dentro_do_intervalo():
    assert AgentMatch(agent_id="a", score=0.5, motivo="m").score == 0.5


@pytest.mark.parametrize("score", [-0.1, 1.1])
def test_agent_match_score_fora_do_intervalo_rejeitado(score):
    with pytest.raises(ValidationError):
        AgentMatch(agent_id="a", score=score, motivo="m")


def test_route_decision_default_lista_vazia():
    assert RouteDecision().agents == []


def test_tool_decision_action_restrito():
    assert ToolDecision(tool_call_id="c", action="approve").edited_args is None
    with pytest.raises(ValidationError):
        ToolDecision(tool_call_id="c", action="talvez")


def test_resume_request_carrega_decisoes():
    req = ResumeRequest(
        thread_id="t", decisions=[ToolDecision(tool_call_id="c", action="reject")]
    )
    assert req.decisions[0].action == "reject"


def test_history_message_role_restrito():
    assert HistoryMessage(role="user", text="oi").role == "user"
    with pytest.raises(ValidationError):
        HistoryMessage(role="system", text="x")


def test_history_response_defaults():
    h = HistoryResponse()
    assert h.messages == []
    assert h.pending == []
    assert h.suggestions == []
    assert isinstance(h.session, SessionMeta)
