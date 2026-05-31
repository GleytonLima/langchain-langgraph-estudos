"""Fiação do agente (manifest + build_agent) e a LLM real (construção).

Não tocamos Postgres/LM Studio: manifest() é puro; build_agent é exercitado via o
conftest (ScriptedModel + MemorySaver). Aqui cobrimos o manifesto e o get_llm, que
apenas constrói o ChatOpenAI (sem chamada de rede).
"""

from __future__ import annotations

from app.agent import AGENT_ID, build_agent, manifest
from app.llm import get_llm
from app.tools import HITL_TOOLS
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langgraph.checkpoint.memory import MemorySaver


def test_manifest_expoe_id_capabilities_e_hitl():
    m = manifest()
    assert m.agent_id == AGENT_ID
    assert m.name == "Suporte de TI"
    assert m.capabilities  # lista não vazia
    assert m.hitl_tools == HITL_TOOLS


def test_build_agent_monta_grafo_compilavel():
    class _Fake(GenericFakeChatModel):
        def bind_tools(self, tools=None, **kwargs):  # noqa: ARG002
            return self

    agent = build_agent(_Fake(messages=iter([])), MemorySaver())
    assert hasattr(agent, "invoke")
    assert hasattr(agent, "get_state")


def test_get_llm_constroi_chatopenai_com_settings():
    from app.settings import settings

    llm = get_llm()
    assert llm.model_name == settings.llm_model
    assert llm.temperature == 0


async def test_checkpointer_e_setup_abrem_pool_e_criam_tabelas(monkeypatch):
    """_checkpointer monta o AsyncPostgresSaver (pool open=False) e setup_checkpointer
    abre o pool + chama setup() — sem tocar Postgres real."""
    import app.agent as agent_mod

    eventos = []

    class _FakePool:
        def __init__(self, *a, **k):
            eventos.append(("pool", k.get("open")))

        async def open(self):
            eventos.append("open")

    class _FakeSaver:
        def __init__(self, pool):
            eventos.append("saver")
            self.conn = pool

        async def setup(self):
            eventos.append("setup")

    monkeypatch.setattr(agent_mod, "AsyncConnectionPool", _FakePool)
    monkeypatch.setattr(agent_mod, "AsyncPostgresSaver", _FakeSaver)
    agent_mod._checkpointer.cache_clear()
    cp = agent_mod._checkpointer()
    assert isinstance(cp, _FakeSaver)
    await agent_mod.setup_checkpointer()
    agent_mod._checkpointer.cache_clear()

    # pool criado com open=False (abre depois, no event loop), depois open + setup
    assert eventos == [("pool", False), "saver", "open", "setup"]


def test_get_agent_usa_llm_e_checkpointer(monkeypatch):
    import app.agent as agent_mod

    sentinel = object()
    monkeypatch.setattr(agent_mod, "get_llm", lambda: object())
    monkeypatch.setattr(agent_mod, "_checkpointer", lambda: MemorySaver())
    monkeypatch.setattr(agent_mod, "build_agent", lambda model, checkpointer: sentinel)
    agent_mod.get_agent.cache_clear()
    assert agent_mod.get_agent() is sentinel
    agent_mod.get_agent.cache_clear()
