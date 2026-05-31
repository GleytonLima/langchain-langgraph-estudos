"""Agente de suporte: chamados de TI (helpdesk).

É o SEGUNDO agente do projeto — mesmo molde do agente-despesas, mas escolhido de
propósito para exercitar o que o exemplo NÃO usa, provando que o chassi/frontend
são genéricos de verdade:

1. DOIS seletores na MESMA tool. `abrir_chamado` expõe `field_options` para dois
   args ao mesmo tempo: `categoria_id` (de-para de ENTIDADE: id estável ↔ nome) e
   `prioridade` (de-para de ENUM: código ↔ rótulo legível). O card HITL renderiza
   os dois selects sem o chassi saber o que é "chamado" ou "prioridade".

2. De-para de ENUM (não só de entidade). No exemplo o seletor era um catálogo de
   entidades (tipos de despesa). Aqui mostramos que o mesmo mecanismo serve para um
   ENUM fechado de domínio (baixa/media/alta) — o modelo só pode citar um valor
   válido, e a UI mostra o rótulo bonito gravando o código.

O resto segue idêntico ao molde: estado no grafo (persistido pelo checkpointer por
thread_id), tools de escrita devolvendo `Command(update=...)`, validação dentro da
tool (anti-alucinação) e HITL em toda escrita.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command


def merge_chamados(
    left: dict[str, dict] | None, right: dict[str, dict] | None
) -> dict[str, dict]:
    """Reducer do campo `chamados` no estado: faz merge por id (o novo vence)."""
    out = dict(left or {})
    out.update(right or {})
    return out


# "API externa" de categorias (hardcoded p/ o estudo). É um de-para de ENTIDADE:
# id estável + nome amigável. A tool só aceita um id do catálogo (anti-alucinação),
# guarda o id no chamado e o card HITL mostra um seletor (nome visível, id gravado).
_CATEGORIAS = [
    {"id": "C1", "nome": "Hardware"},
    {"id": "C2", "nome": "Software"},
    {"id": "C3", "nome": "Rede"},
    {"id": "C4", "nome": "Acesso / Senha"},
]
_CATEGORIAS_BY_ID = {c["id"]: c for c in _CATEGORIAS}

# ENUM fechado de prioridade: código (gravado) ↔ rótulo (exibido). Diferente do
# catálogo de categorias, não vem de "fora" — é uma regra do domínio. Mesmo
# mecanismo de field_options serve para os dois.
_PRIORIDADES = {"baixa": "Baixa", "media": "Média", "alta": "Alta"}


def categoria_nome(categoria_id: str) -> str:
    """De-para id->nome da categoria (cai pro próprio id se desconhecido)."""
    c = _CATEGORIAS_BY_ID.get(categoria_id)
    return c["nome"] if c else categoria_id


def prioridade_nome(prioridade: str) -> str:
    """De-para código->rótulo da prioridade (cai pro próprio código se desconhecido)."""
    return _PRIORIDADES.get(prioridade, prioridade)


def _chamados(state: Any) -> dict[str, dict]:
    """Mapa de chamados do estado do grafo (a conversa atual)."""
    return (state.get("chamados") if isinstance(state, dict) else {}) or {}


def motivo_bloqueio_fechamento(state: Any, args: dict) -> str | None:
    """Por que `fechar_chamado` NÃO pode rodar agora (ou None se pode).

    Mesma validação da tool, exposta ao guard de ordem (middleware) para barrar um
    fechamento prematuro/alucinado ANTES de pedir aprovação humana. Lê o estado do
    grafo (o middleware passa o state).
    """
    cid = args.get("chamado_id")
    ch = _chamados(state).get(cid) if cid else None
    if ch is None:
        return (
            f"Não existe um chamado com id {cid!r} nesta conversa. "
            "Abra um chamado com abrir_chamado e registre ao menos um detalhe antes de fechar."
        )
    if ch["status"] != "aberto":
        return f"O chamado {cid} já está '{ch['status']}', não dá para fechar de novo."
    if not ch["detalhes"]:
        return f"O chamado {cid} ainda não tem nenhum detalhe. Registre ao menos um antes de fechar."
    return None


def motivo_bloqueio_abertura(state: Any, args: dict) -> str | None:
    """Por que `abrir_chamado` NÃO pode rodar agora (ou None se pode).

    Mesma validação da tool, exposta ao guard para barrar uma abertura
    prematura/alucinada ANTES do card HITL — o modelo fraco tende a chamar
    `abrir_chamado` sem ter os dados, gerando um card que, se aprovado, dá erro e
    entra em loop de retry. O texto retornado é exibido AO USUÁRIO (o turno encerra sem
    tool call), então é escrito como o assistente pedindo a informação.
    """
    titulo = (args.get("titulo") or "").strip()
    categoria_id = args.get("categoria_id")
    prioridade = args.get("prioridade")
    if not titulo:
        return "Para abrir um chamado eu preciso do título. Qual é o problema, em poucas palavras?"
    if categoria_id not in _CATEGORIAS_BY_ID:
        opcoes = ", ".join(c["nome"] for c in _CATEGORIAS)
        return f"Qual a categoria do chamado? Escolha uma destas: {opcoes}."
    if prioridade not in _PRIORIDADES:
        opcoes = ", ".join(_PRIORIDADES.values())
        return f"Qual a prioridade do chamado? Escolha uma destas: {opcoes}."
    return None


@tool
def listar_categorias() -> str:
    """Lista as categorias de chamado válidas (id e nome). Consulte ANTES de abrir
    um chamado para descobrir o categoria_id correto — NUNCA invente um id."""
    linhas = "; ".join(f"{c['id']}={c['nome']}" for c in _CATEGORIAS)
    return f"Categorias disponíveis: {linhas}."


# As tools de escrita devolvem Command(update=...): além da mensagem (ToolMessage),
# atualizam o campo `chamados` do estado — que o checkpointer persiste. O `name` do
# ToolMessage é setado à mão (o SequentialTurnMiddleware detecta "houve write" por ele).
@tool
def abrir_chamado(
    titulo: str,
    categoria_id: str,
    prioridade: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command | str:
    """Abre um novo chamado de suporte e retorna seu id.

    `categoria_id` deve ser um id válido do catálogo (use listar_categorias).
    `prioridade` deve ser um destes: baixa, media, alta. Valores inválidos retornam
    ERRO com as opções — nunca invente uma categoria ou prioridade.
    """
    if categoria_id not in _CATEGORIAS_BY_ID:
        opcoes = ", ".join(f"{c['id']} ({c['nome']})" for c in _CATEGORIAS)
        return f"ERRO: categoria_id {categoria_id!r} inválida. Use uma destas: {opcoes}."
    if prioridade not in _PRIORIDADES:
        opcoes = ", ".join(f"{k} ({v})" for k, v in _PRIORIDADES.items())
        return f"ERRO: prioridade {prioridade!r} inválida. Use uma destas: {opcoes}."
    cid = uuid.uuid4().hex[:8]
    ch = {
        "id": cid,
        "titulo": titulo,
        "categoria_id": categoria_id,
        "prioridade": prioridade,
        "status": "aberto",
        "detalhes": [],
    }
    msg = (
        f"Chamado '{titulo}' (categoria: {categoria_nome(categoria_id)}, "
        f"prioridade: {prioridade_nome(prioridade)}) aberto com id={cid} (status=aberto)."
    )
    return Command(
        update={
            "chamados": {cid: ch},
            "messages": [ToolMessage(msg, tool_call_id=tool_call_id, name="abrir_chamado")],
        }
    )


@tool
def adicionar_detalhe(
    chamado_id: str,
    texto: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command | str:
    """Registra um detalhe/andamento em um chamado aberto."""
    ch = _chamados(state).get(chamado_id)
    if ch is None:
        return f"ERRO: chamado {chamado_id} não existe. Abra um chamado antes."
    if ch["status"] != "aberto":
        return f"ERRO: chamado {chamado_id} está '{ch['status']}', não aceita novos detalhes."
    if not texto.strip():
        return "ERRO: o detalhe não pode ser vazio."
    novo = {**ch, "detalhes": [*ch["detalhes"], texto]}
    msg = f"Detalhe registrado no chamado {chamado_id}. Total de detalhes: {len(novo['detalhes'])}."
    return Command(
        update={
            "chamados": {chamado_id: novo},
            "messages": [ToolMessage(msg, tool_call_id=tool_call_id, name="adicionar_detalhe")],
        }
    )


@tool
def consultar_chamado(chamado_id: str, state: Annotated[dict, InjectedState]) -> str:
    """Consulta categoria, prioridade, status e detalhes de um chamado (leitura)."""
    ch = _chamados(state).get(chamado_id)
    if ch is None:
        return f"ERRO: chamado {chamado_id} não existe."
    detalhes = "; ".join(ch["detalhes"]) or "nenhum detalhe"
    return (
        f"Chamado {ch['id']} '{ch['titulo']}' | categoria: {categoria_nome(ch['categoria_id'])} | "
        f"prioridade: {prioridade_nome(ch['prioridade'])} | status={ch['status']} | "
        f"detalhes: {detalhes}."
    )


@tool
def fechar_chamado(
    chamado_id: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command | str:
    """Fecha (resolve) o chamado. AÇÃO SENSÍVEL (requer HITL)."""
    ch = _chamados(state).get(chamado_id)
    if ch is None:
        return f"ERRO: chamado {chamado_id} não existe."
    if ch["status"] != "aberto":
        return f"ERRO: chamado {chamado_id} já está '{ch['status']}'."
    if not ch["detalhes"]:
        return "ERRO: chamado sem detalhes. Registre ao menos um antes de fechar."
    fechado = {**ch, "status": "fechado"}
    msg = f"Chamado {chamado_id} fechado. Detalhes registrados: {len(fechado['detalhes'])}."
    return Command(
        update={
            "chamados": {chamado_id: fechado},
            "messages": [ToolMessage(msg, tool_call_id=tool_call_id, name="fechar_chamado")],
        }
    )


# Nome amigável de cada tool (exibido no lugar do nome técnico). Fica na própria
# tool (metadata) -> a tool é a fonte única; o mapa abaixo é só derivado dela.
listar_categorias.metadata = {"label": "Listar categorias"}
abrir_chamado.metadata = {"label": "Abrir chamado"}
adicionar_detalhe.metadata = {"label": "Adicionar detalhe"}
consultar_chamado.metadata = {"label": "Consultar chamado"}
fechar_chamado.metadata = {"label": "Fechar chamado"}

TOOLS = [listar_categorias, abrir_chamado, adicionar_detalhe, consultar_chamado, fechar_chamado]

# {nome_tecnico: nome_amigavel}, derivado do metadata das tools (DRY).
TOOL_LABELS = {t.name: (t.metadata or {}).get("label", t.name) for t in TOOLS}


def _categoria_options() -> list[dict]:
    """Catálogo de categorias no formato {value, label} p/ o seletor do card HITL."""
    return [{"value": c["id"], "label": c["nome"]} for c in _CATEGORIAS]


def _prioridade_options() -> list[dict]:
    """ENUM de prioridade no formato {value, label} (código gravado, rótulo exibido)."""
    return [{"value": k, "label": v} for k, v in _PRIORIDADES.items()]


# DOIS args-referência na MESMA tool — é o ponto que diferencia este agente do
# exemplo. O runtime injeta as opções nas tool calls pendentes; o front renderiza
# DOIS seletores no card de abertura (categoria + prioridade), sem o chassi conhecer
# o domínio. {nome_da_tool: {nome_do_arg: provider() -> [{value, label}]}}
FIELD_OPTIONS = {
    "abrir_chamado": {
        "categoria_id": _categoria_options,
        "prioridade": _prioridade_options,
    }
}

# Labels amigáveis dos args no card HITL (evita expor nomes técnicos na UI).
FIELD_LABELS: dict[str, dict[str, str]] = {
    "abrir_chamado": {"titulo": "Título", "categoria_id": "Categoria", "prioridade": "Prioridade"},
    "adicionar_detalhe": {"chamado_id": "Chamado", "texto": "Detalhe"},
    "fechar_chamado": {"chamado_id": "Chamado"},
}

# Args que o usuário não deve editar (referências internas, ids de sistema, etc.).
FIELD_READONLY: dict[str, list[str]] = {
    "adicionar_detalhe": ["chamado_id"],
    "fechar_chamado": ["chamado_id"],
}

# tools que ALTERAM estado (consultar_chamado é leitura). Alimenta o
# SequentialTurnMiddleware (detecção de "já houve escrita no turno") e define o que
# pede aprovação humana.
WRITE_TOOLS = ["abrir_chamado", "adicionar_detalhe", "fechar_chamado"]

# HITL: TODO write pede aprovação (approve/edit/reject).
HITL_TOOLS = WRITE_TOOLS

# SEQUENTIAL: exige TURNO PRÓPRIO (não encadeia após outra escrita no mesmo turno).
# Aqui só o fechamento (ação final/irreversível).
SEQUENTIAL_TOOLS = ["fechar_chamado"]
