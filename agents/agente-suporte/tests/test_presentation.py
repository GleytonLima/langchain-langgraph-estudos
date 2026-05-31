"""present(): sugestões + status derivados do ESTADO REAL do domínio.

Função pura (sem LLM) — garante que as dicas de UI refletem o chamado de fato, não
regex no texto do modelo. É o contrato que o chassi só renderiza.
"""

from __future__ import annotations

from app.presentation import present
from contracts import PendingToolCall


def _ch(status="aberto", detalhes=None, titulo="Notebook não liga", cid="c1") -> dict:
    return {
        cid: {
            "id": cid,
            "titulo": titulo,
            "categoria_id": "C1",
            "prioridade": "alta",
            "status": status,
            "detalhes": detalhes or [],
        }
    }


def _fake_pending() -> list[PendingToolCall]:
    return [PendingToolCall(tool_call_id="c1", tool_name="fechar_chamado")]


def test_sem_chamado_status_em_andamento_sem_sugestoes():
    suggestions, session = present({}, [])
    assert session.status.label == "Em andamento"
    assert session.status.tone == "progress"
    assert suggestions == []


def test_pending_status_aguardando_voce_e_sem_sugestoes():
    suggestions, session = present(_ch(), _fake_pending())
    assert session.status.label == "Aguardando você"
    assert session.status.tone == "attention"
    assert suggestions == []


def test_aberto_sem_detalhes_so_sugere_adicionar():
    suggestions, session = present(_ch(), [])
    assert session.status.label == "Aberto"
    assert session.status.tone == "neutral"
    assert [s.label for s in suggestions] == ["Adicionar detalhe"]


def test_aberto_com_detalhes_sugere_fechar_primario():
    suggestions, session = present(_ch(detalhes=["reiniciei"]), [])
    assert session.status.tone == "neutral"
    assert suggestions[0].label == "Fechar chamado"
    assert suggestions[0].primary is True
    assert {s.label for s in suggestions} == {"Fechar chamado", "Adicionar detalhe"}


def test_fechado_status_sucesso_sem_sugestoes():
    suggestions, session = present(_ch(status="fechado", detalhes=["resolvido"]), [])
    assert session.status.label == "Fechado"
    assert session.status.tone == "success"
    assert suggestions == []


def test_titulo_vem_do_chamado():
    _, session = present(_ch(titulo="Sem acesso ao e-mail"), [])
    assert session.title == "Sem acesso ao e-mail"
