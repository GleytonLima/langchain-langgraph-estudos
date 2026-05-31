"""Helpers internos do runtime: callbacks do Langfuse e leitura de estado.

Funções pequenas, mas com ramos importantes (Langfuse ligado/desligado, estado
vazio). Não tocam LLM/Postgres — usam um agente stub e monkeypatch nas settings.
"""

from __future__ import annotations

import app.runtime as rt
from langchain_core.messages import AIMessage, HumanMessage


class _State:
    def __init__(self, messages, nxt=()):
        self.values = {"messages": messages} if messages is not None else None
        self.next = nxt


class _FakeAgent:
    def __init__(self, state):
        self._state = state

    async def aget_state(self, config):
        return self._state


_CFG = {"configurable": {"thread_id": "t1"}}


# --------------------------------------------------------------------------- #
# _callbacks: depende das chaves do Langfuse
# --------------------------------------------------------------------------- #


def test_callbacks_vazio_sem_chaves(monkeypatch):
    monkeypatch.setattr(rt.settings, "langfuse_public_key", "")
    monkeypatch.setattr(rt.settings, "langfuse_secret_key", "")
    rt._callbacks.cache_clear()
    assert rt._callbacks() == []
    rt._callbacks.cache_clear()


def _fake_langfuse(monkeypatch, *, auth_ok: bool):
    """Injeta módulos langfuse dublês p/ controlar o caminho de _callbacks."""
    import sys
    import types

    lf = types.ModuleType("langfuse")
    lf.get_client = lambda: types.SimpleNamespace(auth_check=lambda: auth_ok)
    lf_lc = types.ModuleType("langfuse.langchain")
    lf_lc.CallbackHandler = lambda: object()
    monkeypatch.setitem(sys.modules, "langfuse", lf)
    monkeypatch.setitem(sys.modules, "langfuse.langchain", lf_lc)


def test_callbacks_vazio_quando_auth_check_falha(monkeypatch):
    monkeypatch.setattr(rt.settings, "langfuse_public_key", "pk")
    monkeypatch.setattr(rt.settings, "langfuse_secret_key", "sk")
    _fake_langfuse(monkeypatch, auth_ok=False)
    rt._callbacks.cache_clear()
    assert rt._callbacks() == []
    rt._callbacks.cache_clear()


def test_callbacks_retorna_handler_quando_auth_ok(monkeypatch):
    monkeypatch.setattr(rt.settings, "langfuse_public_key", "pk")
    monkeypatch.setattr(rt.settings, "langfuse_secret_key", "sk")
    _fake_langfuse(monkeypatch, auth_ok=True)
    rt._callbacks.cache_clear()
    assert len(rt._callbacks()) == 1
    rt._callbacks.cache_clear()


def test_callbacks_degrada_quando_import_falha(monkeypatch):
    monkeypatch.setattr(rt.settings, "langfuse_public_key", "pk")
    monkeypatch.setattr(rt.settings, "langfuse_secret_key", "sk")
    import sys

    # força ImportError no `from langfuse import get_client` -> ramo except
    monkeypatch.setitem(sys.modules, "langfuse", None)
    rt._callbacks.cache_clear()
    assert rt._callbacks() == []
    rt._callbacks.cache_clear()


# --------------------------------------------------------------------------- #
# _pending_tool_calls / _last_text: ramos de estado vazio
# --------------------------------------------------------------------------- #


async def test_pending_vazio_sem_mensagens():
    agent = _FakeAgent(_State([]))
    assert await rt._pending_tool_calls(agent, _CFG) == []


async def test_pending_vazio_quando_ultima_nao_e_aimessage_com_toolcalls():
    agent = _FakeAgent(_State([HumanMessage(content="oi")]))
    assert await rt._pending_tool_calls(agent, _CFG) == []


async def test_pending_vazio_quando_state_values_none():
    agent = _FakeAgent(_State(None))
    assert await rt._pending_tool_calls(agent, _CFG) == []


def test_field_options_vazio_para_tool_sem_referencias():
    assert rt._field_options("listar_tipos") == {}


async def test_last_text_vazio_sem_aimessage_com_conteudo():
    agent = _FakeAgent(_State([HumanMessage(content="oi"), AIMessage(content="")]))
    assert await rt._last_text(agent, _CFG) == ""


async def test_last_text_pega_ultima_aimessage_com_conteudo():
    agent = _FakeAgent(
        _State([AIMessage(content="primeira"), HumanMessage(content="x"), AIMessage(content="final")])
    )
    assert await rt._last_text(agent, _CFG) == "final"


async def test_warmup_aquece_agente_callbacks_e_checkpointer(monkeypatch):
    chamadas = []

    async def fake_setup():
        chamadas.append("setup")

    monkeypatch.setattr(rt, "get_agent", lambda: chamadas.append("agent"))
    monkeypatch.setattr(rt, "setup_checkpointer", fake_setup)
    monkeypatch.setattr(rt, "_callbacks", lambda: chamadas.append("cb"))
    await rt.warmup()
    assert chamadas == ["agent", "setup", "cb"]
