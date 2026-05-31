"""Endpoints HTTP do agente (FastAPI). Usa TestClient com o runtime dublado.

Não sobe LLM nem Postgres: cada handler apenas delega para run_chat/run_resume/
run_history/manifest, que substituímos por stubs. O foco é a fiação HTTP.
"""

from __future__ import annotations

import app.main as main
from contracts import ChatResponse, ChatStatus, HistoryMessage, HistoryResponse, Manifest
from fastapi.testclient import TestClient


def _client(monkeypatch) -> TestClient:
    # lifespan chama warmup() (LLM+Postgres). Dublamos p/ não tocar infra real.
    async def fake_warmup():
        return None

    monkeypatch.setattr(main, "warmup", fake_warmup)
    return TestClient(main.app)


def test_manifest_endpoint(monkeypatch):
    fake = Manifest(agent_id="x", name="N", description="D", capabilities=["c"])
    monkeypatch.setattr(main, "manifest", lambda: fake)
    with _client(monkeypatch) as c:
        resp = c.get("/manifest")
    assert resp.status_code == 200
    assert resp.json()["agent_id"] == "x"


def test_lifespan_tolera_falha_no_warmup(monkeypatch):
    async def boom():
        raise RuntimeError("sem postgres")

    monkeypatch.setattr(main, "warmup", boom)
    with TestClient(main.app) as c:
        assert c.get("/health").status_code == 200


def test_health_endpoint(monkeypatch):
    with _client(monkeypatch) as c:
        resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_chat_endpoint(monkeypatch):
    captured = {}

    async def fake_run_chat(thread_id, user_input):
        captured["args"] = (thread_id, user_input)
        return ChatResponse(status=ChatStatus.final, text="oi")

    monkeypatch.setattr(main, "run_chat", fake_run_chat)
    with _client(monkeypatch) as c:
        resp = c.post("/chat", json={"thread_id": "t1", "input": "olá"})
    assert resp.status_code == 200
    assert resp.json()["text"] == "oi"
    assert captured["args"] == ("t1", "olá")


def test_resume_endpoint(monkeypatch):
    captured = {}

    async def fake_run_resume(thread_id, decisions):
        captured["args"] = (thread_id, decisions)
        return ChatResponse(status=ChatStatus.final, text="feito")

    monkeypatch.setattr(main, "run_resume", fake_run_resume)
    with _client(monkeypatch) as c:
        resp = c.post(
            "/resume",
            json={"thread_id": "t1", "decisions": [{"tool_call_id": "a", "action": "approve"}]},
        )
    assert resp.status_code == 200
    assert resp.json()["text"] == "feito"
    tid, decisions = captured["args"]
    assert tid == "t1"
    assert decisions[0].action == "approve"


def test_history_endpoint(monkeypatch):
    async def fake_run_history(thread_id):
        return HistoryResponse(messages=[HistoryMessage(role="user", text="oi")])

    monkeypatch.setattr(main, "run_history", fake_run_history)
    with _client(monkeypatch) as c:
        resp = c.get("/history/t1")
    assert resp.status_code == 200
    assert resp.json()["messages"][0]["text"] == "oi"
