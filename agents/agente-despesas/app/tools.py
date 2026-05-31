"""Agente de exemplo: relatórios de despesa.

Demonstra os dois pontos centrais do projeto:

1. Anti-alucinação: cada tool tem argumentos tipados (Pydantic via @tool) e
   VALIDA o estado no início. Se a pré-condição não está satisfeita, retorna um
   erro claro em vez de seguir adiante. A ordem do fluxo simples
   (abrir -> adicionar item -> enviar) é garantida pelos próprios requisitos das
   tools, sem precisar de máquina de estado.

2. HITL: TODA escrita é marcada para interrupção no agent.py
   (HumanInTheLoopMiddleware). O usuário vê o que vai rodar e pode
   aprovar / editar os args / rejeitar no chassi antes de executar.

O "estado" do domínio (os relatórios) vive no ESTADO DO GRAFO — campo `relatorios`
no state_schema do agente (ver agent.py). Como o agente usa PostgresSaver, esse
estado é PERSISTIDO junto com as mensagens, pelo mesmo thread_id: sobrevive a
restart do processo e abre igual em outro dispositivo. Antes era um dict global em
memória (perdido a cada restart, invisível cross-device) — o atalho foi removido.

As tools de ESCRITA retornam `Command(update={"relatorios": {...}, "messages": [...]})`;
o reducer `merge_relatorios` faz o merge por id. As tools de LEITURA/validação leem
o estado via `InjectedState`. O ponto pedagógico continua: validação dentro da tool
+ isolamento por thread (agora dado pelo próprio checkpointer).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command


def merge_relatorios(
    left: dict[str, dict] | None, right: dict[str, dict] | None
) -> dict[str, dict]:
    """Reducer do campo `relatorios` no estado: faz merge por id (o novo vence)."""
    out = dict(left or {})
    out.update(right or {})
    return out


def _total(rel: dict) -> float:
    return sum(i["valor"] for i in rel["itens"])


# "API externa" de tipos de relatório (hardcoded p/ o estudo). Em produção viria
# de um serviço; o ponto pedagógico é a DEPENDÊNCIA de dados de fora + o de-para
# id<->nome, que aparece em 3 frentes: validação anti-alucinação (a tool só aceita
# um id do catálogo), associação no relatório (guarda o id), e edição na tela (o
# card HITL mostra um seletor com o nome, gravando o id).
_TIPOS_DESPESA = [
    {"id": "T1", "nome": "Viagem"},
    {"id": "T2", "nome": "Alimentação"},
    {"id": "T3", "nome": "Material de escritório"},
    {"id": "T4", "nome": "Hospedagem"},
]
_TIPOS_BY_ID = {t["id"]: t for t in _TIPOS_DESPESA}


def tipo_nome(tipo_id: str) -> str:
    """De-para id->nome (cai pro próprio id se desconhecido)."""
    t = _TIPOS_BY_ID.get(tipo_id)
    return t["nome"] if t else tipo_id


def _relatorios(state: Any) -> dict[str, dict]:
    """Mapa de relatórios do estado do grafo (a conversa atual)."""
    return (state.get("relatorios") if isinstance(state, dict) else {}) or {}


def motivo_bloqueio_envio(state: Any, args: dict) -> str | None:
    """Por que `enviar_para_aprovacao` NÃO pode rodar agora (ou None se pode).

    Mesma validação da tool, mas exposta para o guard de ordem (middleware) poder
    barrar uma chamada prematura/alucinada ANTES de pedir aprovação humana. Lê o
    estado do grafo (o middleware passa o state — não há mais dict global).
    """
    rid = args.get("relatorio_id")
    rel = _relatorios(state).get(rid) if rid else None
    if rel is None:
        return (
            f"Não existe um relatório com id {rid!r} nesta conversa. "
            "Abra um relatório com abrir_relatorio e adicione itens antes de enviar."
        )
    if rel["status"] != "aberto":
        return f"O relatório {rid} já está '{rel['status']}', não dá para enviar de novo."
    if not rel["itens"]:
        return f"O relatório {rid} ainda não tem itens. Adicione ao menos um item antes de enviar."
    return None


def motivo_bloqueio_abertura(state: Any, args: dict) -> str | None:
    """Por que `abrir_relatorio` NÃO pode rodar agora (ou None se pode).

    Mesma validação da tool, mas exposta ao guard para barrar uma abertura
    prematura/alucinada ANTES do card HITL — assim o modelo fraco, que tende a chamar
    `abrir_relatorio` sem ter os dados, não abre um card vazio (que, se aprovado, daria
    erro e entraria em loop de retry). O texto retornado é exibido AO USUÁRIO (o turno
    encerra sem tool call), então é escrito como o assistente pedindo a informação.
    """
    titulo = (args.get("titulo") or "").strip()
    tipo_id = args.get("tipo_id")
    if not titulo:
        return "Para abrir um relatório eu preciso do título. Qual nome você quer dar a ele?"
    if tipo_id not in _TIPOS_BY_ID:
        opcoes = ", ".join(t["nome"] for t in _TIPOS_DESPESA)
        return f"Qual o tipo do relatório? Escolha um destes: {opcoes}."
    return None


@tool
def listar_tipos() -> str:
    """Lista os tipos de relatório válidos (id e nome). Consulte ANTES de abrir um
    relatório para descobrir o tipo_id correto — NUNCA invente um id de tipo."""
    linhas = "; ".join(f"{t['id']}={t['nome']}" for t in _TIPOS_DESPESA)
    return f"Tipos disponíveis: {linhas}."


# As tools de escrita devolvem Command(update=...): além da mensagem (ToolMessage),
# atualizam o campo `relatorios` do estado — que o checkpointer persiste. O `name`
# do ToolMessage é setado à mão (o SequentialTurnMiddleware detecta "houve write" por ele).
@tool
def abrir_relatorio(
    titulo: str, tipo_id: str, tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command | str:
    """Cria um novo relatório de despesa de um dado tipo e retorna seu id.

    `tipo_id` deve ser um id válido do catálogo (use listar_tipos para descobrir).
    Se for inválido, retorna ERRO com as opções — nunca crie um tipo novo.
    """
    if tipo_id not in _TIPOS_BY_ID:
        opcoes = ", ".join(f"{t['id']} ({t['nome']})" for t in _TIPOS_DESPESA)
        return f"ERRO: tipo_id {tipo_id!r} inválido. Use um destes: {opcoes}."
    rid = uuid.uuid4().hex[:8]
    rel = {"id": rid, "titulo": titulo, "tipo_id": tipo_id, "status": "aberto", "itens": []}
    msg = f"Relatório '{titulo}' (tipo: {tipo_nome(tipo_id)}) criado com id={rid} (status=aberto)."
    return Command(
        update={
            "relatorios": {rid: rel},
            "messages": [ToolMessage(msg, tool_call_id=tool_call_id, name="abrir_relatorio")],
        }
    )


@tool
def adicionar_item(
    relatorio_id: str,
    descricao: str,
    valor: float,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command | str:
    """Adiciona um item de despesa a um relatório aberto."""
    rel = _relatorios(state).get(relatorio_id)
    if rel is None:
        return f"ERRO: relatório {relatorio_id} não existe. Abra um relatório antes."
    if rel["status"] != "aberto":
        return f"ERRO: relatório {relatorio_id} está '{rel['status']}', não aceita novos itens."
    if valor <= 0:
        return "ERRO: valor deve ser maior que zero."
    novo = {**rel, "itens": [*rel["itens"], {"descricao": descricao, "valor": valor}]}
    msg = f"Item '{descricao}' (R$ {valor:.2f}) adicionado. Total atual: R$ {_total(novo):.2f}."
    return Command(
        update={
            "relatorios": {relatorio_id: novo},
            "messages": [ToolMessage(msg, tool_call_id=tool_call_id, name="adicionar_item")],
        }
    )


@tool
def consultar_relatorio(relatorio_id: str, state: Annotated[dict, InjectedState]) -> str:
    """Consulta status, itens e total de um relatório (somente leitura)."""
    rel = _relatorios(state).get(relatorio_id)
    if rel is None:
        return f"ERRO: relatório {relatorio_id} não existe."
    itens = "; ".join(f"{i['descricao']} (R$ {i['valor']:.2f})" for i in rel["itens"]) or "nenhum item"
    return (
        f"Relatório {rel['id']} '{rel['titulo']}' | tipo: {tipo_nome(rel['tipo_id'])} | "
        f"status={rel['status']} | itens: {itens} | total: R$ {_total(rel):.2f}."
    )


@tool
def enviar_para_aprovacao(
    relatorio_id: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command | str:
    """Envia o relatório para aprovação financeira. AÇÃO SENSÍVEL (requer HITL)."""
    rel = _relatorios(state).get(relatorio_id)
    if rel is None:
        return f"ERRO: relatório {relatorio_id} não existe."
    if rel["status"] != "aberto":
        return f"ERRO: relatório {relatorio_id} já está '{rel['status']}'."
    if not rel["itens"]:
        return "ERRO: relatório sem itens. Adicione ao menos um item antes de enviar."
    enviado = {**rel, "status": "enviado"}
    msg = f"Relatório {relatorio_id} enviado para aprovação. Total: R$ {_total(enviado):.2f}."
    return Command(
        update={
            "relatorios": {relatorio_id: enviado},
            "messages": [ToolMessage(msg, tool_call_id=tool_call_id, name="enviar_para_aprovacao")],
        }
    )


# Nome amigável de cada tool (exibido no lugar do nome técnico). Fica na própria
# tool (metadata) -> a tool é a fonte única; o mapa abaixo é só derivado dela.
listar_tipos.metadata = {"label": "Listar tipos"}
abrir_relatorio.metadata = {"label": "Abrir relatório"}
adicionar_item.metadata = {"label": "Adicionar item"}
consultar_relatorio.metadata = {"label": "Consultar relatório"}
enviar_para_aprovacao.metadata = {"label": "Enviar para aprovação"}

TOOLS = [listar_tipos, abrir_relatorio, adicionar_item, consultar_relatorio, enviar_para_aprovacao]

# {nome_tecnico: nome_amigavel}, derivado do metadata das tools (DRY).
TOOL_LABELS = {t.name: (t.metadata or {}).get("label", t.name) for t in TOOLS}


def _tipo_options() -> list[dict]:
    """Catálogo no formato {value, label} p/ o seletor do card HITL."""
    return [{"value": t["id"], "label": t["nome"]} for t in _TIPOS_DESPESA]


# Args que são REFERÊNCIAS a entidades externas (id estável + nome amigável). O
# runtime injeta estas opções na tool call pendente; o front renderiza um seletor
# (mostra o nome, grava o id) -> o de-para se materializa na edição na tela.
# {nome_da_tool: {nome_do_arg: provider() -> [{value, label}]}}
FIELD_OPTIONS = {"abrir_relatorio": {"tipo_id": _tipo_options}}

# Labels amigáveis dos args no card HITL (evita expor nomes técnicos na UI).
FIELD_LABELS: dict[str, dict[str, str]] = {
    "abrir_relatorio": {"titulo": "Título", "tipo_id": "Tipo"},
    "adicionar_item": {
        "relatorio_id": "Relatório",
        "descricao": "Descrição",
        "valor": "Valor",
    },
    "enviar_para_aprovacao": {"relatorio_id": "Relatório"},
}

# Args que o usuário não deve editar (referências internas, ids de sistema, etc.).
FIELD_READONLY: dict[str, list[str]] = {
    "adicionar_item": ["relatorio_id"],
    "enviar_para_aprovacao": ["relatorio_id"],
}

# tools que ALTERAM estado (consultar_relatorio é leitura). Alimenta o
# SequentialTurnMiddleware (detecção de "já houve escrita no turno") e definem o que
# pede aprovação humana.
WRITE_TOOLS = ["abrir_relatorio", "adicionar_item", "enviar_para_aprovacao"]

# HITL: TODO write pede aprovação (approve/edit/reject) — o usuário vê o que vai
# rodar e pode editar os args antes de confirmar. Total controle.
HITL_TOOLS = WRITE_TOOLS

# SEQUENTIAL: knob independente do HITL. Estas exigem TURNO PRÓPRIO (não encadeiam
# após outra escrita no mesmo turno). Aqui só o envio (irreversível). Outros times
# escolhem: confirmar tudo -> HITL; forçar passo isolado p/ ação crítica -> aqui.
SEQUENTIAL_TOOLS = ["enviar_para_aprovacao"]
