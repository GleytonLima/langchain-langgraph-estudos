# frontend — SPA Angular do chassi

Angular 18 standalone (signals), **uma única view** sem URL routing. Fala direto
com o chassi (`http://localhost:8000/api`) pelo browser. Card de aprovação HITL.

## Arquivos

- [src/app/chassi.service.ts](src/app/chassi.service.ts) — cliente HTTP (`fetch`)
  dos endpoints `/api/*`. `ChassiApiError` carrega `status` + `message` (extrai
  `detail`/`message` do corpo do erro). **Espelha os modelos de `contracts`.**
- [src/app/app.component.ts](src/app/app.component.ts) — todo o estado da UI em
  signals: agentes, sessões, mensagens, HITL pendente, sugestões. Orquestra
  start/open/send/decide. Renderiza só o que o backend manda (agnóstico de domínio).
- [src/app/decision-trail.component.ts](src/app/decision-trail.component.ts) +
  [decision-pill.component.ts](src/app/decision-pill.component.ts) — trilha de
  decisões HITL (aprovado/rejeitado/editado), com animação.
- [src/app/session-meta.ts](src/app/session-meta.ts) — mapeia o meta da sessão
  (`metaFromSessionInfo` a partir da listagem; `metaFromBackend` ao vivo no chat/resume)
  + ordenação por `tone`. O título/status são **persistidos pelo chassi** (colunas em
  `chassi_sessions`) e vêm prontos na listagem — o front não cacheia em `localStorage`
  nem reconstrói via `/history`.

## Convenções

- **Zero domínio**: o front não conhece "despesa". `tone` (do `SessionStatus`) vira
  cor/ícone; `suggestions` viram botões; `field_options` viram seletores. Tudo
  vindo do agente via chassi.
- Signals + `computed` para estado derivado. Sem store externo.
- `ENABLE_DECISION_RAIL` controla a trilha lateral (hoje `false`).

## Comandos

```bash
npm start   # ng serve  -> http://localhost:4200
npm run build
npm test    # ng test --watch=false --code-coverage (Karma/Jasmine, ChromeHeadless)
```

## Testes
Karma + Jasmine (config em [karma.conf.js](karma.conf.js),
[tsconfig.spec.json](tsconfig.spec.json)). Cobertura ~99% linhas. `ChassiService` é
mockado com `jasmine.createSpyObj`; fluxos assíncronos usam `fakeAsync`/`tick`.
Precisa do Chrome (`CHROME_BIN` aponta para o executável).
</content>
