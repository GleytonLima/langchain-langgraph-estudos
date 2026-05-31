"""Roteador: sugere quais agentes respondem à pergunta. Saída anti-alucinação.

A LLM é dublada (sem LM Studio): controlamos o RouteDecision devolvido para validar
as garantias do roteador — descarta ids fora do registry, ordena por score e
degrada para lista vazia quando não há catálogo ou a LLM falha.
"""

from __future__ import annotations

import sys
import types

import pytest

import app.router_llm as router
from app.registry import AgentEntry
from contracts import AgentMatch, Manifest, RouteDecision


def _entry(aid, com_manifesto=True):
    m = (
        Manifest(agent_id=aid, name=f"N{aid}", description="d", capabilities=["c"])
        if com_manifesto
        else None
    )
    return AgentEntry(id=aid, url=f"http://{aid}", manifest=m)


class _FakeStructured:
    def __init__(self, decision=None, erro=False):
        self._decision = decision
        self._erro = erro

    async def ainvoke(self, prompt, config=None):
        self.config = config  # captura p/ asserts (callbacks do Langfuse)
        if self._erro:
            raise RuntimeError("LLM caiu")
        return self._decision


class _FakeLLM:
    def __init__(self, structured):
        self._structured = structured

    def with_structured_output(self, schema):
        return self._structured


def _entries_async(lst):
    async def _f():
        return lst

    return _f


async def test_sem_agentes_com_manifesto_retorna_vazio(monkeypatch):
    monkeypatch.setattr(router, "list_entries", _entries_async([_entry("a", com_manifesto=False)]))
    out = await router.route("qualquer")
    assert out.agents == []


async def test_llm_falha_retorna_vazio(monkeypatch):
    monkeypatch.setattr(router, "list_entries", _entries_async([_entry("a")]))
    monkeypatch.setattr(router, "_llm", lambda: _FakeLLM(_FakeStructured(erro=True)))
    assert (await router.route("oi")).agents == []


async def test_descarta_ids_fora_do_registry_e_ordena_por_score(monkeypatch):
    monkeypatch.setattr(router, "list_entries", _entries_async([_entry("a"), _entry("b")]))
    decision = RouteDecision(
        agents=[
            AgentMatch(agent_id="a", score=0.3, motivo="m"),
            AgentMatch(agent_id="fantasma", score=0.9, motivo="alucinado"),
            AgentMatch(agent_id="b", score=0.8, motivo="m"),
        ]
    )
    monkeypatch.setattr(router, "_llm", lambda: _FakeLLM(_FakeStructured(decision)))
    out = await router.route("pergunta")
    # fantasma descartado; sobra a/b ordenados por score desc
    assert [a.agent_id for a in out.agents] == ["b", "a"]


def test_llm_constroi_chatopenai_com_settings():
    llm = router._llm()
    assert llm.model_name == router.settings.llm_model
    assert llm.temperature == 0


def test_catalogo_ignora_entries_sem_manifesto(monkeypatch):
    entries = [_entry("a"), _entry("sem", com_manifesto=False)]
    catalog = router._catalog(entries)
    assert "id=a" in catalog
    assert "sem" not in catalog


async def test_route_passa_callbacks_do_langfuse_ao_invoke(monkeypatch):
    monkeypatch.setattr(router, "list_entries", _entries_async([_entry("a")]))
    structured = _FakeStructured(RouteDecision(agents=[]))
    monkeypatch.setattr(router, "_llm", lambda: _FakeLLM(structured))
    monkeypatch.setattr(router, "_callbacks", lambda: ["CB"])
    await router.route("oi")
    assert structured.config == {"callbacks": ["CB"]}


# ---------------------------------------------------------------------------
# _callbacks (Langfuse) — mesmo padrão do agente
# ---------------------------------------------------------------------------


def _fake_langfuse(monkeypatch, auth_ok: bool):
    """Injeta módulos langfuse/langfuse.langchain dublês p/ não tocar a SDK real."""
    captured = {}

    class _Client:
        def auth_check(self):
            return auth_ok

    class _Handler:
        def __init__(self):
            captured["handler"] = True

    lf = types.ModuleType("langfuse")
    lf.get_client = lambda: _Client()
    lf_lc = types.ModuleType("langfuse.langchain")
    lf_lc.CallbackHandler = _Handler
    monkeypatch.setitem(sys.modules, "langfuse", lf)
    monkeypatch.setitem(sys.modules, "langfuse.langchain", lf_lc)
    return captured


@pytest.fixture(autouse=True)
def _limpa_cache_callbacks():
    router._callbacks.cache_clear()
    yield
    router._callbacks.cache_clear()


def test_callbacks_vazio_sem_chaves(monkeypatch):
    monkeypatch.setattr(router.settings, "langfuse_public_key", "")
    monkeypatch.setattr(router.settings, "langfuse_secret_key", "")
    assert router._callbacks() == []


def test_callbacks_monta_handler_quando_auth_ok(monkeypatch):
    monkeypatch.setattr(router.settings, "langfuse_public_key", "pk")
    monkeypatch.setattr(router.settings, "langfuse_secret_key", "sk")
    captured = _fake_langfuse(monkeypatch, auth_ok=True)
    out = router._callbacks()
    assert len(out) == 1
    assert captured.get("handler") is True


def test_callbacks_vazio_quando_auth_falha(monkeypatch):
    monkeypatch.setattr(router.settings, "langfuse_public_key", "pk")
    monkeypatch.setattr(router.settings, "langfuse_secret_key", "sk")
    _fake_langfuse(monkeypatch, auth_ok=False)
    assert router._callbacks() == []


def test_callbacks_vazio_quando_import_falha(monkeypatch):
    monkeypatch.setattr(router.settings, "langfuse_public_key", "pk")
    monkeypatch.setattr(router.settings, "langfuse_secret_key", "sk")
    monkeypatch.setitem(sys.modules, "langfuse", None)  # força ImportError
    assert router._callbacks() == []
