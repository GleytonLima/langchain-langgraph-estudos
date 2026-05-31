# contracts — o protocolo

Pacote Pydantic compartilhado (instalado com `-e ../contracts`) que define **todo**
o tráfego entre o chassi e os agentes. É o contrato único (DRY): se um modelo muda
aqui, os dois lados mudam juntos. Comunicação **síncrona** (request/response JSON).

Fonte: [contracts/__init__.py](contracts/__init__.py) · middlewares genéricos em
[contracts/middleware.py](contracts/middleware.py).

## Middlewares de fluxo (genéricos, agnósticos de domínio)

Em [contracts/middleware.py](contracts/middleware.py). **Uma responsabilidade cada**
(antes era um `FlowGuardMiddleware` que fazia as duas — foi separado para clareza):

- `PreconditionMiddleware` — eixo **por-tool/estado**: barra uma tool cuja
  pré-condição (`fn(state, args) -> str | None`) não está satisfeita.
- `SequentialTurnMiddleware` — eixo **temporal**: segura `sequential_tools` se já
  houve escrita (`write_tools`) no turno. A mensagem ao usuário vem **injetada**
  (`announce`) — o middleware não conhece wording nem rótulos de tela.

Ambos atuam no `after_model` reescrevendo a AIMessage (removem a tool call barrada;
sem tool calls o loop encerra). O domínio injeta a política no `build_agent` do agente.

## Os modelos, por papel

**Descoberta**
- `Manifest` — o agente se descreve ao registry/roteador do chassi (`agent_id`,
  `name`, `capabilities`, `examples`, `hitl_tools`).

**Chat (turno síncrono)**
- `ChatRequest` (`thread_id`, `input`) → `ChatResponse`.
- `ChatResponse.status` é `final` (tem `text` do assistant) ou `interrupt` (HITL:
  precisa aprovar `tool_calls` antes de rodar).
- `PendingToolCall` — uma tool aguardando aprovação. Carrega o que o card HITL
  precisa: `args`, `field_options` (de-para id↔nome p/ seletores), `field_labels`,
  `readonly_fields`.

**Retomada (HITL)**
- `ResumeRequest` (`thread_id`, `decisions`) → `ChatResponse`.
- `ToolDecision.action` ∈ `approve`|`reject`; `edited_args` opcional (usuário editou
  antes de aprovar).

**Histórico (reabrir conversa)**
- `HistoryResponse` — transcript (`messages`) + HITL pendente (`pending`). Mesmo
  shape de dicas de UI do `ChatResponse` → **paridade** entre conversa ao vivo e
  reaberta.

**Dicas de UI (opcionais, agnósticas de domínio)** — ver bloco de comentário no fonte.
- `Suggestion` — botão de próximo passo (o chassi reenvia `message` ao clicar).
- `SessionStatus` — `label` (vocabulário do agente) + `tone` genérico
  (`neutral|progress|attention|success`); o chassi traduz `tone`→cor/ícone, nunca o
  label.
- `SessionMeta` — título + status p/ a sidebar.

**Roteamento (anti-alucinação)**
- `RouteDecision` → lista de `AgentMatch` (`agent_id`, `score` 0..1, `motivo`).
  Saída estruturada força a LLM a só citar agentes que existem.

## Regras ao mexer aqui

- Campo novo opcional? Dê `default`/`default_factory` para não quebrar agentes
  antigos (degradação graciosa é intencional).
- Nada de lógica de domínio nos modelos — só forma de dados.
- `tone` e `status.label` são **separados** de propósito: domínio fica no label,
  apresentação no tone.

## Testes
`python -m pytest --cov=contracts` (rode com o venv do agente-despesas, que tem
langchain p/ os middlewares). Cobre defaults, validações (`Literal`, `score` 0..1) e
os dois middlewares de fluxo.
</content>
