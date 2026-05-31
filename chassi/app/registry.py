"""Registry estático de agentes (agents.yaml) + descoberta de manifestos.

Cada entrada do YAML tem id + url. O chassi busca /manifest de cada agente para
conhecer suas capabilities (usadas no roteamento e exibidas no frontend).
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path

import httpx
import yaml
from contracts import Manifest
from pydantic import BaseModel

from .settings import settings


class AgentEntry(BaseModel):
    id: str
    url: str
    manifest: Manifest | None = None


@lru_cache
def _entries() -> list[AgentEntry]:
    raw = yaml.safe_load(Path(settings.agents_file).read_text(encoding="utf-8"))
    return [AgentEntry(id=a["id"], url=a["url"].rstrip("/")) for a in raw.get("agents", [])]


async def _fetch_manifest(client: httpx.AsyncClient, e: AgentEntry) -> AgentEntry:
    try:
        resp = await client.get(f"{e.url}/manifest")
        resp.raise_for_status()
        m = Manifest.model_validate(resp.json())
    except Exception:
        m = None  # agente offline: aparece sem manifesto
    return AgentEntry(id=e.id, url=e.url, manifest=m)


async def list_entries() -> list[AgentEntry]:
    """Lista os agentes, enriquecendo com o manifesto (best-effort).

    Busca os manifestos em paralelo (asyncio.gather): com N agentes, o tempo é o
    do mais lento, não a soma — e um agente offline não trava a lista.
    """
    entries = _entries()
    async with httpx.AsyncClient(timeout=5) as client:
        return list(await asyncio.gather(*(_fetch_manifest(client, e) for e in entries)))


def get_entry(agent_id: str) -> AgentEntry | None:
    for e in _entries():
        if e.id == agent_id:
            return e
    return None
