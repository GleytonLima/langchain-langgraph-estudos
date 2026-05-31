"""Tools do agente: validação anti-alucinação, de-para id<->nome e isolamento.

São funções puras (sem LLM) — o coração da garantia de que o agente não inventa
ids/tipos/totais. Por isso valem testes diretos e rápidos.

Como o estado agora vive no GRAFO (não num dict global), invocamos a função crua
(`.func`) passando um `state` explícito (`{"relatorios": {...}}`) e o `tool_call_id`.
As tools de escrita devolvem `Command`; o helper `_aplicar` interpreta o retorno:
aplica o update no `state` local (via reducer) e devolve o texto da ToolMessage.
"""

from __future__ import annotations

from app.tools import (
    FIELD_OPTIONS,
    HITL_TOOLS,
    SEQUENTIAL_TOOLS,
    TOOL_LABELS,
    WRITE_TOOLS,
    _tipo_options,
    abrir_relatorio,
    adicionar_item,
    consultar_relatorio,
    enviar_para_aprovacao,
    listar_tipos,
    merge_relatorios,
    motivo_bloqueio_envio,
    tipo_nome,
)
from langgraph.types import Command


def _aplicar(tool, state: dict, **kwargs) -> str:
    """Invoca a função crua da tool com o `state` dado e devolve o texto.

    Se a tool escreveu (retornou Command), aplica o update no `state` local
    (merge por id, como o reducer faz em produção) e extrai o texto da ToolMessage.
    """
    if "tool_call_id" in tool.func.__code__.co_varnames:
        kwargs["tool_call_id"] = "x"
    out = tool.func(**kwargs, state=state)
    if isinstance(out, Command):
        rels = out.update.get("relatorios")
        if rels:
            state["relatorios"] = merge_relatorios(state.get("relatorios"), rels)
        return str(out.update["messages"][0].content)
    return str(out)


def _abrir(state: dict, titulo="Viagem SP", tipo_id="T1") -> str:
    """Cria um relatório no `state` e devolve o id extraído da mensagem de sucesso."""
    out = abrir_relatorio.func(titulo=titulo, tipo_id=tipo_id, tool_call_id="x")
    assert isinstance(out, Command), out
    rels = out.update["relatorios"]
    state["relatorios"] = merge_relatorios(state.get("relatorios"), rels)
    return next(iter(rels))


# --------------------------------------------------------------------------- #
# Catálogo externo + de-para
# --------------------------------------------------------------------------- #


def test_listar_tipos_traz_todos_os_tipos():
    out = listar_tipos.invoke({})
    for marca in ("T1=Viagem", "T2=Alimentação", "T3=Material", "T4=Hospedagem"):
        assert marca in out


def test_tipo_nome_de_para():
    assert tipo_nome("T2") == "Alimentação"
    assert tipo_nome("T9") == "T9"  # desconhecido cai pro próprio id


def test_tipo_options_formato_value_label():
    opts = _tipo_options()
    assert {"value": "T1", "label": "Viagem"} in opts
    assert all(set(o) == {"value", "label"} for o in opts)


def test_field_options_aponta_tipo_id_de_abrir():
    provider = FIELD_OPTIONS["abrir_relatorio"]["tipo_id"]
    assert provider() == _tipo_options()


def test_field_readonly_bloqueia_ids_internos():
    from app.tools import FIELD_READONLY

    assert "relatorio_id" in FIELD_READONLY["adicionar_item"]
    assert "relatorio_id" in FIELD_READONLY["enviar_para_aprovacao"]
    assert FIELD_READONLY.get("abrir_relatorio", []) == []


# --------------------------------------------------------------------------- #
# abrir_relatorio: tipo obrigatório e validado
# --------------------------------------------------------------------------- #


def test_abrir_com_tipo_invalido_retorna_erro_com_opcoes():
    out = abrir_relatorio.func(titulo="X", tipo_id="T99", tool_call_id="x")
    assert isinstance(out, str)
    assert out.startswith("ERRO")
    assert "T1 (Viagem)" in out  # lista as opções válidas p/ o modelo se corrigir


def test_abrir_valido_cria_e_mostra_nome_do_tipo():
    out = abrir_relatorio.func(titulo="Viagem SP", tipo_id="T1", tool_call_id="x")
    assert isinstance(out, Command)
    msg = str(out.update["messages"][0].content)
    assert "tipo: Viagem" in msg
    assert "status=aberto" in msg


# --------------------------------------------------------------------------- #
# adicionar_item
# --------------------------------------------------------------------------- #


def test_adicionar_em_relatorio_inexistente_erro():
    out = _aplicar(
        adicionar_item, {"relatorios": {}}, relatorio_id="nope", descricao="Táxi", valor=45
    )
    assert out.startswith("ERRO")


def test_adicionar_valor_nao_positivo_erro():
    state: dict = {}
    rid = _abrir(state)
    out = _aplicar(adicionar_item, state, relatorio_id=rid, descricao="Táxi", valor=0)
    assert out.startswith("ERRO")


def test_adicionar_acumula_total():
    state: dict = {}
    rid = _abrir(state)
    _aplicar(adicionar_item, state, relatorio_id=rid, descricao="Táxi", valor=45)
    out = _aplicar(adicionar_item, state, relatorio_id=rid, descricao="Café", valor=5)
    assert "R$ 50.00" in out


# --------------------------------------------------------------------------- #
# enviar_para_aprovacao + pré-condição exposta ao guard
# --------------------------------------------------------------------------- #


def test_motivo_bloqueio_envio_cobre_os_casos():
    state: dict = {}
    # relatório inexistente
    assert motivo_bloqueio_envio(state, {"relatorio_id": "nope"}) is not None
    rid = _abrir(state)
    # aberto mas sem itens
    assert motivo_bloqueio_envio(state, {"relatorio_id": rid}) is not None
    _aplicar(adicionar_item, state, relatorio_id=rid, descricao="Táxi", valor=45)
    # agora pode enviar
    assert motivo_bloqueio_envio(state, {"relatorio_id": rid}) is None


def test_enviar_relatorio_inexistente_erro():
    out = _aplicar(enviar_para_aprovacao, {"relatorios": {}}, relatorio_id="nope")
    assert out.startswith("ERRO") and "não existe" in out


def test_enviar_sem_itens_erro_e_com_itens_ok():
    state: dict = {}
    rid = _abrir(state)
    assert _aplicar(enviar_para_aprovacao, state, relatorio_id=rid).startswith("ERRO")
    _aplicar(adicionar_item, state, relatorio_id=rid, descricao="Táxi", valor=45)
    out = _aplicar(enviar_para_aprovacao, state, relatorio_id=rid)
    assert "enviado para aprovação" in out
    # não dá para enviar de novo
    assert _aplicar(enviar_para_aprovacao, state, relatorio_id=rid).startswith("ERRO")


def test_acoes_em_relatorio_ja_enviado_sao_barradas():
    """Depois de enviado, nem adicionar item, nem o guard de envio liberam."""
    state: dict = {}
    rid = _abrir(state)
    _aplicar(adicionar_item, state, relatorio_id=rid, descricao="Táxi", valor=45)
    _aplicar(enviar_para_aprovacao, state, relatorio_id=rid)  # status -> enviado
    out = _aplicar(adicionar_item, state, relatorio_id=rid, descricao="Café", valor=5)
    assert out.startswith("ERRO") and "enviado" in out
    # reenviar um relatório já enviado também é barrado
    assert _aplicar(enviar_para_aprovacao, state, relatorio_id=rid).startswith("ERRO")
    motivo = motivo_bloqueio_envio(state, {"relatorio_id": rid})
    assert motivo is not None and "enviado" in motivo


def test_consultar_mostra_tipo_status_e_total():
    state: dict = {}
    rid = _abrir(state, tipo_id="T2")
    _aplicar(adicionar_item, state, relatorio_id=rid, descricao="Almoço", valor=30)
    out = _aplicar(consultar_relatorio, state, relatorio_id=rid)
    assert "tipo: Alimentação" in out
    assert "total: R$ 30.00" in out


# --------------------------------------------------------------------------- #
# Isolamento por thread + knobs declarados
# --------------------------------------------------------------------------- #


def test_relatorios_isolados_por_thread():
    # cada conversa tem seu próprio state (no grafo é o checkpointer por thread_id):
    state_a: dict = {}
    rid = _abrir(state_a)
    # outra conversa (outro state) não enxerga o relatório da primeira
    assert _aplicar(consultar_relatorio, {"relatorios": {}}, relatorio_id=rid).startswith("ERRO")


def test_knobs_de_politica():
    assert HITL_TOOLS == WRITE_TOOLS  # todo write pede aprovação
    assert SEQUENTIAL_TOOLS == ["enviar_para_aprovacao"]  # só o envio é turno-próprio
    assert TOOL_LABELS["abrir_relatorio"] == "Abrir relatório"
    assert "consultar_relatorio" not in WRITE_TOOLS  # leitura não é write
