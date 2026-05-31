# Coleção Bruno — APIs do chassi e dos agentes

Coleção [Bruno](https://www.usebruno.com/) (arquivos `.bru` em texto puro, versionáveis)
para exercitar as APIs sem o frontend.

## Como abrir
Bruno → **Open Collection** → selecione esta pasta (`bruno/`). Escolha o ambiente
**Local** no canto superior direito.

## Variáveis de ambiente (`environments/Local.bru`)
- `chassiUrl` — http://localhost:8000
- `despesasUrl` — http://localhost:8101 (agente-despesas)
- `suporteUrl` — http://localhost:8102 (agente-suporte)
- `threadId` — id de conversa ao falar **direto** com um agente. O `Chat` o
  **regenera** (uuid) a cada envio via `script:pre-request`, então cada `Chat`
  começa uma conversa nova; o `Resume` seguinte reusa o mesmo id
- `sessionId` — preenchido **automaticamente** ao rodar "Sessions — criar"
- `toolCallId` — preenchido **automaticamente** pelo `chat`/`Chat` quando a resposta
  é um `interrupt` (HITL); o `resume` já o usa

## Dois jeitos de interagir

**1. Via chassi (caminho real do produto)** — pasta `chassi/`, nesta ordem:
1. `Route — sugerir agente` (opcional): o roteador sugere qual agente atende.
2. `Sessions — criar`: cria a sessão fixada num `agent_id`. Um script salva o
   `sessionId` no ambiente.
3. `Sessions — chat`: manda uma mensagem. Se a resposta vier com `status: interrupt`,
   o script salva o `tool_call_id` pendente em `{{toolCallId}}`.
4. `Sessions — resume`: já usa `{{toolCallId}}` — só rode (ou troque `action` para
   `reject`, ou adicione `edited_args`).
5. `Sessions — history`: transcript da conversa.

**2. Direto no agente (debug)** — pastas `agente-despesas/` e `agente-suporte/`:
- `Chat`/`Resume` usam `{{threadId}}` (em vez de sessão). Mesmo fluxo de interrupt →
  resume, mas batendo no agente sem passar pelo chassi.

> Os corpos JSON trazem exemplos de domínio (abrir relatório / abrir chamado). O
> `resume` vem com `action: approve` usando `{{toolCallId}}` (capturado pelo `chat`).
> Para editar antes de aprovar, troque para `"action": "edit"` e inclua `edited_args`.
