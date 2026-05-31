"""Monta o agente com create_agent (LangChain v1).

- checkpointer Postgres -> permite continuar a conversa de onde parou (thread_id).
- HumanInTheLoopMiddleware -> interrompe antes das tools sensíveis (HITL).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from contracts import Manifest
from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware, ToolCallLimitMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from contracts.middleware import PreconditionMiddleware, SequentialTurnMiddleware
from .llm import get_llm
from .settings import settings
from .tools import (
    HITL_TOOLS,
    SEQUENTIAL_TOOLS,
    TOOL_LABELS,
    TOOLS,
    WRITE_TOOLS,
    merge_chamados,
    motivo_bloqueio_abertura,
    motivo_bloqueio_fechamento,
)

AGENT_ID = "agente-suporte"

# Trava anti-loop por turno (run = uma invocação /chat). Modelo fraco às vezes
# fica repetindo tool calls; o fluxo legítimo de um turno faz poucas (listar +
# abrir, etc.), então 10 dá folga e ainda corta loops. exit_behavior padrão
# ("continue"): ao estourar, a tool é bloqueada e o agente encerra com texto —
# sem exceção (evita o NotImplementedError do "end" com tool calls paralelas).
TOOL_CALL_RUN_LIMIT = 10


def _anuncia_proximo_passo(seguradas: list[str]) -> str:
    """Wording (de domínio/UX) da ação segurada para o próximo turno. Injetado no
    SequentialTurnMiddleware — o middleware não conhece rótulos nem texto de tela."""
    proximos = ", ".join(TOOL_LABELS.get(n, n) for n in seguradas)
    return f"Pronto até aqui. Quando quiser, o próximo passo é: {proximos}. É só confirmar."


class ChamadoState(AgentState):
    """Estado do agente = AgentState (mensagens) + os chamados do domínio.

    Igual ao molde: guardar os chamados aqui faz o checkpointer Postgres
    PERSISTI-LOS junto com as mensagens, pelo mesmo thread_id. O reducer faz merge
    por id quando uma tool devolve Command(update=...).
    """

    chamados: Annotated[dict[str, dict], merge_chamados]


SYSTEM_PROMPT = (
    "Você é um assistente de suporte de TI (helpdesk). Ajude o usuário a abrir um "
    "chamado, registrar detalhes e fechá-lo. Use SEMPRE as tools para qualquer ação "
    "— nunca invente ids, categorias, prioridades ou status. Para abrir um chamado "
    "é obrigatório uma categoria e uma prioridade: chame listar_categorias para "
    "descobrir as categorias válidas e passe o categoria_id correto (nunca invente "
    "um id). A prioridade deve ser baixa, media ou alta. NUNCA presuma título, "
    "categoria ou prioridade: pergunte ao usuário os dados que faltam antes de "
    "chamar abrir_chamado — não escolha valores por conta própria. Se uma tool "
    "retornar ERRO, explique ao usuário e peça a informação que falta. Respeite a "
    "ordem: abrir_chamado -> adicionar_detalhe -> fechar_chamado."
)


def manifest() -> Manifest:
    return Manifest(
        agent_id=AGENT_ID,
        name="Suporte de TI",
        description=(
            "Abra chamados de TI e acompanhe o atendimento."
        ),
        capabilities=[
            "abrir chamado de suporte de TI",
            "definir categoria e prioridade do chamado",
            "registrar detalhes/andamento em um chamado",
            "fechar (resolver) um chamado",
            "consultar status de um chamado",
        ],
        examples=[
            "Meu notebook não liga, quero abrir um chamado",
            "Adiciona um detalhe: já tentei reiniciar e não resolveu",
            "Pode fechar o chamado, foi resolvido",
        ],
        hitl_tools=HITL_TOOLS,
    )


@lru_cache
def _checkpointer() -> AsyncPostgresSaver:
    # open=False: o pool async deve ser aberto DENTRO do event loop (em setup,
    # chamado no warmup) — abrir no construtor, fora do loop, emite warning.
    pool = AsyncConnectionPool(
        conninfo=settings.database_url,
        max_size=10,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0},
    )
    return AsyncPostgresSaver(pool)


async def setup_checkpointer() -> None:
    """Abre o pool e cria as tabelas de checkpoint. Chamado no warmup (no loop)."""
    cp = _checkpointer()
    await cp.conn.open()
    await cp.setup()


def build_agent(model, checkpointer):
    """Fiação do agente (modelo + checkpointer injetados).

    Fonte única da composição (middleware/tools/prompt). Produção usa a LLM real +
    Postgres; testes injetam um modelo dublê + checkpointer em memória, exercitando
    exatamente a mesma configuração.
    """
    return create_agent(
        model=model,
        tools=TOOLS,
        state_schema=ChamadoState,
        system_prompt=SYSTEM_PROMPT,
        # after_model roda na ORDEM INVERSA da lista. Por isso os guards vêm DEPOIS
        # do HITL: seus after_model executam ANTES, barrando a ação antes do card de
        # aprovação aparecer. Cada guard tem UMA responsabilidade.
        middleware=[
            # Trava anti-loop p/ modelo fraco: corta repetição de tool calls no turno.
            ToolCallLimitMiddleware(run_limit=TOOL_CALL_RUN_LIMIT),
            HumanInTheLoopMiddleware(interrupt_on={t: True for t in HITL_TOOLS}),
            # só o fechamento (ação final) exige turno próprio; abrir+detalhar encadeiam.
            SequentialTurnMiddleware(
                write_tools=WRITE_TOOLS,
                sequential_tools=SEQUENTIAL_TOOLS,
                announce=_anuncia_proximo_passo,
            ),
            # pré-condições de domínio: abertura só com título + categoria + prioridade
            # válidos (barra a abertura prematura do modelo fraco antes do card); fechar
            # só com chamado existente/aberto.
            PreconditionMiddleware(
                preconditions={
                    "abrir_chamado": motivo_bloqueio_abertura,
                    "fechar_chamado": motivo_bloqueio_fechamento,
                }
            ),
        ],
        checkpointer=checkpointer,
    )


@lru_cache
def get_agent():
    return build_agent(get_llm(), _checkpointer())
