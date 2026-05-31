"""present(): sugestões + status derivados do ESTADO REAL do domínio.

Função pura (sem LLM) — garante que as dicas de UI refletem o relatório de fato,
não regex no texto do modelo. É o contrato que o chassi só renderiza.

present() recebe o mapa `relatorios` (campo do estado do grafo) + as tool calls
pendentes. Aqui montamos esse mapa direto, do jeito que o runtime o leria do estado.
"""

from __future__ import annotations

from app.presentation import present
from contracts import PendingToolCall


def _rel(status="aberto", itens=None, titulo="Viagem SP", rid="r1") -> dict:
    return {rid: {"id": rid, "titulo": titulo, "tipo_id": "T1", "status": status, "itens": itens or []}}


def _fake_pending() -> list[PendingToolCall]:
    return [PendingToolCall(tool_call_id="c1", tool_name="enviar_para_aprovacao")]


def test_sem_relatorio_status_em_andamento_sem_sugestoes():
    suggestions, session = present({}, [])
    assert session.status.label == "Em andamento"
    assert session.status.tone == "progress"
    assert suggestions == []


def test_pending_status_aguardando_voce_e_sem_sugestoes():
    suggestions, session = present(_rel(), _fake_pending())
    assert session.status.label == "Aguardando você"
    assert session.status.tone == "attention"
    assert suggestions == []


def test_aberto_sem_itens_so_sugere_adicionar():
    suggestions, session = present(_rel(), [])
    assert session.status.label == "Rascunho"
    assert session.status.tone == "neutral"
    assert [s.label for s in suggestions] == ["Adicionar item"]


def test_aberto_com_itens_sugere_enviar_primario():
    suggestions, session = present(_rel(itens=[{"descricao": "Táxi", "valor": 45}]), [])
    assert session.status.tone == "neutral"
    assert suggestions[0].label == "Enviar para aprovação"
    assert suggestions[0].primary is True
    assert {s.label for s in suggestions} == {"Enviar para aprovação", "Adicionar item"}


def test_enviado_status_sucesso_sem_sugestoes():
    suggestions, session = present(
        _rel(status="enviado", itens=[{"descricao": "Táxi", "valor": 45}]), []
    )
    assert session.status.label == "Enviado"
    assert session.status.tone == "success"
    assert suggestions == []


def test_titulo_vem_do_relatorio():
    _, session = present(_rel(titulo="Viagem SP"), [])
    assert session.title == "Viagem SP"
