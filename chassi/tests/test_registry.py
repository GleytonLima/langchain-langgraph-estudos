"""Registry de agentes: lê o agents.yaml e enriquece com o /manifest (best-effort).

`_entries` é cacheado e lê um arquivo — apontamos `settings.agents_file` para um
YAML temporário e limpamos o cache. O httpx do /manifest é dublado para cobrir os
três casos: manifesto ok, agente offline (sem manifesto) e a busca por id.
"""

from __future__ import annotations

import app.registry as registry
import pytest


@pytest.fixture
def agents_yaml(tmp_path, monkeypatch):
    f = tmp_path / "agents.yaml"
    f.write_text(
        "agents:\n"
        "  - id: ag1\n"
        "    url: http://a1:8101/\n"  # barra final removida pelo registry
        "  - id: ag2\n"
        "    url: http://a2:8102\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(registry.settings, "agents_file", str(f))
    registry._entries.cache_clear()
    yield
    registry._entries.cache_clear()


def _manifest_payload(agent_id):
    return {
        "agent_id": agent_id,
        "name": f"Nome {agent_id}",
        "description": "desc",
        "capabilities": ["c1"],
    }


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


class _FakeClient:
    """Dublê do httpx.AsyncClient: get(url) delega para a função fornecida."""

    def __init__(self, get_fn):
        self._get_fn = get_fn

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        return self._get_fn(url)


def _install_client(monkeypatch, get_fn):
    monkeypatch.setattr(registry.httpx, "AsyncClient", lambda timeout: _FakeClient(get_fn))


def test_entries_le_yaml_e_normaliza_url(agents_yaml):
    entries = registry._entries()
    assert [e.id for e in entries] == ["ag1", "ag2"]
    assert entries[0].url == "http://a1:8101"  # sem barra final


def test_get_entry_encontra_e_falha(agents_yaml):
    assert registry.get_entry("ag2").url == "http://a2:8102"
    assert registry.get_entry("inexistente") is None


async def test_list_entries_enriquece_com_manifesto(agents_yaml, monkeypatch):
    def fake_get(url):
        aid = "ag1" if "a1" in url else "ag2"
        return _Resp(_manifest_payload(aid))

    _install_client(monkeypatch, fake_get)
    out = await registry.list_entries()
    assert out[0].manifest is not None
    assert out[0].manifest.name == "Nome ag1"


async def test_list_entries_agente_offline_fica_sem_manifesto(agents_yaml, monkeypatch):
    def fake_get(url):
        raise registry.httpx.ConnectError("offline")

    _install_client(monkeypatch, fake_get)
    out = await registry.list_entries()
    assert all(e.manifest is None for e in out)
    assert [e.id for e in out] == ["ag1", "ag2"]  # ainda aparecem na lista
