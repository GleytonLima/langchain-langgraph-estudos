# agente-suporte — segundo agente (helpdesk de TI)

FastAPI (porta 8102) construído com `create_agent` (LangChain/LangGraph v1). É o
**segundo** agente do projeto: mesmo molde do [agente-despesas](../agente-despesas/AGENTS.md),
mas com um domínio escolhido de propósito para **provar que o chassi/frontend são
genéricos**. Domínio: chamados de suporte (abrir → adicionar detalhe → fechar).
Swagger em `/docs`.

## O que ele demonstra (e o exemplo não)

- **Dois `field_options` na MESMA tool**: `abrir_chamado` expõe seletor para
  `categoria_id` **e** `prioridade` ao mesmo tempo. O card HITL renderiza dois
  selects sem o chassi conhecer o domínio — o exemplo só tinha um (`tipo_id`).
- **De-para de ENUM, não só de entidade**: `categoria_id` é um catálogo de
  entidades (id↔nome, como no exemplo); `prioridade` é um ENUM fechado de domínio
  (`baixa`/`media`/`alta` ↔ rótulo). O **mesmo** mecanismo (`{value, label}`) serve
  para os dois — anti-alucinação garante que o modelo só cite valores válidos.

## Endpoints (consumidos pelo chassi)

`GET /manifest` · `POST /chat` · `POST /resume` · `GET /history/{thread_id}` ·
`GET /health`. Tudo tipado pelos modelos de `contracts`. Ver [app/main.py](app/main.py).

## Anatomia

Idêntica ao molde — veja [agente-despesas/AGENTS.md](../agente-despesas/AGENTS.md)
para a explicação completa de cada arquivo. Aqui só muda o domínio:

- [app/tools.py](app/tools.py) — tools de chamado. `WRITE_TOOLS` =
  `abrir_chamado`, `adicionar_detalhe`, `fechar_chamado`; `SEQUENTIAL_TOOLS` =
  só `fechar_chamado` (ação final). `FIELD_OPTIONS["abrir_chamado"]` tem **dois**
  providers (categoria + prioridade).
- [app/agent.py](app/agent.py) — `ChamadoState` com `chamados`; manifest `Iris`;
  mesma pilha de middleware do molde (ToolCallLimit + HITL + SequentialTurn +
  Precondition). Para o mental model (ordem de tools, `state_schema` × `StateGraph`,
  `after_model` × `wrap_tool_call`), ver a seção **Perguntas frequentes** do molde.
- [app/presentation.py](app/presentation.py) — status Aberto/Fechado; sugere
  "Fechar chamado" quando há detalhes.
- [app/runtime.py](app/runtime.py) · [app/llm.py](app/llm.py) — iguais ao molde
  (lê `chamados` em vez de `relatorios`).

## Testes
`.venv/Scripts/python -m pytest --cov=app` (100%). Mesmos padrões do molde:
LLM dublada (`GenericFakeChatModel`), `MemorySaver`, Langfuse via
`monkeypatch.setitem(sys.modules, ...)`, `cache_clear()` nas funções `@lru_cache`.
