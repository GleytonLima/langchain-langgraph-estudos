from contextlib import asynccontextmanager

from contracts import ChatRequest, ChatResponse, HistoryResponse, Manifest, ResumeRequest
from fastapi import FastAPI

from .agent import manifest
from .runtime import run_chat, run_history, run_resume, warmup


@asynccontextmanager
async def lifespan(app: FastAPI):
    # aquece o agente no boot (ver runtime.warmup) p/ a 1ª mensagem não pagar
    # o custo de inicialização. Best-effort: se falhar, segue a inicialização
    # preguiçosa no primeiro /chat.
    try:
        await warmup()
    except Exception:
        pass
    yield


app = FastAPI(title="agente-despesas", lifespan=lifespan)


@app.get("/manifest", response_model=Manifest)
def get_manifest() -> Manifest:
    return manifest()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    return await run_chat(req.thread_id, req.input)


@app.post("/resume", response_model=ChatResponse)
async def resume(req: ResumeRequest) -> ChatResponse:
    return await run_resume(req.thread_id, req.decisions)


@app.get("/history/{thread_id}", response_model=HistoryResponse)
async def history(thread_id: str) -> HistoryResponse:
    return await run_history(thread_id)
