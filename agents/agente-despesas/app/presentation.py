"""Dicas de UI que ESTE agente expõe ao chassi (opcional, mas recomendado).

O chassi é genérico: ele não conhece "relatório de despesa". A cada turno ele só
RENDERIZA o que o agente devolve no ChatResponse:

  - suggestions: botões de PRÓXIMO PASSO (respostas rápidas)
  - session:     título + status da conversa p/ a lista lateral

Tudo aqui é derivado do ESTADO REAL do domínio (não de regex no texto do modelo),
então é exato e não quebra quando o agente reescreve uma frase.

================================ PARA UM NOVO AGENTE ================================
Implemente `present(thread_id, pending)` lendo o SEU estado de domínio e devolva
`(suggestions, session)`. Não quer a feature? Devolva `([], SessionMeta())` — a UI
degrada graciosamente (sem botões, status neutro). É só isto: nenhuma regra de UI
vaza para o chassi.

DICA (atalhos / suggestions): só ofereça como atalho AÇÕES QUE EXECUTAM SOZINHAS,
sem pedir dados adicionais. O clique gera uma mensagem pronta e o agente já age.
  - BOM: "Enviar para aprovação" -> a mensagem "Enviar o relatório para aprovação"
    basta; não falta nenhum dado.
  - RUIM: "Adicionar item" -> gera "Quero adicionar outro item", mas aí o usuário
    AINDA precisa digitar descrição e valor. O atalho não economizou nada — só
    adicionou um passo. Ações com parâmetros obrigatórios não devem virar atalho
    (deixe o usuário digitar a frase completa, ou conduza via card HITL).
A regra prática: se depois do clique o usuário ainda tem que digitar, não é atalho.
====================================================================================
"""

from __future__ import annotations

from contracts import PendingToolCall, SessionMeta, SessionStatus, Suggestion


def present(
    relatorios: dict[str, dict], pending: list[PendingToolCall]
) -> tuple[list[Suggestion], SessionMeta]:
    """Sugestões de próximo passo + resumo da sessão para a conversa atual.

    `relatorios` é o campo do ESTADO do grafo (lido pelo runtime via get_state) —
    portanto reflete o estado persistido, não um cache em memória.
    """
    rel = _relatorio_da_conversa(relatorios)
    return _suggestions(rel, pending), _session(rel, pending)


def _relatorio_da_conversa(relatorios: dict[str, dict]) -> dict | None:
    """O relatório da conversa (uma thread costuma ter um; pega o mais recente)."""
    return next(reversed(relatorios.values()), None) if relatorios else None


def _session(rel: dict | None, pending: list[PendingToolCall]) -> SessionMeta:
    if pending:  # há um card HITL aguardando decisão do usuário
        status = SessionStatus(label="Aguardando você", tone="attention")
    elif rel is None:  # conversa começou mas nada foi criado ainda
        status = SessionStatus(label="Em andamento", tone="progress")
    elif rel["status"] == "enviado":
        status = SessionStatus(label="Enviado", tone="success")
    else:  # relatório aberto, ainda editável
        status = SessionStatus(label="Rascunho", tone="neutral")
    return SessionMeta(title=rel["titulo"] if rel else "", status=status)


def _suggestions(rel: dict | None, pending: list[PendingToolCall]) -> list[Suggestion]:
    # com HITL aberto, o card já conduz a tela -> não polui com sugestões
    if pending or rel is None or rel["status"] != "aberto":
        return []
    adicionar = Suggestion(label="Adicionar item", message="Quero adicionar outro item")
    if rel["itens"]:  # já dá para enviar -> envio é a ação recomendada
        return [
            Suggestion(
                label="Enviar para aprovação",
                message="Enviar o relatório para aprovação",
                primary=True,
            ),
            adicionar,
        ]
    return [adicionar]  # sem itens ainda: só faz sentido adicionar
