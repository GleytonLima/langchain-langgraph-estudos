"""Sessões do chassi: session_id -> (agent_id, thread_id) no Postgres (async).

O pool é dublado por um fake em memória (sem Postgres): captura o SQL/params e
devolve linhas controladas. Validamos a regra de negócio — thread_id = id, ordem
da listagem e o None quando a sessão não existe.
"""

from __future__ import annotations

import datetime

import app.sessions as sessions
import pytest


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    async def fetchall(self):
        return self._rows

    async def fetchone(self):
        return self._rows[0] if self._rows else None


class _Conn:
    def __init__(self, store):
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, sql, params=None):
        self.store["calls"].append((sql, params))
        if sql.strip().upper().startswith("INSERT"):
            self.store["rows"].append(params)
            return _Cursor([])
        if "WHERE id" in sql:
            sid = params[0]
            match = [r for r in self.store["rows"] if r[0] == sid]
            return _Cursor(match)
        # SELECT ... ORDER BY (list_sessions): inclui created_at no fim
        return _Cursor(self.store["select_rows"])


class _Pool:
    def __init__(self, store):
        self.store = store

    def connection(self):
        return _Conn(self.store)


@pytest.fixture
def fake_pool(monkeypatch):
    store = {"calls": [], "rows": [], "select_rows": []}
    monkeypatch.setattr(sessions, "_pool", lambda: _Pool(store))
    return store


async def test_create_session_usa_id_como_thread_id(fake_pool, monkeypatch):
    monkeypatch.setattr(sessions.uuid, "uuid4", lambda: type("U", (), {"hex": "abc123"})())
    s = await sessions.create_session("ag")
    assert s.id == "abc123"
    assert s.thread_id == "abc123"  # KISS: thread_id == session_id
    assert s.agent_id == "ag"
    # persistiu (id, agent_id, thread_id)
    assert fake_pool["rows"][0] == ("abc123", "ag", "abc123")


async def test_create_session_reaproveita_sessao_vazia(fake_pool):
    # há uma conversa vazia (title='') -> a SELECT a encontra e ela é reusada
    fake_pool["select_rows"] = [("vazia1", "vazia1")]  # (id, thread_id)
    s = await sessions.create_session("ag")
    assert (s.id, s.thread_id) == ("vazia1", "vazia1")
    # não inseriu uma nova sessão
    assert all(not str(sql).strip().upper().startswith("INSERT") for sql, _ in fake_pool["calls"])


async def test_get_session_existente_e_inexistente(fake_pool):
    fake_pool["rows"].append(("s1", "ag", "s1"))
    encontrada = await sessions.get_session("s1")
    assert encontrada.agent_id == "ag"
    assert await sessions.get_session("nao-existe") is None


async def test_setup_abre_pool_e_cria_tabela(monkeypatch):
    """setup() abre o pool e cria a tabela (CREATE TABLE IF NOT EXISTS)."""
    sqls = []
    eventos = []

    class _C:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def execute(self, sql, params=None):
            sqls.append(sql)

    class _P:
        async def open(self):
            eventos.append("open")

        def connection(self):
            return _C()

    monkeypatch.setattr(sessions, "_pool", lambda: _P())
    await sessions.setup()
    assert eventos == ["open"]
    assert any("CREATE TABLE IF NOT EXISTS chassi_sessions" in s for s in sqls)


def test_pool_constroi_async_connection_pool(monkeypatch):
    """_pool() monta um AsyncConnectionPool com open=False (abre no setup)."""
    capturado = {}

    class _P:
        def __init__(self, *a, **k):
            capturado["args"] = a
            capturado["kwargs"] = k

    monkeypatch.setattr(sessions, "AsyncConnectionPool", _P)
    sessions._pool.cache_clear()
    pool = sessions._pool()
    sessions._pool.cache_clear()
    assert isinstance(pool, _P)
    assert capturado["kwargs"]["open"] is False


async def test_list_sessions_mapeia_meta_e_formata_data(fake_pool):
    dt = datetime.datetime(2026, 5, 30, 12, 0, 0)
    fake_pool["select_rows"] = [
        ("s1", "ag1", dt, "Viagem SP", "Enviado", "success"),
        ("s2", "ag2", dt, "", "Em andamento", "progress"),
    ]
    out = await sessions.list_sessions()
    assert [s.id for s in out] == ["s1", "s2"]
    assert out[0].created_at == dt.isoformat()
    # metadados de exibição vêm da própria listagem (sem localStorage no frontend)
    assert (out[0].title, out[0].status_label, out[0].status_tone) == ("Viagem SP", "Enviado", "success")
    # teto simples sem paginação: a query limita aos N mais recentes
    sql = fake_pool["calls"][-1][0]
    assert f"LIMIT {sessions._LIST_LIMIT}" in sql


async def test_update_session_meta_grava_titulo_e_status(fake_pool):
    await sessions.update_session_meta("s1", "Viagem SP", "Enviado", "success")
    sql, params = fake_pool["calls"][-1]
    assert sql.strip().upper().startswith("UPDATE")
    assert params == ("Viagem SP", "Viagem SP", "Enviado", "success", "s1")
    # título vazio NÃO sobrescreve um já existente (CASE WHEN ... <> '')
    assert "CASE WHEN" in sql
