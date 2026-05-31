from contextlib import asynccontextmanager

from contracts import ChatResponse, HistoryResponse, RouteDecision
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

from .proxy import proxy_chat, proxy_history, proxy_resume
from .registry import list_entries
from .router_llm import route
from .sessions import (
    create_session,
    get_session,
    list_sessions,
    setup as sessions_setup,
    update_session_meta,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # abre o pool Postgres e cria a tabela de sessões no boot (dentro do event
    # loop). Best-effort: se a infra não subir, segue — o erro reaparece no 1º uso.
    try:
        await sessions_setup()
    except Exception:
        pass
    yield


app = FastAPI(title="chassi", lifespan=lifespan)

# frontend Angular (microfrontend) chama o chassi direto do browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- requests ----
class RouteRequest(BaseModel):
    question: str


class CreateSessionRequest(BaseModel):
    agent_id: str  # inicia já fixado num agente específico


class ChatRequest(BaseModel):
    input: str


class ResumeRequest(BaseModel):
    decisions: list[dict]


# ---- endpoints ----
@app.get("/api/agents")
async def agents():
    return [
        {"id": e.id, "url": e.url, "manifest": e.manifest.model_dump() if e.manifest else None}
        for e in await list_entries()
    ]


@app.post("/api/route", response_model=RouteDecision)
async def api_route(req: RouteRequest) -> RouteDecision:
    return await route(req.question)


@app.post("/api/sessions")
async def api_create_session(req: CreateSessionRequest):
    s = await create_session(req.agent_id)
    return s.model_dump()


@app.get("/api/sessions")
async def api_list_sessions():
    return [s.model_dump() for s in await list_sessions()]


@app.get("/api/sessions/{session_id}")
async def api_get_session(session_id: str):
    s = await get_session(session_id)
    if s is None:
        raise HTTPException(404, "sessão não encontrada")
    return s.model_dump()


async def _require_session(session_id: str):
    s = await get_session(session_id)
    if s is None:
        raise HTTPException(404, "sessão não encontrada")
    return s


async def _proxy_agent(coro):
    """Traduz falhas de rede/timeout do agente em HTTP errors legíveis."""
    try:
        return await coro
    except httpx.TimeoutException:
        raise HTTPException(
            504,
            "O agente demorou demais para responder. Tente novamente em instantes.",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"Erro no agente ({exc.response.status_code}).")
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Não foi possível contactar o agente: {exc}")
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/sessions/{session_id}/history", response_model=HistoryResponse)
async def api_history(session_id: str) -> HistoryResponse:
    s = await _require_session(session_id)
    return await _proxy_agent(proxy_history(s.agent_id, s.thread_id))


async def _persist_meta(session_id: str, resp: ChatResponse, fallback: str = "") -> None:
    """Salva o metadado de exibição da sessão a partir do `SessionMeta` do agente.

    Mantém o título pronto na listagem (sem localStorage no frontend). `fallback` (o
    input do usuário) vira título quando o agente ainda não tem um (ex.: antes de criar
    o relatório). O chassi trata título/status como strings opacas — segue agnóstico.
    """
    meta = resp.session  # sempre presente (SessionMeta com default_factory)
    title = (meta.title or "").strip() or fallback.strip()[:60]
    await update_session_meta(session_id, title, meta.status.label, meta.status.tone)


@app.post("/api/sessions/{session_id}/chat", response_model=ChatResponse)
async def api_chat(session_id: str, req: ChatRequest) -> ChatResponse:
    s = await _require_session(session_id)
    resp = await _proxy_agent(proxy_chat(s.agent_id, s.thread_id, req.input))
    await _persist_meta(session_id, resp, fallback=req.input)
    return resp


@app.post("/api/sessions/{session_id}/resume", response_model=ChatResponse)
async def api_resume(session_id: str, req: ResumeRequest) -> ChatResponse:
    s = await _require_session(session_id)
    resp = await _proxy_agent(proxy_resume(s.agent_id, s.thread_id, req.decisions))
    await _persist_meta(session_id, resp)
    return resp
