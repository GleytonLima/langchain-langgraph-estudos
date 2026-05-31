"""Dicas de UI que ESTE agente expõe ao chassi (opcional, mas recomendado).

O chassi é genérico: ele não conhece "chamado de TI". A cada turno ele só RENDERIZA
o que o agente devolve no ChatResponse:

  - suggestions: botões de PRÓXIMO PASSO (respostas rápidas)
  - session:     título + status da conversa p/ a lista lateral

Tudo aqui é derivado do ESTADO REAL do domínio (não de regex no texto do modelo),
então é exato e não quebra quando o agente reescreve uma frase.

Mesma regra de atalho do molde: só ofereça como suggestion AÇÕES QUE EXECUTAM
SOZINHAS, sem pedir dados adicionais (ex.: "Fechar chamado" basta; já há contexto).
"""

from __future__ import annotations

from contracts import PendingToolCall, SessionMeta, SessionStatus, Suggestion


def present(
    chamados: dict[str, dict], pending: list[PendingToolCall]
) -> tuple[list[Suggestion], SessionMeta]:
    """Sugestões de próximo passo + resumo da sessão para a conversa atual.

    `chamados` é o campo do ESTADO do grafo (lido pelo runtime via get_state) —
    portanto reflete o estado persistido, não um cache em memória.
    """
    ch = _chamado_da_conversa(chamados)
    return _suggestions(ch, pending), _session(ch, pending)


def _chamado_da_conversa(chamados: dict[str, dict]) -> dict | None:
    """O chamado da conversa (uma thread costuma ter um; pega o mais recente)."""
    return next(reversed(chamados.values()), None) if chamados else None


def _session(ch: dict | None, pending: list[PendingToolCall]) -> SessionMeta:
    if pending:  # há um card HITL aguardando decisão do usuário
        status = SessionStatus(label="Aguardando você", tone="attention")
    elif ch is None:  # conversa começou mas nada foi criado ainda
        status = SessionStatus(label="Em andamento", tone="progress")
    elif ch["status"] == "fechado":
        status = SessionStatus(label="Fechado", tone="success")
    else:  # chamado aberto, ainda editável
        status = SessionStatus(label="Aberto", tone="neutral")
    return SessionMeta(title=ch["titulo"] if ch else "", status=status)


def _suggestions(ch: dict | None, pending: list[PendingToolCall]) -> list[Suggestion]:
    # com HITL aberto, o card já conduz a tela -> não polui com sugestões
    if pending or ch is None or ch["status"] != "aberto":
        return []
    detalhar = Suggestion(label="Adicionar detalhe", message="Quero adicionar mais um detalhe")
    if ch["detalhes"]:  # já há contexto -> fechar é a ação recomendada
        return [
            Suggestion(
                label="Fechar chamado",
                message="Fechar o chamado",
                primary=True,
            ),
            detalhar,
        ]
    return [detalhar]  # sem detalhes ainda: só faz sentido detalhar
