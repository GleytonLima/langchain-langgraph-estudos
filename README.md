# Chassi de Agentes LangGraph (estudo)

Estudo do `create_agent` (LangChain/LangGraph v1) com a metáfora de um **call
center**: um **chassi** (proxy + frontend único) conecta o usuário a **um agente
por vez**. Não há roteamento automático entre agentes — **quem decide trocar ou
parar é o usuário**. Cada agente é um serviço FastAPI independente; outros times
plugam o seu agente no registry.

## Arquitetura

```
infra/      docker-compose: Langfuse v2 + Postgres (DBs: langfuse, chassi)
contracts/  pacote Pydantic compartilhado (protocolo request/response) — DRY
agents/
  agente-despesas/   FastAPI + create_agent (LM Studio) + HITL + PostgresSaver
  agente-suporte/    segundo agente (helpdesk) — prova que o chassi é genérico
chassi/
  app/        FastAPI: registry YAML, /api/route (Pydantic), sessões, proxy síncrono
  agents.yaml registry estático de agentes
  frontend/   Angular SPA (1 view, sem URL routing) com card de aprovação HITL
```

Ideias-chave:
- **Anti-alucinação**: toda saída estruturada usa Pydantic (`response_format` /
  `with_structured_output`). As tools validam o estado no início e devolvem erro
  claro — a ordem dos fluxos simples é garantida pelos requisitos das tools.
- **HITL**: `HumanInTheLoopMiddleware(interrupt_on=...)` interrompe antes de tools
  sensíveis; o chassi mostra um card de aprovação; o `/resume` retoma com
  `Command(resume=...)`.
- **Continuar de onde parou**: chassi guarda `session → (agent_id, thread_id)` no
  Postgres; o agente recupera o estado pelo `thread_id` no seu checkpointer.

Veja o [diagrama de sequência de uma interação completa](docs/sequencia.md).

## Pré-requisitos
- Docker, Python 3.12, Node 20+.
- **LM Studio** servindo `qwen2.5-coder-7b-instruct` em `http://localhost:1234/v1`.

## Setup (primeira vez, depois de clonar)

Cria os venvs, instala dependências e prepara os `.env`. Roda uma vez. (Git Bash no
Windows; cada `.venv/Scripts/python` usa o interpretador do próprio módulo, sem
precisar de `activate`.)

```bash
# infra: Langfuse + Postgres
cd infra && cp .env.example .env && docker compose up -d && cd ..
# Langfuse em http://localhost:3000 — crie um projeto e ponha as chaves nos .env

# agente-despesas
cd agents/agente-despesas && python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt && cp .env.example .env && cd ../..

# agente-suporte
cd agents/agente-suporte && python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt && cp .env.example .env && cd ../..

# chassi
cd chassi && python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt && cp .env.example .env && cd ..

# frontend
cd chassi/frontend && npm install && cd ../..
```

## Rodar (dia a dia, já configurado)

São **4 processos** — um por terminal (ou clique no ▶ ao lado de cada bloco, no
preview do README do PyCharm). Cada bloco é independente: pare/reinicie um sem mexer
nos outros.

> No **Windows**, a flag `--loop asyncio:SelectorEventLoop` é necessária (o psycopg
> async não roda no `ProactorEventLoop`). No **Linux/Docker**, remova-a (deixa o uvloop).

```bash
# infra (só se não estiver de pé)
cd infra && docker compose up -d && cd ..
```

```bash
# agente-despesas → http://localhost:8101
cd agents/agente-despesas && .venv/Scripts/python -m uvicorn app.main:app --port 8101 --loop asyncio:SelectorEventLoop
```

```bash
# agente-suporte → http://localhost:8102
cd agents/agente-suporte && .venv/Scripts/python -m uvicorn app.main:app --port 8102 --loop asyncio:SelectorEventLoop
```

```bash
# chassi → http://localhost:8000
cd chassi && .venv/Scripts/python -m uvicorn app.main:app --port 8000 --loop asyncio:SelectorEventLoop
```

```bash
# frontend → http://localhost:4200
cd chassi/frontend && npm start
```

## Roteiro de teste (ponta a ponta)
1. No frontend, pergunte algo (ex.: "quero lançar despesas de viagem") e clique
   em **Sugerir agentes** → o roteador retorna o `agente-despesas`.
2. **Falar com este agente** → começa a conversa (proxy).
3. Peça para abrir um relatório, adicionar um item, e **enviar para aprovação**.
4. No envio, surge o **card HITL** → **Aprovar** ou **Rejeitar**.
5. **Encerrar/trocar agente** e, depois, reusar o mesmo `session_id` (via
   `GET /api/sessions/{id}`) → o histórico continua de onde parou.
6. Veja os traces em **Langfuse** (`:3000`), se configurou as chaves.

## Adicionando um novo agente
1. Crie um serviço FastAPI expondo `/manifest`, `/chat`, `/resume` (use o
   `agente-despesas` como molde e o pacote `contracts` para o protocolo).
2. Registre-o em `chassi/agents.yaml` (`id` + `url`).

## Nota: agentes complexos com ordem estrita
Para fluxos onde a ordem não pode ser garantida só pelas tools, o padrão é um
`state_schema` customizado (ex.: `current_step`) + middleware que bloqueia tools
fora da etapa atual. O `agente-despesas` implementa só o caso simples (validação na
tool) para manter KISS.
```
