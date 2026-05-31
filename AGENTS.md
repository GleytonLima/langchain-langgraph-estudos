# AGENTS.md

Guia para agentes de IA (e humanos) que vão ler ou modificar este repositório.
Este é um **projeto de estudo**: serve de molde para construir agentes de IA com
`create_agent` (LangChain/LangGraph v1) atrás de um chassi genérico. Otimize para
clareza didática, não para features.

## O que é

Metáfora de **call center**: um **chassi** (proxy + frontend único) conecta o
usuário a **um agente por vez**. Não há roteamento automático — quem decide
trocar/parar é o usuário. Cada agente é um serviço FastAPI independente; outros
times "plugam" o seu no registry.

```
contracts/   protocolo Pydantic compartilhado (request/response JSON) — o CONTRATO
agents/
  agente-despesas/   FastAPI + create_agent (LM Studio) + HITL + PostgresSaver
chassi/
  app/        FastAPI: registry YAML, /api/route, sessões (Postgres), proxy síncrono
  frontend/   Angular SPA (1 view) com card de aprovação HITL
infra/        docker-compose: Langfuse + Postgres
```

## Comece pelo CONTRATO

Antes de tocar em qualquer serviço, leia [contracts/contracts/__init__.py](contracts/contracts/__init__.py).
**Tudo que trafega entre chassi e agentes passa por esses modelos Pydantic.** É a
fonte de verdade do protocolo; mudou o contrato, mudou os dois lados. Há um
[AGENTS.md próprio em contracts/](contracts/AGENTS.md).

A forma mais rápida de entender o "como fazer um agente" é olhar o **OpenAPI/Swagger**
dos dois serviços (gerado automaticamente pelo FastAPI a partir dos modelos do
contrato):

- Agente: `http://localhost:8101/docs` · spec em `/openapi.json`
- Chassi: `http://localhost:8000/docs`

## Convenções (válidas em todo o repo)

- **Anti-alucinação por tipos**: toda saída estruturada de LLM usa Pydantic
  (`response_format` / `with_structured_output`). O roteador, por exemplo, só
  consegue citar `agent_id` que existe no registry.
- **Comunicação síncrona**: request/response JSON. **Sem streaming/SSE.** Não
  introduza SSE/websocket sem necessidade explícita.
- **Chassi é agnóstico de domínio**: ele só renderiza o que o agente manda
  (`suggestions`, `session.status`, `field_options`). Nenhuma regra de negócio do
  agente pode vazar para o chassi ou para o frontend.
- **KISS**: o `agente-despesas` implementa o caso simples (validação na própria
  tool). Fluxos de ordem estrita usam `state_schema` + middleware (ver
  [contracts/middleware.py](contracts/contracts/middleware.py)).
- **Idioma**: código, comentários e UI em **português**. Comentários explicam o
  *porquê*, não o *o quê*.
- **Observabilidade**: toda chamada de LLM do sistema é traceada no Langfuse. O
  **agente** instrumenta o `invoke` (callbacks); o **chassi** instrumenta o
  roteador (`/api/route`) — sua única inferência. O caminho de chat do chassi é
  proxy puro, então não há o que tracear ali.

## Comandos

Pré-requisitos: Docker, Python 3.12, Node 20+, **LM Studio** servindo
`qwen2.5-coder-7b-instruct` em `http://localhost:1234/v1`.

```bash
# Infra (Langfuse + Postgres)
cd infra && docker compose up -d

# No Windows acrescente --loop asyncio:SelectorEventLoop em ambos: o psycopg async
# não roda no ProactorEventLoop (padrão do uvicorn no Windows single-process).
# Agente   (porta 8101)
cd agents/agente-despesas && uvicorn app.main:app --port 8101 --loop asyncio:SelectorEventLoop
# Chassi   (porta 8000)
cd chassi && uvicorn app.main:app --port 8000 --loop asyncio:SelectorEventLoop
# Frontend (porta 4200)
cd chassi/frontend && npm start
```

## Testes (cobertura ~100% — mantenha assim)

```bash
# backend Python (use o venv de cada módulo)
cd agents/agente-despesas && .venv/Scripts/python -m pytest --cov=app
cd chassi               && .venv/Scripts/python -m pytest --cov=app
cd contracts            && python -m pytest --cov=contracts   # precisa do venv do agente (tem langchain)

# frontend Angular (Karma/Jasmine + ChromeHeadless)
cd chassi/frontend && npm test
```

Ao adicionar/alterar comportamento, escreva o teste junto. Dependências de infra
(Postgres, httpx, LLM, Langfuse, fetch) são sempre mockadas nos testes.

## Adicionando um novo agente

1. Copie `agents/agente-despesas` como molde. Exponha `/manifest`, `/chat`,
   `/resume`, `/history/{thread_id}` usando os modelos de `contracts`.
2. Registre `id` + `url` em [chassi/agents.yaml](chassi/agents.yaml).
3. O chassi descobre o resto sozinho (manifesto, proxy, sessões).

## Diagrama de sequência

Uma interação completa (sugestão de agente → HITL → envio) está em
[docs/sequencia.md](docs/sequencia.md) (Mermaid, renderiza no GitHub).

## Mapa de AGENTS.md por módulo

- [contracts/AGENTS.md](contracts/AGENTS.md) — o protocolo
- [chassi/AGENTS.md](chassi/AGENTS.md) — proxy, registry, sessões, roteador
- [agents/agente-despesas/AGENTS.md](agents/agente-despesas/AGENTS.md) — molde de agente, HITL, tools
- [chassi/frontend/AGENTS.md](chassi/frontend/AGENTS.md) — SPA Angular
</content>
</invoke>
