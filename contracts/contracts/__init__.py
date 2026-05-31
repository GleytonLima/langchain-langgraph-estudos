"""Protocolo compartilhado entre o chassi e os agentes.

Tudo que trafega entre os servicos passa por estes modelos Pydantic. Centralizar
aqui mantem o contrato unico (DRY) e evita divergencia de formato entre os servicos.
A comunicacao e sincrona (request/response JSON), sem streaming/SSE.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Manifesto do agente (consumido pelo registry/roteador do chassi)
# ---------------------------------------------------------------------------


class Manifest(BaseModel):
    agent_id: str
    name: str
    description: str
    capabilities: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    # nomes das tools que exigem aprovacao humana (HITL)
    hitl_tools: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Chat (chassi <-> agente) - sincrono, request/response
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    thread_id: str
    input: str


class ChatStatus(str, Enum):
    final = "final"          # turno concluido: ha uma resposta do assistant
    interrupt = "interrupt"  # HITL: precisa de aprovacao antes de rodar a(s) tool(s)


class FieldOption(BaseModel):
    """Opção de um arg que referencia entidade externa (de-para id<->nome)."""

    value: str  # id estável (gravado)
    label: str  # nome amigável (exibido no seletor)


class PendingToolCall(BaseModel):
    tool_call_id: str
    tool_name: str  # nome técnico (usado internamente)
    tool_label: str = ""  # nome amigável p/ exibição; cai p/ tool_name se vazio
    args: dict[str, Any] = Field(default_factory=dict)
    # args que são referências a entidades externas -> o front mostra um seletor
    # (label visível, value gravado). {nome_do_arg: [FieldOption, ...]}
    field_options: dict[str, list[FieldOption]] = Field(default_factory=dict)
    # labels amigáveis dos args (ex.: descricao -> "Descrição")
    field_labels: dict[str, str] = Field(default_factory=dict)
    # args que nunca podem ser editados no card HITL (ex.: ids internos)
    readonly_fields: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Dicas de UI que o AGENTE expõe ao chassi (opcional). O chassi é genérico: ele
# NÃO conhece o domínio do agente, apenas RENDERIZA o que vier aqui. Assim a
# experiência (próximos passos, status na lista) é extensível a qualquer agente
# sem nenhuma regra de domínio no frontend. Um novo time só precisa preencher
# estes campos no ChatResponse; se não preencher, a UI degrada graciosamente.
# ---------------------------------------------------------------------------


class Suggestion(BaseModel):
    """Botão de PRÓXIMO PASSO oferecido ao usuário (resposta rápida).

    Quem decide quando/se sugerir é o agente. Ao clicar, o chassi envia `message`
    ao agente como se o usuário tivesse digitado.
    """

    label: str             # texto do botão (ex.: "Enviar para aprovação")
    message: str           # o que vai pro agente ao clicar
    primary: bool = False  # destaque visual (ação recomendada)


class SessionStatus(BaseModel):
    """Status da conversa na lista lateral. Agnóstico de domínio: o agente diz o
    RÓTULO (vocabulário dele) + um TOM genérico que o chassi traduz em cor/ícone.
    """

    label: str = ""  # texto exibido (ex.: "Rascunho", "Enviado")
    # neutral: sem destaque | progress: em andamento | attention: precisa do
    # usuário | success: concluído. O chassi mapeia tom -> cor/ícone (não o rótulo).
    tone: Literal["neutral", "progress", "attention", "success"] = "neutral"


class SessionMeta(BaseModel):
    """Resumo de uma conversa p/ a sidebar do chassi (preenchido pelo agente)."""

    title: str = ""  # título curto (ex.: "Viagem SP"); vazio -> chassi usa fallback
    status: SessionStatus = Field(default_factory=SessionStatus)


class ChatResponse(BaseModel):
    """Resposta sincrona de um turno (request/response, sem streaming)."""

    status: ChatStatus
    text: str | None = None  # mensagem final do assistant (quando status=final)
    tool_calls: list[PendingToolCall] = Field(default_factory=list)  # quando interrupt
    # transcript completo da thread — mesmo formato do /history (paridade ao vivo vs reopen)
    messages: list[HistoryMessage] = Field(default_factory=list)
    # dicas de UI (opcionais) — ver Suggestion/SessionMeta
    suggestions: list[Suggestion] = Field(default_factory=list)
    session: SessionMeta = Field(default_factory=SessionMeta)


# ---------------------------------------------------------------------------
# HITL: retomada apos interrupcao
# ---------------------------------------------------------------------------


class ToolDecision(BaseModel):
    tool_call_id: str
    action: Literal["approve", "reject"]
    # opcional: argumentos editados pelo usuario antes de aprovar
    edited_args: dict[str, Any] | None = None


class ResumeRequest(BaseModel):
    thread_id: str
    decisions: list[ToolDecision]


# ---------------------------------------------------------------------------
# Historico de uma conversa (transcript) - para reabrir e continuar
# ---------------------------------------------------------------------------


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class HistoryResponse(BaseModel):
    """Transcript de uma thread + eventual HITL pendente (se parou interrompida)."""

    messages: list[HistoryMessage] = Field(default_factory=list)
    pending: list[PendingToolCall] = Field(default_factory=list)
    # mesmas dicas de UI do ChatResponse — paridade ao reabrir a conversa
    suggestions: list[Suggestion] = Field(default_factory=list)
    session: SessionMeta = Field(default_factory=SessionMeta)


# ---------------------------------------------------------------------------
# Roteamento do chassi (qual agente consegue responder) - saida anti-alucinacao
# ---------------------------------------------------------------------------


class AgentMatch(BaseModel):
    agent_id: str = Field(description="id exato do agente, vindo do registry")
    score: float = Field(ge=0, le=1, description="confianca de que responde bem")
    motivo: str = Field(description="por que este agente serve (ou nao)")


class RouteDecision(BaseModel):
    """Saida estruturada do roteador. Forca a LLM a so citar agentes do registry."""

    agents: list[AgentMatch] = Field(default_factory=list)
