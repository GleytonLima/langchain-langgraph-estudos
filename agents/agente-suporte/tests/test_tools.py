"""Tools do agente: validação anti-alucinação, de-para id<->nome / enum e isolamento.

São funções puras (sem LLM) — o coração da garantia de que o agente não inventa
ids/categorias/prioridades/status. Por isso valem testes diretos e rápidos.

Como o estado vive no GRAFO (não num dict global), invocamos a função crua (`.func`)
passando um `state` explícito (`{"chamados": {...}}`) e o `tool_call_id`. As tools
de escrita devolvem `Command`; o helper `_aplicar` interpreta o retorno: aplica o
update no `state` local (via reducer) e devolve o texto da ToolMessage.
"""

from __future__ import annotations

from app.tools import (
    FIELD_OPTIONS,
    FIELD_READONLY,
    HITL_TOOLS,
    SEQUENTIAL_TOOLS,
    TOOL_LABELS,
    WRITE_TOOLS,
    _categoria_options,
    _prioridade_options,
    abrir_chamado,
    adicionar_detalhe,
    categoria_nome,
    consultar_chamado,
    fechar_chamado,
    listar_categorias,
    merge_chamados,
    motivo_bloqueio_fechamento,
    prioridade_nome,
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
        chs = out.update.get("chamados")
        if chs:
            state["chamados"] = merge_chamados(state.get("chamados"), chs)
        return str(out.update["messages"][0].content)
    return str(out)


def _abrir(state: dict, titulo="Notebook não liga", categoria_id="C1", prioridade="alta") -> str:
    """Cria um chamado no `state` e devolve o id extraído da mensagem de sucesso."""
    out = abrir_chamado.func(
        titulo=titulo, categoria_id=categoria_id, prioridade=prioridade, tool_call_id="x"
    )
    assert isinstance(out, Command), out
    chs = out.update["chamados"]
    state["chamados"] = merge_chamados(state.get("chamados"), chs)
    return next(iter(chs))


# --------------------------------------------------------------------------- #
# Catálogo externo + de-para (categoria e prioridade)
# --------------------------------------------------------------------------- #


def test_listar_categorias_traz_todas():
    out = listar_categorias.invoke({})
    for marca in ("C1=Hardware", "C2=Software", "C3=Rede", "C4=Acesso"):
        assert marca in out


def test_categoria_nome_de_para():
    assert categoria_nome("C2") == "Software"
    assert categoria_nome("C9") == "C9"  # desconhecida cai pro próprio id


def test_prioridade_nome_de_para():
    assert prioridade_nome("media") == "Média"
    assert prioridade_nome("urgentissima") == "urgentissima"  # fora do enum cai pro código


def test_categoria_options_formato_value_label():
    opts = _categoria_options()
    assert {"value": "C1", "label": "Hardware"} in opts
    assert all(set(o) == {"value", "label"} for o in opts)


def test_prioridade_options_formato_value_label():
    opts = _prioridade_options()
    assert {"value": "media", "label": "Média"} in opts
    assert all(set(o) == {"value", "label"} for o in opts)


def test_field_options_expoe_dois_seletores_em_abrir():
    # o diferencial deste agente: DOIS args-referência na mesma tool
    abrir = FIELD_OPTIONS["abrir_chamado"]
    assert set(abrir) == {"categoria_id", "prioridade"}
    assert abrir["categoria_id"]() == _categoria_options()
    assert abrir["prioridade"]() == _prioridade_options()


def test_field_readonly_bloqueia_ids_internos():
    assert "chamado_id" in FIELD_READONLY["adicionar_detalhe"]
    assert "chamado_id" in FIELD_READONLY["fechar_chamado"]
    assert FIELD_READONLY.get("abrir_chamado", []) == []


# --------------------------------------------------------------------------- #
# abrir_chamado: categoria E prioridade obrigatórias e validadas
# --------------------------------------------------------------------------- #


def test_abrir_com_categoria_invalida_retorna_erro_com_opcoes():
    out = abrir_chamado.func(titulo="X", categoria_id="C99", prioridade="alta", tool_call_id="x")
    assert isinstance(out, str)
    assert out.startswith("ERRO")
    assert "C1 (Hardware)" in out


def test_abrir_com_prioridade_invalida_retorna_erro_com_opcoes():
    out = abrir_chamado.func(titulo="X", categoria_id="C1", prioridade="urgente", tool_call_id="x")
    assert isinstance(out, str)
    assert out.startswith("ERRO")
    assert "baixa (Baixa)" in out


def test_abrir_valido_mostra_nome_categoria_e_prioridade():
    out = abrir_chamado.func(
        titulo="Notebook não liga", categoria_id="C1", prioridade="alta", tool_call_id="x"
    )
    assert isinstance(out, Command)
    msg = str(out.update["messages"][0].content)
    assert "categoria: Hardware" in msg
    assert "prioridade: Alta" in msg
    assert "status=aberto" in msg


# --------------------------------------------------------------------------- #
# adicionar_detalhe
# --------------------------------------------------------------------------- #


def test_adicionar_em_chamado_inexistente_erro():
    out = _aplicar(adicionar_detalhe, {"chamados": {}}, chamado_id="nope", texto="reiniciei")
    assert out.startswith("ERRO")


def test_adicionar_detalhe_vazio_erro():
    state: dict = {}
    cid = _abrir(state)
    out = _aplicar(adicionar_detalhe, state, chamado_id=cid, texto="   ")
    assert out.startswith("ERRO")


def test_adicionar_acumula_detalhes():
    state: dict = {}
    cid = _abrir(state)
    _aplicar(adicionar_detalhe, state, chamado_id=cid, texto="reiniciei")
    out = _aplicar(adicionar_detalhe, state, chamado_id=cid, texto="troquei o cabo")
    assert "Total de detalhes: 2" in out


# --------------------------------------------------------------------------- #
# fechar_chamado + pré-condição exposta ao guard
# --------------------------------------------------------------------------- #


def test_motivo_bloqueio_fechamento_cobre_os_casos():
    state: dict = {}
    # chamado inexistente
    assert motivo_bloqueio_fechamento(state, {"chamado_id": "nope"}) is not None
    cid = _abrir(state)
    # aberto mas sem detalhes
    assert motivo_bloqueio_fechamento(state, {"chamado_id": cid}) is not None
    _aplicar(adicionar_detalhe, state, chamado_id=cid, texto="reiniciei")
    # agora pode fechar
    assert motivo_bloqueio_fechamento(state, {"chamado_id": cid}) is None


def test_fechar_chamado_inexistente_erro():
    out = _aplicar(fechar_chamado, {"chamados": {}}, chamado_id="nope")
    assert out.startswith("ERRO") and "não existe" in out


def test_fechar_sem_detalhes_erro_e_com_detalhes_ok():
    state: dict = {}
    cid = _abrir(state)
    assert _aplicar(fechar_chamado, state, chamado_id=cid).startswith("ERRO")
    _aplicar(adicionar_detalhe, state, chamado_id=cid, texto="resolvido")
    out = _aplicar(fechar_chamado, state, chamado_id=cid)
    assert "fechado" in out
    # não dá para fechar de novo
    assert _aplicar(fechar_chamado, state, chamado_id=cid).startswith("ERRO")


def test_acoes_em_chamado_ja_fechado_sao_barradas():
    """Depois de fechado, nem adicionar detalhe, nem o guard de fechamento liberam."""
    state: dict = {}
    cid = _abrir(state)
    _aplicar(adicionar_detalhe, state, chamado_id=cid, texto="resolvido")
    _aplicar(fechar_chamado, state, chamado_id=cid)  # status -> fechado
    out = _aplicar(adicionar_detalhe, state, chamado_id=cid, texto="mais um")
    assert out.startswith("ERRO") and "fechado" in out
    # refechar um chamado já fechado também é barrado
    assert _aplicar(fechar_chamado, state, chamado_id=cid).startswith("ERRO")
    motivo = motivo_bloqueio_fechamento(state, {"chamado_id": cid})
    assert motivo is not None and "fechado" in motivo


def test_consultar_mostra_categoria_prioridade_status_e_detalhes():
    state: dict = {}
    cid = _abrir(state, categoria_id="C2", prioridade="baixa")
    _aplicar(adicionar_detalhe, state, chamado_id=cid, texto="erro ao abrir o app")
    out = _aplicar(consultar_chamado, state, chamado_id=cid)
    assert "categoria: Software" in out
    assert "prioridade: Baixa" in out
    assert "erro ao abrir o app" in out


# --------------------------------------------------------------------------- #
# Isolamento por thread + knobs declarados
# --------------------------------------------------------------------------- #


def test_chamados_isolados_por_thread():
    state_a: dict = {}
    cid = _abrir(state_a)
    # outra conversa (outro state) não enxerga o chamado da primeira
    assert _aplicar(consultar_chamado, {"chamados": {}}, chamado_id=cid).startswith("ERRO")


def test_knobs_de_politica():
    assert HITL_TOOLS == WRITE_TOOLS  # todo write pede aprovação
    assert SEQUENTIAL_TOOLS == ["fechar_chamado"]  # só o fechamento é turno-próprio
    assert TOOL_LABELS["abrir_chamado"] == "Abrir chamado"
    assert "consultar_chamado" not in WRITE_TOOLS  # leitura não é write
