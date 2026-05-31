"""Proxy assíncrono: repassa o turno ao agente e devolve a resposta (JSON).

O chassi é um proxy (metáfora do call center): conecta o usuário a UM agente por
vez e apenas encaminha a requisição, reescrevendo o thread_id para o da sessão.
Usa httpx.AsyncClient: enquanto um agente processa, o event loop atende outros
usuários em vez de prender uma thread do pool — é o que permite escalar.
"""

from __future__ import annotations

import httpx
from contracts import ChatResponse, HistoryResponse

from .registry import get_entry
from .settings import settings


def _timeout() -> httpx.Timeout:
    seconds = settings.agent_timeout_seconds
    return httpx.Timeout(seconds, connect=30.0)


async def _post(url: str, payload: dict) -> ChatResponse:
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        resp = await client.post(url, json=payload)
    resp.raise_for_status()
    return ChatResponse.model_validate(resp.json())


async def proxy_chat(agent_id: str, thread_id: str, user_input: str) -> ChatResponse:
    entry = get_entry(agent_id)
    if entry is None:
        raise ValueError(f"agente desconhecido: {agent_id}")
    return await _post(f"{entry.url}/chat", {"thread_id": thread_id, "input": user_input})


async def proxy_resume(agent_id: str, thread_id: str, decisions: list[dict]) -> ChatResponse:
    entry = get_entry(agent_id)
    if entry is None:
        raise ValueError(f"agente desconhecido: {agent_id}")
    return await _post(f"{entry.url}/resume", {"thread_id": thread_id, "decisions": decisions})


async def proxy_history(agent_id: str, thread_id: str) -> HistoryResponse:
    entry = get_entry(agent_id)
    if entry is None:
        raise ValueError(f"agente desconhecido: {agent_id}")
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        resp = await client.get(f"{entry.url}/history/{thread_id}")
    resp.raise_for_status()
    return HistoryResponse.model_validate(resp.json())
