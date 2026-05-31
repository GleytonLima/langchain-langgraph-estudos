"""Proxy assíncrono do chassi: encaminha o turno ao agente certo.

Mockamos `get_entry` (registry) e o `httpx.AsyncClient` para não tocar rede. O
foco é: monta a URL certa, repassa o payload com o thread_id da sessão e valida o
ChatResponse.
"""

from __future__ import annotations

import app.proxy as proxy
import pytest
from app.registry import AgentEntry
from contracts import ChatStatus


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


class _FakeClient:
    """Dublê do httpx.AsyncClient: captura url/json e devolve uma resposta fixa."""

    def __init__(self, capturado, resp):
        self._capturado = capturado
        self._resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json):
        self._capturado["url"] = url
        self._capturado["json"] = json
        return self._resp

    async def get(self, url):
        self._capturado["url"] = url
        return self._resp


def _install_client(monkeypatch, capturado, resp):
    monkeypatch.setattr(proxy.httpx, "AsyncClient", lambda timeout: _FakeClient(capturado, resp))


def _entry():
    return AgentEntry(id="ag", url="http://agente:8101")


def _chat_payload(text="oi"):
    return {"status": "final", "text": text}


async def test_proxy_chat_monta_url_e_payload(monkeypatch):
    monkeypatch.setattr(proxy, "get_entry", lambda aid: _entry())
    capturado = {}
    _install_client(monkeypatch, capturado, _Resp(_chat_payload()))
    out = await proxy.proxy_chat("ag", "thread-1", "olá")
    assert out.status == ChatStatus.final
    assert capturado["url"] == "http://agente:8101/chat"
    assert capturado["json"] == {"thread_id": "thread-1", "input": "olá"}


async def test_proxy_resume_monta_url_e_decisoes(monkeypatch):
    monkeypatch.setattr(proxy, "get_entry", lambda aid: _entry())
    capturado = {}
    _install_client(monkeypatch, capturado, _Resp(_chat_payload("feito")))
    decisoes = [{"tool_call_id": "a", "action": "approve"}]
    out = await proxy.proxy_resume("ag", "thread-1", decisoes)
    assert out.text == "feito"
    assert capturado["url"] == "http://agente:8101/resume"
    assert capturado["json"] == {"thread_id": "thread-1", "decisions": decisoes}


async def test_proxy_history_monta_url(monkeypatch):
    monkeypatch.setattr(proxy, "get_entry", lambda aid: _entry())
    capturado = {}
    _install_client(monkeypatch, capturado, _Resp({"messages": [{"role": "user", "text": "oi"}]}))
    out = await proxy.proxy_history("ag", "thread-1")
    assert capturado["url"] == "http://agente:8101/history/thread-1"
    assert out.messages[0].text == "oi"


@pytest.mark.parametrize(
    "fn,args",
    [
        ("proxy_chat", ("ag", "t", "oi")),
        ("proxy_resume", ("ag", "t", [])),
        ("proxy_history", ("ag", "t")),
    ],
)
async def test_proxy_agente_desconhecido_levanta_valueerror(monkeypatch, fn, args):
    monkeypatch.setattr(proxy, "get_entry", lambda aid: None)
    with pytest.raises(ValueError, match="agente desconhecido"):
        await getattr(proxy, fn)(*args)


def test_timeout_usa_settings(monkeypatch):
    monkeypatch.setattr(proxy.settings, "agent_timeout_seconds", 12.0)
    t = proxy._timeout()
    assert t.read == 12.0
    assert t.connect == 30.0
