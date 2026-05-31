# agente-despesas — molde de agente

FastAPI (porta 8101) construído com `create_agent` (LangChain/LangGraph v1).
Use como **molde** para novos agentes. Domínio de exemplo: relatórios de despesa
(abrir → adicionar item → enviar para aprovação). Swagger em `/docs`.

## Endpoints (consumidos pelo chassi)

`GET /manifest` · `POST /chat` · `POST /resume` · `GET /history/{thread_id}` ·
`GET /health`. Tudo tipado pelos modelos de `contracts`. Ver [app/main.py](app/main.py).

## Anatomia

- [app/agent.py](app/agent.py) — fiação com `create_agent`: modelo + tools +
  `state_schema` (`DespesaState`) + `system_prompt` + middleware + checkpointer.
  **Fonte única da composição.** `build_agent(model, checkpointer)` recebe as deps
  injetadas → produção usa LLM real + Postgres; testes injetam dublê + `MemorySaver`.
- [app/tools.py](app/tools.py) — as tools. **Anti-alucinação**: cada tool tem args
  tipados (`@tool` Pydantic) e VALIDA o estado no início; pré-condição não satisfeita
  → erro claro, sem seguir. A ordem do fluxo simples é garantida pelos requisitos das
  tools, sem máquina de estado.
- [app/runtime.py](app/runtime.py) — execução síncrona: `invoke`, inspeção do
  estado, montagem de `ChatResponse`/`HistoryResponse`. Aqui mora a integração
  **Langfuse** (`_callbacks` → `CallbackHandler` anexado ao `invoke`).
- [app/presentation.py](app/presentation.py) — gera as dicas de UI agnósticas
  (`Suggestion`, `SessionMeta`) a partir do estado do domínio.
- [app/llm.py](app/llm.py) — `get_llm()` (LM Studio via OpenAI-compatible).

## Conceitos-chave (o que ensinar)

- **Estado no grafo, não global**: `relatorios` vive no `state_schema`
  (`DespesaState`), então o `PostgresSaver` o persiste junto com as mensagens, pelo
  mesmo `thread_id` → a conversa reabre completa após restart / em outro device.
  Tools de escrita devolvem `Command(update={"relatorios": ..., "messages": ...})`;
  o reducer `merge_relatorios` faz merge por id.
- **Domínio SIMULADO no state (não há backend real)**: não existe tabela de
  relatórios nem API de despesas. O relatório só existe **dentro da conversa** — está
  serializado no checkpoint do LangGraph (`checkpoints`/`checkpoint_blobs`...),
  chaveado pelo `thread_id`. O catálogo de tipos (`_TIPOS_DESPESA`) é hardcoded no
  `tools.py`. Implicações: abrir outra conversa (novo `thread_id`) começa do zero,
  sem ver relatórios de outra; não há consulta global "meus relatórios". **Em
  produção**, a tool chamaria um **serviço de despesas real** (com sua própria
  tabela/regras como fonte da verdade) e o state guardaria no máximo um id/cache para
  a UX — ver "o agente não é a fonte da verdade" (a validação na tool é a borda; a
  invariante de negócio vive no backend).
- **HITL**: `HumanInTheLoopMiddleware(interrupt_on=HITL_TOOLS)` interrompe antes de
  tools sensíveis. O `/resume` converte `ToolDecision` (approve/reject/edit) no
  payload do middleware e retoma com `Command(resume=...)`.
- **Guards de fluxo** (genéricos, vêm de `contracts`) — **um por responsabilidade**:
  `PreconditionMiddleware` (barra tool por pré-condição de estado) e
  `SequentialTurnMiddleware` (segura ação irreversível para turno próprio). A POLÍTICA
  (o que é write, pré-condições, tools sequenciais) e o **wording** (`announce`) são
  injetados aqui pelo domínio — o middleware não conhece texto de tela. Ordem na lista
  importa: `after_model` roda na ordem inversa, então os guards barram envios
  prematuros **antes** do card HITL aparecer.
- **De-para id↔nome**: args que referenciam entidades externas (ex.: `tipo_id`)
  expõem `field_options` → o card HITL mostra um seletor (label visível, id gravado).
  Aparece em 3 frentes: validação, associação no estado, edição na tela.
- **ToolCallLimitMiddleware** (`run_limit=TOOL_CALL_RUN_LIMIT`): trava anti-loop por
  turno. Modelo fraco às vezes repete a mesma tool; ao estourar o limite a tool é
  bloqueada (`exit_behavior="continue"`, o default) e o turno encerra com texto, sem
  exceção. É rede de segurança — o fluxo legítimo faz poucas tool calls por turno.

## Perguntas frequentes (mental model)

Dúvidas que todo dev tem ao ler este código. Respostas curtas e onde olhar:

- **`create_agent` garante a ORDEM das tool calls?** Não. `create_agent` é um loop
  ReAct: ele dá as tools e o **modelo decide** qual chamar e em que ordem. Se você
  pedir "fecha o chamado" um modelo fraco tenta `fechar_chamado` direto. Quem garante
  a ordem é **código seu**, não o LLM: a tool valida o estado no início (erro claro se
  falta pré-requisito) e os guards (`PreconditionMiddleware`/`SequentialTurnMiddleware`)
  barram deterministicamente. A regra de ordem nunca vive só no `system_prompt`
  — prompt é dica (soft), o gate é garantia (hard).
- **Por que barrar no `after_model` e não no `wrap_tool_call`?** As duas interceptam
  tool calls. Escolhemos `after_model` por causa do **HITL**: barrando antes, a tool
  some da AIMessage e o card de aprovação **nem aparece** para uma ação que seria
  rejeitada. (`wrap_tool_call` bloquearia só na hora de executar, depois do card.)
- **`state_schema` é o `StateGraph`?** NÃO — confusão comum de nome. `state_schema`
  (ex.: `DespesaState`) só define o **formato do estado** que o agente carrega (campos
  além de `messages`, como `relatorios`); é um TypedDict, não um grafo. `StateGraph`
  (`from langgraph.graph import StateGraph`) é **outra coisa**: você desenha nós e
  arestas na unha. Não é parâmetro do `create_agent` — é uma **alternativa** a ele.
- **Por que `create_agent` + gate e não um `StateGraph` com a ordem nas arestas?**
  No `StateGraph` a ordem é a topologia (`START→a→b→c→END`) — ótimo quando a sequência
  é **fixa e inegociável** (ex.: construir casa: alicerce→parede→teto). Nosso domínio
  é **flexível**: o usuário às vezes só adiciona um item a um relatório que já existe,
  às vezes abre vários, às vezes nem envia. Forçar um grafo linear engessaria o que
  precisa ser livre. Por isso: agente flexível + gate que só impõe as pré-condições.
  (Os dois se combinam: um nó de `StateGraph` pode ser, ele mesmo, um `create_agent`.)
- **Estado no gate: leia do `state`, nunca de uma global.** As `preconditions` recebem
  `(state, args)` e leem o domínio do `state` do grafo. Uma global quebraria com
  execuções concorrentes (vários usuários no mesmo processo, agora que somos async).

## Ao criar um agente novo a partir daqui

1. Troque tools, `state_schema`, `system_prompt` e `manifest()`.
2. Mantenha o tripé: **args tipados + validação na tool + HITL nas escritas**.
3. Para fluxos de ordem estrita (não garantida pelas tools), use o
   `PreconditionMiddleware` (pré-condições) e/ou o `SequentialTurnMiddleware`
   (ação por turno + `announce` do domínio).
4. Mantenha o `ToolCallLimitMiddleware` (rede de segurança anti-loop p/ modelo fraco).

## Testes
`.venv/Scripts/python -m pytest --cov=app` (100%). Mocka LLM
(`GenericFakeChatModel`), `MemorySaver`, pool/`PostgresSaver` e Langfuse
(via `monkeypatch.setitem(sys.modules, ...)`). Funções `@lru_cache` precisam de
`cache_clear()` entre testes.
</content>
