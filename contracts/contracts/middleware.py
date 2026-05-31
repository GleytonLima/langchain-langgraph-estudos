"""Middlewares reutilizáveis de controle de fluxo para agentes `create_agent`.

GENÉRICOS: não conhecem domínio nenhum. Cada agente injeta sua política. São DOIS
middlewares pequenos, um por responsabilidade (em vez de um que faz as duas):

- `PreconditionMiddleware` — eixo POR-TOOL/ESTADO: "esta tool pode rodar dado o
  estado atual?". Recebe `preconditions = {tool: fn(state, args) -> str | None}`; a
  função lê o estado do grafo e devolve o MOTIVO do bloqueio (str) ou `None`.

- `SequentialTurnMiddleware` — eixo TEMPORAL: "uma ação irreversível exige turno
  próprio". Segura `sequential_tools` se já houve qualquer escrita (`write_tools`)
  desde a última mensagem do usuário. A MENSAGEM ao usuário é injetada via `announce`
  (callable do domínio) — o middleware não conhece wording nem rótulos de tela.

Estratégia comum (no `after_model`): reescreve a AIMessage removendo as tool calls
barradas. Como o LangGraph encerra o loop quando não há tool calls, o usuário lê a
orientação e a ação não roda. Liste estes middlewares DEPOIS do
HumanInTheLoopMiddleware para que seus `after_model` rodem ANTES (ordem inversa) —
assim o card HITL nem aparece para uma chamada bloqueada.

Importa langchain só quando usado; o pacote `contracts` em si continua pydantic puro.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

# (state, args) -> motivo do bloqueio (str) ou None se a tool pode rodar.
Precondition = Callable[[Any, dict], "str | None"]
# (nomes das tools seguradas) -> texto exibido ao usuário.
Announce = Callable[[list[str]], str]


def _last_ai_tool_calls(messages: list) -> AIMessage | None:
    """A última mensagem, se for uma AIMessage com tool calls (senão None)."""
    last = messages[-1] if messages else None
    if isinstance(last, AIMessage) and last.tool_calls:
        return last
    return None


def _reescreve(last: AIMessage, mantidas: list, avisos: list[str]) -> dict:
    """Substitui a AIMessage (mesmo id => o reducer troca no lugar) mantendo só as
    tool calls liberadas e acrescentando os avisos. Preserva o conteúdo já existente
    para que os middlewares componham entre si."""
    partes = [p for p in [last.content, *avisos] if p]
    return {"messages": [AIMessage(id=last.id, content="\n".join(partes), tool_calls=mantidas)]}


class PreconditionMiddleware(AgentMiddleware):
    """Barra tools cuja pré-condição (dado o estado) não está satisfeita."""

    def __init__(self, preconditions: Mapping[str, Precondition] | None = None) -> None:
        super().__init__()
        self.preconditions = dict(preconditions or {})

    def after_model(self, state, runtime):
        last = _last_ai_tool_calls(state.get("messages") or [])
        # Devolver None = "não mexe na mensagem": nada a fazer se o modelo não pediu tools.
        if last is None:
            return None

        # Para cada tool call pedida, a pré-condição (se houver) devolve um motivo de
        # bloqueio. Quem tem motivo é barrada (removida); o resto segue.
        tools_recebidas_mantidas: list = []   # passam e executam
        tools_recebidas_barradas: list = []   # pré-condição não satisfeita -> removidas
        motivos_do_bloqueio: list[str] = []
        for tc in last.tool_calls:
            check = self.preconditions.get(tc["name"])
            motivo = check(state, tc.get("args", {})) if check else None
            if motivo:
                tools_recebidas_barradas.append(tc)
                motivos_do_bloqueio.append(motivo)
            else:
                tools_recebidas_mantidas.append(tc)

        if not tools_recebidas_barradas:
            return None  # nenhuma barrada -> não interfere
        # Reescreve a AIMessage só com as mantidas + os motivos. Sem a tool call
        # barrada, o loop encerra e ela não roda.
        return _reescreve(last, tools_recebidas_mantidas, motivos_do_bloqueio)


class SequentialTurnMiddleware(AgentMiddleware):
    """Segura ações que exigem turno próprio quando já houve escrita no turno."""

    def __init__(
        self,
        *,
        write_tools: Iterable[str] = (),
        sequential_tools: Iterable[str] = (),
        announce: Announce | None = None,
    ) -> None:
        super().__init__()
        self.write_tools = set(write_tools)
        self.sequential_tools = set(sequential_tools)
        # default neutro; o domínio injeta a mensagem amigável (com seus rótulos).
        self.announce = announce or (lambda seguradas: "Ação segurada para o próximo passo.")

    def after_model(self, state, runtime):
        messages = state.get("messages") or []
        last = _last_ai_tool_calls(messages)
        # Nada a fazer (devolver None = "não mexe na mensagem") se o modelo não pediu
        # tools OU se ainda não houve escrita neste turno — sem escrita anterior, uma
        # ação sequencial pode rodar normalmente.
        if last is None or not self._houve_write(messages):
            return None

        # Separa as tool calls pedidas em dois grupos (ambos guardam o tool call):
        tools_recebidas_para_remover: list = []  # sequenciais -> seguradas p/ o próximo turno
        tools_recebidas_mantidas: list = []      # demais -> seguem e executam
        for tc in last.tool_calls:
            if tc["name"] in self.sequential_tools:
                tools_recebidas_para_remover.append(tc)
            else:
                tools_recebidas_mantidas.append(tc)

        if not tools_recebidas_para_remover:
            return None  # nada sequencial neste turno -> não interfere

        # Reescreve a AIMessage só com as mantidas + o aviso de "próximo passo".
        # Sem a tool call sequencial, o loop encerra e ela não roda agora.
        nomes_removidos = [tc["name"] for tc in tools_recebidas_para_remover]
        return _reescreve(last, tools_recebidas_mantidas, [self.announce(nomes_removidos)])

    def _houve_write(self, messages) -> bool:
        """Houve algum write neste turno (desde a última HumanMessage)?"""
        for m in reversed(messages):
            if isinstance(m, HumanMessage):
                break
            if isinstance(m, ToolMessage) and getattr(m, "name", None) in self.write_tools:
                return True
        return False
