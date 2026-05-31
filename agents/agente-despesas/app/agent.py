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
    merge_relatorios,
    motivo_bloqueio_abertura,
    motivo_bloqueio_envio,
)

AGENT_ID = "agente-despesas"

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


class DespesaState(AgentState):
    """Estado do agente = AgentState (mensagens) + os relatórios do domínio.

    Guardar os relatórios aqui (em vez de um dict global em memória) faz o
    checkpointer Postgres PERSISTI-LOS junto com as mensagens, pelo mesmo
    thread_id: a conversa reabre completa após restart e em outro dispositivo.
    O reducer faz merge por id quando uma tool devolve Command(update=...).
    """

    relatorios: Annotated[dict[str, dict], merge_relatorios]

SYSTEM_PROMPT = (
    "Você é um assistente de relatórios de despesa. Ajude o usuário a abrir um "
    "relatório, adicionar itens e enviá-lo para aprovação. Use SEMPRE as tools "
    "para qualquer ação — nunca invente ids, totais, tipos ou status. Para abrir "
    "um relatório é obrigatório um tipo: chame listar_tipos para descobrir os "
    "tipos válidos e passe o tipo_id correto (nunca invente um id de tipo). NUNCA "
    "presuma título ou tipo: pergunte ao usuário os dados que faltam antes de chamar "
    "abrir_relatorio — não escolha valores por conta própria. Se uma tool retornar "
    "ERRO, explique ao usuário e peça a informação que falta. Respeite a ordem: "
    "abrir_relatorio -> adicionar_item -> enviar_para_aprovacao."
)


def manifest() -> Manifest:
    return Manifest(
        agent_id=AGENT_ID,
        name="Agente de Despesas",
        description=(
            "Crie relatórios de despesas e envie para aprovação financeira."
        ),
        capabilities=[
            "abrir relatório de despesa",
            "adicionar itens de despesa a um relatório",
            "enviar relatório para aprovação",
            "consultar total de um relatório",
        ],
        examples=[
            "Quero abrir um relatório de despesas da viagem a SP",
            "Adiciona um táxi de 45 reais no relatório",
            "Pode enviar o relatório pra aprovação",
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
        state_schema=DespesaState,
        system_prompt=SYSTEM_PROMPT,
        # after_model roda na ORDEM INVERSA da lista. Por isso os guards vêm DEPOIS
        # do HITL: seus after_model executam ANTES, barrando a ação antes do card de
        # aprovação aparecer. Cada guard tem UMA responsabilidade.
        middleware=[
            # Trava anti-loop p/ modelo fraco: corta repetição de tool calls no turno.
            ToolCallLimitMiddleware(run_limit=TOOL_CALL_RUN_LIMIT),
            HumanInTheLoopMiddleware(interrupt_on={t: True for t in HITL_TOOLS}),
            # só o envio (irreversível) exige turno próprio; abrir+adicionar encadeiam.
            SequentialTurnMiddleware(
                write_tools=WRITE_TOOLS,
                sequential_tools=SEQUENTIAL_TOOLS,
                announce=_anuncia_proximo_passo,
            ),
            # pré-condições de domínio: abertura só com título + tipo válido (barra a
            # abertura prematura do modelo fraco antes do card); envio só com relatório
            # aberto e com item.
            PreconditionMiddleware(
                preconditions={
                    "abrir_relatorio": motivo_bloqueio_abertura,
                    "enviar_para_aprovacao": motivo_bloqueio_envio,
                }
            ),
        ],
        checkpointer=checkpointer,
    )


@lru_cache
def get_agent():
    return build_agent(get_llm(), _checkpointer())
