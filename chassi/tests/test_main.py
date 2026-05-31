"""Endpoints HTTP do chassi (FastAPI). TestClient com as dependências dubladas.

Cada handler delega para registry/router/sessions/proxy — substituímos esses por
stubs. Cobrimos as rotas, o 404 de sessão e a tradução de falhas do agente
(timeout/erro de rede/ValueError) em HTTP errors legíveis (_proxy_agent).
"""

from __future__ import annotations

import app.main as main
import httpx
import pytest
from app.registry import AgentEntry
from app.sessions import Session, SessionInfo
from contracts import (
    AgentMatch,
    ChatResponse,
    ChatStatus,
    HistoryResponse,
    Manifest,
    RouteDecision,
    SessionMeta,
    SessionStatus,
)
from fastapi.testclient import TestClient

client = TestClient(main.app)


def _session():
    return Session(id="s1", agent_id="ag", thread_id="s1")


# ---- lifespan: abre o pool de sessões no boot (best-effort) ---- #


def test_lifespan_chama_sessions_setup(monkeypatch):
    chamou = []

    async def fake_setup():
        chamou.append(True)

    monkeypatch.setattr(main, "sessions_setup", fake_setup)
    with TestClient(main.app):
        pass
    assert chamou == [True]


def test_lifespan_tolera_falha_no_setup(monkeypatch):
    async def boom():
        raise RuntimeError("sem postgres")

    monkeypatch.setattr(main, "sessions_setup", boom)
    with TestClient(main.app):  # app sobe mesmo se o setup falhar
        pass


def _async(value):
    """Fabrica uma coroutine-function que devolve `value` (stub p/ deps async)."""

    async def _f(*a, **k):
        return value

    return _f


# ---- agentes / rota ---- #


def test_agents_lista_com_e_sem_manifesto(monkeypatch):
    m = Manifest(agent_id="a1", name="N", description="d")
    monkeypatch.setattr(
        main,
        "list_entries",
        _async(
            [
                AgentEntry(id="a1", url="http://a1", manifest=m),
                AgentEntry(id="a2", url="http://a2", manifest=None),
            ]
        ),
    )
    body = client.get("/api/agents").json()
    assert body[0]["manifest"]["name"] == "N"
    assert body[1]["manifest"] is None


def test_route_endpoint(monkeypatch):
    monkeypatch.setattr(
        main,
        "route",
        _async(RouteDecision(agents=[AgentMatch(agent_id="a1", score=0.9, motivo="m")])),
    )
    body = client.post("/api/route", json={"question": "oi"}).json()
    assert body["agents"][0]["agent_id"] == "a1"


# ---- sessões ---- #


def test_create_session(monkeypatch):
    monkeypatch.setattr(main, "create_session", _async(Session(id="s1", agent_id="ag", thread_id="s1")))
    body = client.post("/api/sessions", json={"agent_id": "ag"}).json()
    assert body == {"id": "s1", "agent_id": "ag", "thread_id": "s1"}


def test_list_sessions(monkeypatch):
    monkeypatch.setattr(
        main, "list_sessions", _async([SessionInfo(id="s1", agent_id="ag", created_at="2026-05-30T12:00:00")])
    )
    body = client.get("/api/sessions").json()
    assert body[0]["id"] == "s1"


def test_get_session_ok_e_404(monkeypatch):
    async def fake(sid):
        return _session() if sid == "s1" else None

    monkeypatch.setattr(main, "get_session", fake)
    assert client.get("/api/sessions/s1").json()["agent_id"] == "ag"
    resp = client.get("/api/sessions/xxx")
    assert resp.status_code == 404


# ---- chat / resume / history via proxy ---- #


def test_chat_ok(monkeypatch):
    monkeypatch.setattr(main, "get_session", _async(_session()))
    monkeypatch.setattr(main, "proxy_chat", _async(ChatResponse(status=ChatStatus.final, text="oi")))
    _capture_update(monkeypatch)  # _persist_meta sempre grava (session tem default)
    body = client.post("/api/sessions/s1/chat", json={"input": "olá"}).json()
    assert body["text"] == "oi"


def test_resume_ok(monkeypatch):
    monkeypatch.setattr(main, "get_session", _async(_session()))
    monkeypatch.setattr(main, "proxy_resume", _async(ChatResponse(status=ChatStatus.final, text="feito")))
    _capture_update(monkeypatch)
    body = client.post("/api/sessions/s1/resume", json={"decisions": []}).json()
    assert body["text"] == "feito"


def _capture_update(monkeypatch) -> dict:
    captured: dict = {}

    async def fake_update(session_id, title, label, tone):
        captured["args"] = (session_id, title, label, tone)

    monkeypatch.setattr(main, "update_session_meta", fake_update)
    return captured


def _resp_com_session(title: str, label: str, tone: str) -> ChatResponse:
    return ChatResponse(
        status=ChatStatus.final, text="ok",
        session=SessionMeta(title=title, status=SessionStatus(label=label, tone=tone)),
    )


def test_chat_persiste_meta_do_agente(monkeypatch):
    monkeypatch.setattr(main, "get_session", _async(_session()))
    monkeypatch.setattr(main, "proxy_chat", _async(_resp_com_session("Viagem SP", "Enviado", "success")))
    captured = _capture_update(monkeypatch)
    client.post("/api/sessions/s1/chat", json={"input": "quero registrar"})
    assert captured["args"] == ("s1", "Viagem SP", "Enviado", "success")


def test_chat_sem_titulo_usa_input_como_fallback(monkeypatch):
    monkeypatch.setattr(main, "get_session", _async(_session()))
    monkeypatch.setattr(main, "proxy_chat", _async(_resp_com_session("", "Aguardando você", "attention")))
    captured = _capture_update(monkeypatch)
    client.post("/api/sessions/s1/chat", json={"input": "Quero registrar uma despesa"})
    # sem título do agente -> fallback = input do usuário
    assert captured["args"] == ("s1", "Quero registrar uma despesa", "Aguardando você", "attention")


def test_resume_persiste_meta(monkeypatch):
    monkeypatch.setattr(main, "get_session", _async(_session()))
    monkeypatch.setattr(main, "proxy_resume", _async(_resp_com_session("Viagem SP", "Enviado", "success")))
    captured = _capture_update(monkeypatch)
    client.post("/api/sessions/s1/resume", json={"decisions": []})
    assert captured["args"] == ("s1", "Viagem SP", "Enviado", "success")


def test_history_ok(monkeypatch):
    monkeypatch.setattr(main, "get_session", _async(_session()))
    monkeypatch.setattr(main, "proxy_history", _async(HistoryResponse()))
    assert client.get("/api/sessions/s1/history").status_code == 200


def test_chat_sessao_inexistente_404(monkeypatch):
    monkeypatch.setattr(main, "get_session", _async(None))
    resp = client.post("/api/sessions/xxx/chat", json={"input": "oi"})
    assert resp.status_code == 404


# ---- _proxy_agent: tradução de falhas do agente ---- #


@pytest.mark.parametrize(
    "exc,status",
    [
        (httpx.TimeoutException("demorou"), 504),
        (httpx.ConnectError("sem rede"), 502),
        (ValueError("agente desconhecido: x"), 400),
    ],
)
def test_proxy_agent_traduz_falhas(monkeypatch, exc, status):
    monkeypatch.setattr(main, "get_session", _async(_session()))

    async def boom(*a, **k):
        raise exc

    monkeypatch.setattr(main, "proxy_chat", boom)
    resp = client.post("/api/sessions/s1/chat", json={"input": "oi"})
    assert resp.status_code == status


def test_proxy_agent_http_status_error(monkeypatch):
    monkeypatch.setattr(main, "get_session", _async(_session()))

    async def boom(*a, **k):
        request = httpx.Request("POST", "http://agente/chat")
        response = httpx.Response(500, request=request)
        raise httpx.HTTPStatusError("erro", request=request, response=response)

    monkeypatch.setattr(main, "proxy_chat", boom)
    resp = client.post("/api/sessions/s1/chat", json={"input": "oi"})
    assert resp.status_code == 502
    assert "500" in resp.json()["detail"]
