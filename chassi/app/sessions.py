"""Sessões do chassi: mapeia session_id -> (agent_id, thread_id) no Postgres.

Permite continuar a conversa de onde parou: o chassi guarda com quem (agent_id) e
em qual thread o usuário estava; o agente recupera o estado pelo thread_id no seu
próprio checkpointer. Usamos thread_id = session_id (KISS).
"""

from __future__ import annotations

import uuid
from functools import lru_cache

from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel

from .settings import settings


class Session(BaseModel):
    id: str
    agent_id: str
    thread_id: str


class SessionInfo(BaseModel):
    """Resumo para a lista de conversas anteriores (sem o thread_id interno).

    `title`/`status_*` são METADADOS de exibição (não dado de negócio): o agente os
    devolve em cada `SessionMeta` e o chassi os persiste aqui, opacos. Assim a
    listagem já traz o título pronto — o frontend não precisa cachear em localStorage
    nem reconstruir via /history.
    """

    id: str
    agent_id: str
    created_at: str
    title: str = ""
    status_label: str = "Em andamento"
    status_tone: str = "progress"


@lru_cache
def _pool() -> AsyncConnectionPool:
    # open=False: o pool async deve ser aberto DENTRO do event loop (em setup,
    # chamado no lifespan) — abrir no construtor, fora do loop, emite warning.
    return AsyncConnectionPool(
        settings.database_url, max_size=10, open=False, kwargs={"autocommit": True}
    )


async def setup() -> None:
    """Abre o pool e cria a tabela. Chamado no startup do chassi (lifespan)."""
    pool = _pool()
    await pool.open()
    async with pool.connection() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chassi_sessions (
                id           TEXT PRIMARY KEY,
                agent_id     TEXT NOT NULL,
                thread_id    TEXT NOT NULL,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                title        TEXT NOT NULL DEFAULT '',
                status_label TEXT NOT NULL DEFAULT 'Em andamento',
                status_tone  TEXT NOT NULL DEFAULT 'progress'
            )
            """
        )
        # migração de bancos já existentes (colunas de metadado adicionadas depois)
        await conn.execute("ALTER TABLE chassi_sessions ADD COLUMN IF NOT EXISTS title TEXT NOT NULL DEFAULT ''")
        await conn.execute(
            "ALTER TABLE chassi_sessions ADD COLUMN IF NOT EXISTS status_label TEXT NOT NULL DEFAULT 'Em andamento'"
        )
        await conn.execute(
            "ALTER TABLE chassi_sessions ADD COLUMN IF NOT EXISTS status_tone TEXT NOT NULL DEFAULT 'progress'"
        )


async def create_session(agent_id: str) -> Session:
    async with _pool().connection() as conn:
        # Reaproveita uma conversa VAZIA do mesmo agente (title='' => nenhum chat
        # ainda) em vez de criar outra — senão clicar no agente várias vezes polui a
        # lista com sessões em branco.
        cur = await conn.execute(
            "SELECT id, thread_id FROM chassi_sessions "
            "WHERE agent_id = %s AND title = '' ORDER BY created_at DESC LIMIT 1",
            (agent_id,),
        )
        existente = await cur.fetchone()
        if existente is not None:
            return Session(id=existente[0], agent_id=agent_id, thread_id=existente[1])

        sid = uuid.uuid4().hex
        await conn.execute(
            "INSERT INTO chassi_sessions (id, agent_id, thread_id) VALUES (%s, %s, %s)",
            (sid, agent_id, sid),
        )
    return Session(id=sid, agent_id=agent_id, thread_id=sid)


_LIST_LIMIT = 50  # teto simples (sem paginação) — ver "limitação conhecida" no AGENTS.md


async def list_sessions() -> list[SessionInfo]:
    """As conversas mais recentes (até `_LIST_LIMIT`). Sem paginação — KISS para o
    estudo; basta para o uso single-user. Ver AGENTS.md (limitação conhecida)."""
    async with _pool().connection() as conn:
        cur = await conn.execute(
            f"SELECT id, agent_id, created_at, title, status_label, status_tone "
            f"FROM chassi_sessions ORDER BY created_at DESC LIMIT {_LIST_LIMIT}"
        )
        rows = await cur.fetchall()
    return [
        SessionInfo(
            id=r[0],
            agent_id=r[1],
            created_at=r[2].isoformat(),
            title=r[3],
            status_label=r[4],
            status_tone=r[5],
        )
        for r in rows
    ]


async def update_session_meta(session_id: str, title: str, status_label: str, status_tone: str) -> None:
    """Grava os metadados de exibição da sessão (vindos do `SessionMeta` do agente).

    O `title` só sobrescreve quando vem preenchido — assim um turno sem título de
    domínio (ex.: antes de criar o relatório) não apaga um título já obtido.
    """
    async with _pool().connection() as conn:
        await conn.execute(
            "UPDATE chassi_sessions SET "
            "title = CASE WHEN %s <> '' THEN %s ELSE title END, "
            "status_label = %s, status_tone = %s WHERE id = %s",
            (title, title, status_label, status_tone, session_id),
        )


async def get_session(session_id: str) -> Session | None:
    async with _pool().connection() as conn:
        cur = await conn.execute(
            "SELECT id, agent_id, thread_id FROM chassi_sessions WHERE id = %s",
            (session_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return Session(id=row[0], agent_id=row[1], thread_id=row[2])
