# chassi — proxy + orquestração de sessões

FastAPI (porta 8000) que conecta o frontend a **um agente por vez**. É um **proxy
assíncrono**: no caminho de chat ele NÃO faz inferência, só repassa HTTP ao agente
reescrevendo o `thread_id` para o da sessão. Swagger em `/docs`.

## Módulos

- [app/main.py](app/main.py) — endpoints `/api/*` e tradução de erros de rede do
  agente em HTTP legível (`_proxy_agent`: timeout→504, status→502, conexão→502,
  ValueError→400). CORS liberado só para `localhost:4200`.
- [app/proxy.py](app/proxy.py) — `proxy_chat`/`proxy_resume`/`proxy_history`:
  `httpx` para `{agent.url}/chat|/resume|/history`. Valida a resposta contra os
  modelos de `contracts`.
- [app/registry.py](app/registry.py) — lê [agents.yaml](agents.yaml), busca o
  `/manifest` de cada agente (enriquecimento) e normaliza URLs. Agente offline →
  manifest `None`, mas continua listado.
- [app/sessions.py](app/sessions.py) — `session_id → (agent_id, thread_id)` no
  Postgres. **`thread_id = session_id`** (KISS); é assim que a conversa "continua de
  onde parou" — o agente recupera o estado pelo `thread_id` no checkpointer dele.
- [app/router_llm.py](app/router_llm.py) — `/api/route`: LLM com
  `with_structured_output(RouteDecision)`. **Único ponto onde o chassi pensa.**
  Descarta `agent_id` alucinado (que não está no registry) e ordena por score.

## Endpoints (todos sob `/api`)

`GET /agents` · `POST /route` · `POST /sessions` · `GET /sessions` ·
`GET /sessions/{id}` · `GET /sessions/{id}/history` · `POST /sessions/{id}/chat` ·
`POST /sessions/{id}/resume`. Sessão inexistente → 404.

## Regras

- **Zero domínio aqui.** O chassi não conhece "relatório", "despesa" etc. — só
  repassa e renderiza as dicas de UI vindas do agente (`suggestions`, `session`).
- Funções de infra usam `@lru_cache` (`_pool`, `_entries`); nos testes, sempre
  `cache_clear()` antes/depois e mocke `httpx`/Postgres.
- **Langfuse**: o caminho de chat é proxy puro (sem inferência) → não traceado. A
  **única** chamada de LLM do chassi é o roteador (`router_llm`), que **é** traceado
  via `_callbacks()` (mesmo padrão e SDK v4 do agente). Sem chaves `LANGFUSE_*`,
  roda sem traces.
- **Async ponta a ponta (para escalar com múltiplos usuários)**: endpoints `async def`,
  `httpx.AsyncClient` no proxy, `AsyncConnectionPool` + queries `await` no `sessions.py`,
  e `AsyncPostgresSaver` + `agent.ainvoke` nos agentes. Tudo roda no event loop, sem
  ocupar threads de um pool. **Lição da migração**: meia-migração (httpx async, mas DB
  síncrono) é **pior** que tudo síncrono — passa a **bloquear o event loop** em vez de
  uma thread do pool. É tudo-ou-nada. No Windows, o psycopg async exige
  `SelectorEventLoop`: suba o uvicorn com `--loop asyncio:SelectorEventLoop` (no
  Linux/Docker, deixe o uvloop padrão).

## Limitações conhecidas

- **`GET /api/sessions` não tem paginação.** `list_sessions()` devolve os
  `_LIST_LIMIT` (=50) mais recentes (`ORDER BY created_at DESC LIMIT 50`), sem
  `offset`/cursor. É KISS proposital para o uso single-user do estudo — basta para
  não crescer sem limite, mas **não** é paginação de verdade. Para produção
  multi-usuário, exporia `limit`/`offset` (ou cursor por `created_at`) como query
  params no endpoint.
- **Um único Postgres/DB compartilhado.** Chassi e os dois agentes apontam para o
  mesmo banco (`DATABASE_URL=.../chassi`): o chassi usa a tabela `chassi_sessions`; os
  agentes usam as tabelas de checkpoint do LangGraph (`checkpoints`,
  `checkpoint_writes`, `checkpoint_blobs`, `checkpoint_migrations`) — **e os dois
  agentes compartilham essas mesmas tabelas**. Funciona sem colisão (`thread_id =
  session_id` é único por sessão, e cada sessão é de um agente só), mas não há
  isolamento de estado por agente. Em produção, cada agente teria seu próprio
  banco/schema (deploy, backup e escala independentes). É KISS proposital para o estudo.

## Decisão de design: por que NÃO usamos o padrão "supervisor"

A [doc oficial do LangChain](https://docs.langchain.com/oss/python/langchain/multi-agent/subagents-personal-assistant)
descreve o padrão **supervisor**: um LLM que tem os subagentes como tools, **decide
o roteamento automaticamente** e sintetiza os resultados. Avaliamos e **não** adotamos
no chassi — de propósito:

- **Roteamento é decisão do usuário, não de um LLM.** A metáfora do projeto é uma
  central de atendimento ligando o usuário a UM agente por vez. O `router_llm` apenas
  **sugere** (`RouteDecision` com score/motivo); quem escolhe é o usuário. Um supervisor
  poria mais um LLM como **dono** da decisão de roteamento — outra camada que pode
  alucinar (delegar ao agente errado, sintetizar algo que nenhum subagente devolveu).
- **Agentes desacoplados.** Aqui os agentes são serviços FastAPI independentes (deploy,
  estado e checkpointer próprios por `thread_id`), atrás de um proxy HTTP. No supervisor,
  os subagentes viram tools in-process num único grafo — outro acoplamento/topologia.
- **Coerência com a tese do projeto.** "O agente é camada fina de experiência, não dono
  da verdade": manter o roteamento **determinístico e auditável** segue essa linha.

Quando o supervisor seria a escolha certa: quando **um pedido precisa atravessar vários
agentes** ("faça X no agente A e Y no B") ou para uma experiência de assistente único
multi-domínio — casos que descartamos de propósito. E daria para adotá-lo **sem quebrar
o chassi**: o supervisor entraria como *mais um agente* atrás do proxy (chassi continua
sem domínio), com tools chamando os `/chat` dos outros agentes — o padrão aninhado.

## Testes
`.venv/Scripts/python -m pytest --cov=app` (100%). [conftest.py](conftest.py) põe a
raiz no path. Fakes para pool/cursor, `httpx`, LLM estruturada.
</content>
