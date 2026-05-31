"""Fixtures compartilhadas dos testes do agente-despesas.

Fica na raiz do projeto (ao lado de `app/`) para que o pytest insira este
diretório no sys.path — assim `import app...` funciona nos testes.

A LLM é DUBLADA: um modelo roteirizado devolve AIMessages na ordem definida pelo
teste. Combinado com um checkpointer em memória, isso roda os ciclos chat->resume
ponta a ponta sem LM Studio nem Postgres, de forma determinística.
"""

from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langgraph.checkpoint.memory import MemorySaver

from app.agent import build_agent


class ScriptedModel(GenericFakeChatModel):
    """Modelo dublê: devolve as AIMessages roteirizadas, na ordem.

    `create_agent` chama `bind_tools` no modelo; o fake o ignora (não precisa de
    tools reais — as tool calls já vêm prontas em cada AIMessage do roteiro).
    """

    def bind_tools(self, tools=None, **kwargs):  # noqa: ARG002
        return self


def make_agent(script: list):
    """Agente com a fiação de produção, mas modelo dublê + checkpointer em memória."""
    return build_agent(ScriptedModel(messages=iter(script)), MemorySaver())


@pytest.fixture
def use_agent(monkeypatch):
    """Faz run_chat/run_resume/run_history usarem um agente dublê roteirizado.

    Devolve uma função `install(script)` que injeta o agente e o retorna.
    """

    def install(script: list):
        agent = make_agent(script)
        import app.runtime as rt

        monkeypatch.setattr(rt, "get_agent", lambda: agent)
        return agent

    return install
