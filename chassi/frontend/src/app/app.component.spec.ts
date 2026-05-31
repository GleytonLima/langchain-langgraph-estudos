import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import { AppComponent } from './app.component';
import {
  ChassiApiError,
  ChassiService,
  ChatResponse,
  HistoryResponse,
  PendingToolCall,
  SessionInfo,
} from './chassi.service';

function pendingCall(over: Partial<PendingToolCall> = {}): PendingToolCall {
  return {
    tool_call_id: 'tc1',
    tool_name: 'abrir_relatorio',
    tool_label: 'Abrir relatório',
    args: { titulo: 'Viagem', tipo_id: 'T1' },
    field_options: { tipo_id: [{ value: 'T1', label: 'Viagem' }, { value: 'T2', label: 'Alimentação' }] },
    field_labels: { titulo: 'Título', tipo_id: 'Tipo' },
    readonly_fields: [],
    ...over,
  };
}

function session(over: Partial<SessionInfo> = {}): SessionInfo {
  return { id: 's1', agent_id: 'ag', created_at: new Date().toISOString(), ...over };
}

describe('AppComponent', () => {
  let api: jasmine.SpyObj<ChassiService>;

  function makeComponent(): AppComponent {
    TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [{ provide: ChassiService, useValue: api }],
    });
    return TestBed.createComponent(AppComponent).componentInstance;
  }

  beforeEach(() => {
    localStorage.clear();
    api = jasmine.createSpyObj<ChassiService>('ChassiService', [
      'agents',
      'listSessions',
      'history',
      'createSession',
      'chat',
      'resume',
    ]);
    api.agents.and.resolveTo([
      { id: 'ag', url: 'http://ag', manifest: { agent_id: 'ag', name: 'Rex', description: 'd', capabilities: [], examples: [], hitl_tools: [] } },
    ]);
    api.listSessions.and.resolveTo([]);
    api.history.and.resolveTo({ messages: [], pending: [] } as HistoryResponse);
  });

  // ------------------------------------------------------------------ //
  // construtor + helpers de agente
  // ------------------------------------------------------------------ //

  it('carrega agentes e sessões no construtor', fakeAsync(() => {
    const c = makeComponent();
    tick();
    expect(api.agents).toHaveBeenCalled();
    expect(api.listSessions).toHaveBeenCalled();
    expect(c.agents().length).toBe(1);
    expect(c.loadingAgents()).toBeFalse();
  }));

  it('agentName cai no id quando não há manifesto', fakeAsync(() => {
    const c = makeComponent();
    tick();
    expect(c.agentName('ag')).toBe('Rex');
    expect(c.agentName('desconhecido')).toBe('desconhecido');
  }));

  it('agentInitialsFromName: duas palavras vs uma', () => {
    const c = makeComponent();
    expect(c.agentInitialsFromName('Rex Bot')).toBe('RB');
    expect(c.agentInitialsFromName('Rex')).toBe('RE');
    expect(c.agentInitialsFromName('Conta & Saldo')).toBe('CS');
  });

  it('agentInitials usa o nome resolvido', fakeAsync(() => {
    const c = makeComponent();
    tick();
    expect(c.agentInitials('ag')).toBe('RE');
  }));

  // ------------------------------------------------------------------ //
  // status / tempo / agrupamento
  // ------------------------------------------------------------------ //

  it('sessionStatusClass mapeia todos os tons', () => {
    const c = makeComponent();
    expect(c.sessionStatusClass('success')).toBe('status-sent');
    expect(c.sessionStatusClass('attention')).toBe('status-waiting');
    expect(c.sessionStatusClass('neutral')).toBe('status-draft');
    expect(c.sessionStatusClass('progress')).toBe('status-default');
  });

  it('formatSessionTime: hora no mesmo dia, data caso contrário', () => {
    const c = makeComponent();
    const hoje = c.formatSessionTime(session({ created_at: new Date().toISOString() }));
    expect(hoje).toMatch(/\d{2}:\d{2}/);
    const antigo = c.formatSessionTime(session({ created_at: '2020-01-15T10:00:00' }));
    expect(antigo).not.toMatch(/^\d{2}:\d{2}$/);
  });

  it('dateLabel: Hoje / Ontem / data', () => {
    const c = makeComponent();
    const dl = (iso: string) => (c as any).dateLabel(iso) as string;
    const ontem = new Date();
    ontem.setDate(ontem.getDate() - 1);
    expect(dl(new Date().toISOString())).toBe('Hoje');
    expect(dl(ontem.toISOString())).toBe('Ontem');
    expect(dl('2020-01-15T10:00:00')).not.toBe('Hoje');
  });

  it('groupSessions agrupa por rótulo de data', fakeAsync(() => {
    const c = makeComponent();
    tick();
    const grupos = c.groupSessions([
      session({ id: 'a', created_at: new Date().toISOString() }),
      session({ id: 'b', created_at: new Date().toISOString() }),
    ]);
    expect(grupos[0].label).toBe('Hoje');
    expect(grupos[0].sessions.length).toBe(2);
  }));

  // ------------------------------------------------------------------ //
  // navegação básica
  // ------------------------------------------------------------------ //

  it('newConversation limpa o estado da conversa', () => {
    const c = makeComponent();
    c.sessionId.set('s1');
    c.messages.set([{ role: 'user', text: 'oi' } as any]);
    c.newConversation();
    expect(c.sessionId()).toBeNull();
    expect(c.messages()).toEqual([]);
    expect(c.sidebarOpen()).toBeFalse();
  });

  it('toggleSidebar/closeSidebar', () => {
    const c = makeComponent();
    c.toggleSidebar();
    expect(c.sidebarOpen()).toBeTrue();
    c.closeSidebar();
    expect(c.sidebarOpen()).toBeFalse();
  });

  it('activeSession devolve a sessão atual ou null', fakeAsync(() => {
    const c = makeComponent();
    tick();
    c.sessions.set([session({ id: 's1' })]);
    c.sessionId.set('s1');
    expect(c.activeSession()?.id).toBe('s1');
    c.sessionId.set(null);
    expect(c.activeSession()).toBeNull();
  }));

  // ------------------------------------------------------------------ //
  // start / open
  // ------------------------------------------------------------------ //

  it('start cria sessão e zera o estado', fakeAsync(() => {
    const c = makeComponent();
    tick();
    api.createSession.and.resolveTo({ id: 's9', agent_id: 'ag', thread_id: 's9' });
    c.start('ag');
    tick();
    expect(c.sessionId()).toBe('s9');
    expect(c.activeAgent()).toBe('Rex');
    expect(c.busy()).toBeFalse();
  }));

  it('open carrega histórico e pendências', fakeAsync(() => {
    const c = makeComponent();
    tick();
    api.history.and.resolveTo({
      messages: [{ role: 'user', text: 'oi' }, { role: 'assistant', text: 'olá' }],
      pending: [pendingCall()],
      suggestions: [],
    } as HistoryResponse);
    c.open(session({ id: 's1', agent_id: 'ag' }));
    tick();
    expect(c.messages().length).toBe(2);
    expect(c.pending().length).toBe(1);
    expect(c.sessionId()).toBe('s1');
  }));

  it('selectSession abre e fecha a sidebar', fakeAsync(() => {
    const c = makeComponent();
    tick();
    c.sidebarOpen.set(true);
    c.selectSession(session({ id: 's1' }));
    tick();
    expect(c.sidebarOpen()).toBeFalse();
  }));

  // ------------------------------------------------------------------ //
  // send / quick / enter
  // ------------------------------------------------------------------ //

  it('send ignora rascunho vazio', fakeAsync(() => {
    const c = makeComponent();
    tick();
    c.draft = '   ';
    c.send();
    tick();
    expect(api.chat).not.toHaveBeenCalled();
  }));

  it('send anexa a fala do usuário e chama chat; resposta final vira mensagem', fakeAsync(() => {
    const c = makeComponent();
    tick();
    c.sessionId.set('s1');
    api.chat.and.resolveTo({ status: 'final', text: 'resposta', messages: [] } as ChatResponse);
    c.draft = 'minha pergunta';
    c.send();
    tick();
    const texts = c.messages().map((m) => m.text);
    expect(texts).toContain('minha pergunta');
    expect(texts).toContain('resposta');
    expect(c.draft).toBe('');
  }));

  it('resposta interrupt seta pendências', fakeAsync(() => {
    const c = makeComponent();
    tick();
    c.sessionId.set('s1');
    api.chat.and.resolveTo({ status: 'interrupt', tool_calls: [pendingCall()], messages: [] } as ChatResponse);
    c.draft = 'abrir relatório';
    c.send();
    tick();
    expect(c.pending().length).toBe(1);
  }));

  it('sendQuick respeita o guard de busy', fakeAsync(() => {
    const c = makeComponent();
    tick();
    c.busy.set(true);
    c.sendQuick('oi');
    tick();
    expect(api.chat).not.toHaveBeenCalled();
  }));

  it('onComposerEnter: shift não envia; enter puro envia', fakeAsync(() => {
    const c = makeComponent();
    tick();
    c.sessionId.set('s1');
    api.chat.and.resolveTo({ status: 'final', text: 'r', messages: [] } as ChatResponse);
    const shift = new KeyboardEvent('keydown', { key: 'Enter', shiftKey: true });
    spyOn(shift, 'preventDefault');
    c.onComposerEnter(shift);
    expect(shift.preventDefault).not.toHaveBeenCalled();

    c.draft = 'x';
    const enter = new KeyboardEvent('keydown', { key: 'Enter' });
    spyOn(enter, 'preventDefault');
    c.onComposerEnter(enter);
    tick();
    expect(enter.preventDefault).toHaveBeenCalled();
    expect(api.chat).toHaveBeenCalled();
  }));

  // ------------------------------------------------------------------ //
  // erros / recuperação
  // ------------------------------------------------------------------ //

  it('erro no chat sem histórico vira mensagem de erro', fakeAsync(() => {
    const c = makeComponent();
    tick();
    c.sessionId.set('s1');
    api.chat.and.rejectWith(new ChassiApiError('O agente demorou', 504));
    api.history.and.rejectWith(new Error('sem historico'));
    c.draft = 'oi';
    c.send();
    tick();
    const last = c.messages()[c.messages().length - 1];
    expect(last.role).toBe('assistant');
    expect(last.text).toBe('O agente demorou');
  }));

  it('erro no chat recupera pelo histórico quando possível', fakeAsync(() => {
    const c = makeComponent();
    tick();
    c.sessionId.set('s1');
    api.chat.and.rejectWith(new Error('caiu'));
    api.history.and.resolveTo({
      messages: [{ role: 'assistant', text: 'recuperado' }],
      pending: [],
    } as HistoryResponse);
    c.draft = 'oi';
    c.send();
    tick();
    expect(c.messages().some((m) => m.text === 'recuperado')).toBeTrue();
  }));

  it('apiErrorMessage cobre ChassiApiError, Error genérico e desconhecido', () => {
    const c = makeComponent();
    const f = (e: unknown) => (c as any).apiErrorMessage(e) as string;
    expect(f(new ChassiApiError('detalhe', 400))).toBe('detalhe');
    expect(f(new Error('boom'))).toBe('Não foi possível concluir: boom');
    expect(f('???')).toContain('Tente novamente');
  });

  // ------------------------------------------------------------------ //
  // HITL: edição de args, decide
  // ------------------------------------------------------------------ //

  it('setPending inicializa o argsDraft por tool call', () => {
    const c = makeComponent();
    (c as any).setPending([pendingCall()]);
    expect(c.pending().length).toBe(1);
    expect((c as any).argsDraft['tc1']).toEqual({ titulo: 'Viagem', tipo_id: 'T1' });
  });

  it('fieldLabel / isFieldReadonly / hasEditableFields / argKeys / optionsFor / isNumber', () => {
    const c = makeComponent();
    const tc = pendingCall({ readonly_fields: ['tipo_id'], args: { titulo: 'V', tipo_id: 'T1', valor: 10 } });
    expect(c.fieldLabel(tc, 'titulo')).toBe('Título');
    expect(c.fieldLabel(tc, 'inexistente')).toBe('inexistente');
    expect(c.isFieldReadonly(tc, 'tipo_id')).toBeTrue();
    expect(c.isFieldReadonly(tc, 'titulo')).toBeFalse();
    expect(c.hasEditableFields(tc)).toBeTrue();
    expect(c.argKeys(tc)).toEqual(['titulo', 'tipo_id', 'valor']);
    expect(c.optionsFor(tc, 'tipo_id')?.length).toBe(2);
    expect(c.isNumber(tc, 'valor')).toBeTrue();
    expect(c.isNumber(tc, 'titulo')).toBeFalse();
  });

  it('toggleHitlEditing liga e desliga (revertendo o draft)', () => {
    const c = makeComponent();
    const tc = pendingCall();
    (c as any).setPending([tc]);
    expect(c.isHitlEditing(tc)).toBeFalse();
    c.toggleHitlEditing(tc);
    expect(c.isHitlEditing(tc)).toBeTrue();
    (c as any).argsDraft['tc1'].titulo = 'Alterado';
    c.toggleHitlEditing(tc); // desliga -> reverte campos editáveis
    expect((c as any).argsDraft['tc1'].titulo).toBe('Viagem');
  });

  it('displayValue: opção (label), moeda, número e vazio', () => {
    const c = makeComponent();
    const tc = pendingCall({ args: { tipo_id: 'T2', valor: 45, descricao: '', qtd: 3 } });
    (c as any).setPending([tc]);
    expect(c.displayValue(tc, 'tipo_id')).toBe('Alimentação');
    expect(c.displayValue(tc, 'valor')).toContain('45');
    expect(c.displayValue(tc, 'qtd')).toBe('3');
    expect(c.displayValue(tc, 'descricao')).toBe('—');
  });

  it('decide(reject) envia rejeição e registra fala', fakeAsync(() => {
    const c = makeComponent();
    tick();
    c.sessionId.set('s1');
    (c as any).setPending([pendingCall()]);
    api.resume.and.resolveTo({ status: 'final', text: 'ok', messages: [] } as ChatResponse);
    c.decide('reject');
    tick();
    expect(api.resume).toHaveBeenCalled();
    const [, decisions] = api.resume.calls.mostRecent().args;
    expect(decisions[0].action).toBe('reject');
    expect(c.messages().some((m) => m.text.startsWith('rejeitou'))).toBeTrue();
  }));

  it('decide(approve) com edição manda edited_args e resumo', fakeAsync(() => {
    const c = makeComponent();
    tick();
    c.sessionId.set('s1');
    const tc = pendingCall();
    (c as any).setPending([tc]);
    c.toggleHitlEditing(tc);
    (c as any).argsDraft['tc1'].tipo_id = 'T2';
    api.resume.and.resolveTo({ status: 'final', text: 'ok', messages: [] } as ChatResponse);
    c.decide('approve');
    tick();
    const [, decisions] = api.resume.calls.mostRecent().args;
    expect(decisions[0].edited_args).toEqual(jasmine.objectContaining({ tipo_id: 'T2' }));
    expect(c.messages().some((m) => m.decision === 'edited')).toBeTrue();
  }));

  it('endSession limpa e atualiza a lista', fakeAsync(() => {
    const c = makeComponent();
    tick();
    c.sessionId.set('s1');
    c.endSession();
    expect(c.sessionId()).toBeNull();
    expect(c.decisions()).toEqual([]);
  }));

  // ------------------------------------------------------------------ //
  // computed / sincronização de mensagens
  // ------------------------------------------------------------------ //

  it('loadingMessage por ação pendente', () => {
    const c = makeComponent();
    c.pendingAction.set('start');
    expect(c.loadingMessage()).toContain('Iniciando');
    c.pendingAction.set('open');
    expect(c.loadingMessage()).toContain('Carregando conversa');
    c.pendingAction.set('chat');
    expect(c.loadingMessage()).toContain('Aguardando');
    c.pendingAction.set('resume');
    expect(c.loadingMessage()).toContain('aprovação');
    c.pendingAction.set(null);
    expect(c.loadingMessage()).toBe('Carregando…');
  });

  it('waitingReply / isEmptyChat refletem o estado', () => {
    const c = makeComponent();
    c.sessionId.set('s1');
    expect(c.isEmptyChat()).toBeTrue();
    c.busy.set(true);
    c.pendingAction.set('chat');
    expect(c.waitingReply()).toBeTrue();
    c.pendingAction.set('open');
    expect(c.isEmptyChat()).toBeFalse();
  });

  it('showDecisionRail desligado por flag', () => {
    const c = makeComponent();
    c.pending.set([pendingCall()]);
    expect(c.showDecisionRail()).toBeFalse();
  });

  it('quickReplies só aparecem ancoradas após fala do assistant', () => {
    const c = makeComponent();
    c.suggestions.set([{ label: 'Enviar', message: 'Enviar' }]);
    c.messages.set([{ role: 'assistant', text: 'pronto' } as any]);
    expect(c.quickReplyAnchor()).toBe(0);
    expect(c.quickReplies().length).toBe(1);
    c.pending.set([pendingCall()]);
    expect(c.quickReplies()).toEqual([]);
  });

  it('syncMessagesFromResponse usa resp.messages e anima decisões', () => {
    const c = makeComponent();
    const resp = {
      status: 'final',
      messages: [
        { role: 'user', text: 'aprovou Abrir relatório' },
        { role: 'assistant', text: 'feito' },
      ],
    } as ChatResponse;
    const animated = [{ role: 'user', text: 'aprovou Abrir relatório', decision: 'approved', decisionLabel: 'Abrir relatório' } as any];
    const used = (c as any).syncMessagesFromResponse(resp, animated);
    expect(used).toBeTrue();
    const dec = c.messages().find((m) => m.decision === 'approved');
    expect(dec?.decisionAnimate).toBeTrue();
  });

  it('syncMessagesFromResponse retorna false sem messages', () => {
    const c = makeComponent();
    expect((c as any).syncMessagesFromResponse({ status: 'final' } as ChatResponse)).toBeFalse();
  });

  it('buildDecisionsFromMessages extrai decisões do transcript', () => {
    const c = makeComponent();
    const out = (c as any).buildDecisionsFromMessages([
      { role: 'user', text: 'aprovou Abrir relatório' },
      { role: 'user', text: 'rejeitou Enviar' },
      { role: 'assistant', text: 'texto comum' },
      { role: 'user', text: 'editou e aprovou Item' },
    ]);
    expect(out.map((d: any) => d.status)).toEqual(['approved', 'rejected', 'edited']);
  });

  it('chatSessionTitle: vazio sem sessão, status quando "Nova conversa", título · status', fakeAsync(() => {
    const c = makeComponent();
    tick();
    expect(c.chatSessionTitle()).toBe('');
    c.sessionId.set('s1');
    (c as any).patchSessionMeta('s1', { title: 'Nova conversa', status: 'Em andamento', tone: 'progress' });
    expect(c.chatSessionTitle()).toBe('Em andamento');
    (c as any).patchSessionMeta('s1', { title: 'Viagem SP', status: 'Rascunho', tone: 'neutral' });
    expect(c.chatSessionTitle()).toBe('Viagem SP · Rascunho');
  }));

  // ------------------------------------------------------------------ //
  // meta vindo da listagem (server-side) + ordenação
  // ------------------------------------------------------------------ //

  it('loadSessions semeia o meta a partir da listagem do servidor', fakeAsync(() => {
    api.listSessions.and.resolveTo([
      session({ id: 'sx', title: 'Vinda do servidor', status_label: 'Enviado', status_tone: 'success' }),
    ]);
    const c = makeComponent();
    tick();
    expect(c.sessionMeta(session({ id: 'sx' })).title).toBe('Vinda do servidor');
    expect(c.sessionMeta(session({ id: 'sx' })).tone).toBe('success');
  }));

  it('sessionMeta cai em "Nova conversa" quando a listagem não traz título', fakeAsync(() => {
    api.listSessions.and.resolveTo([session({ id: 'sy' })]);
    const c = makeComponent();
    tick();
    expect(c.sessionMeta(session({ id: 'sy' })).title).toBe('Nova conversa');
  }));

  it('groupSessions ordena por tom (attention antes de success)', fakeAsync(() => {
    const c = makeComponent();
    tick();
    const dia = '2026-05-10T10:00:00Z';
    const a = session({ id: 'a', created_at: dia });
    const b = session({ id: 'b', created_at: dia });
    (c as any).patchSessionMeta('a', { title: 'A', status: 'ok', tone: 'success' });
    (c as any).patchSessionMeta('b', { title: 'B', status: 'pend', tone: 'attention' });
    const groups = c.groupSessions([a, b]);
    expect(groups[0].sessions.map((s) => s.id)).toEqual(['b', 'a']);
  }));

  // ------------------------------------------------------------------ //
  // sendQuick / decide com edição / formatação
  // ------------------------------------------------------------------ //

  it('sendQuick preenche o draft e dispara o envio quando livre', fakeAsync(() => {
    const c = makeComponent();
    tick();
    c.sessionId.set('s1');
    api.chat.and.resolveTo({ status: 'final', text: 'resposta' } as ChatResponse);
    c.sendQuick('oi rápido');
    tick();
    expect(api.chat).toHaveBeenCalledWith('s1', 'oi rápido');
  }));

  it('formatArgValue formata "valor" como moeda e usa label de opção', fakeAsync(() => {
    const c = makeComponent();
    tick();
    const tc = pendingCall({ args: { valor: 1500, tipo_id: 'T2' } });
    expect((c as any).formatArgValue(tc, 'valor', 1500)).toContain('R$');
    expect((c as any).formatArgValue(tc, 'tipo_id', 'T2')).toBe('Alimentação');
  }));

  it('displayValue: número não-valor e currency', fakeAsync(() => {
    const c = makeComponent();
    tick();
    const tc = pendingCall({ args: { valor: 200, qtd: 3 }, field_options: {} });
    (c as any).setPending([tc]);
    expect(c.displayValue(tc, 'valor')).toContain('R$');
    expect(c.displayValue(tc, 'qtd')).toBe('3');
  }));

  it('decide approve com edição produz edited_args e summary', fakeAsync(() => {
    const c = makeComponent();
    tick();
    c.sessionId.set('s1');
    const tc = pendingCall({ args: { titulo: 'Viagem', tipo_id: 'T1' }, readonly_fields: ['tipo_id'] });
    (c as any).setPending([tc]);
    c.toggleHitlEditing(tc); // entra em edição
    (c as any).argsDraft[tc.tool_call_id].titulo = 'Viagem SP';
    api.resume.and.resolveTo({ status: 'final', text: 'feito' } as ChatResponse);
    void c.decide('approve');
    tick();
    const [, decisions] = api.resume.calls.mostRecent().args;
    expect(decisions[0].action).toBe('approve');
    expect(decisions[0].edited_args.titulo).toBe('Viagem SP');
    expect(c.decisions().some((d) => d.status === 'edited')).toBeTrue();
  }));

  // ------------------------------------------------------------------ //
  // run: branches de interrupt e recuperação
  // ------------------------------------------------------------------ //

  it('run sem messages e status interrupt define o pending', fakeAsync(() => {
    const c = makeComponent();
    tick();
    c.sessionId.set('s1');
    api.chat.and.resolveTo({ status: 'interrupt', tool_calls: [pendingCall()] } as ChatResponse);
    c.draft = 'preciso aprovar';
    void c.send();
    tick();
    expect(c.pending().length).toBe(1);
  }));

  it('run com messages presentes e status interrupt define o pending', fakeAsync(() => {
    const c = makeComponent();
    tick();
    c.sessionId.set('s1');
    api.chat.and.resolveTo({
      status: 'interrupt',
      tool_calls: [pendingCall()],
      messages: [{ role: 'assistant', text: 'pensando' }],
    } as ChatResponse);
    c.draft = 'vai';
    void c.send();
    tick();
    expect(c.pending().length).toBe(1);
    expect(c.messages().some((m) => m.text === 'pensando')).toBeTrue();
  }));

  it('decide approve sem edição não envia edited_args', fakeAsync(() => {
    const c = makeComponent();
    tick();
    c.sessionId.set('s1');
    const tc = pendingCall();
    (c as any).setPending([tc]);
    api.resume.and.resolveTo({ status: 'final', text: 'feito' } as ChatResponse);
    void c.decide('approve');
    tick();
    const [, decisions] = api.resume.calls.mostRecent().args;
    expect(decisions[0].edited_args).toBeUndefined();
    expect(c.decisions().some((d) => d.status === 'approved')).toBeTrue();
  }));

  it('fallbacks: readonly/argKeys/displayValue sem dados', fakeAsync(() => {
    const c = makeComponent();
    tick();
    const tc = pendingCall({ args: undefined as any, readonly_fields: undefined, field_options: { tipo_id: [{ value: 'X', label: 'X' }] } });
    expect(c.isFieldReadonly(tc, 'q')).toBeFalse();
    expect(c.argKeys(tc)).toEqual([]);
    // opção existe mas valor não casa → cai no String(val) / '—'
    expect(c.displayValue(tc, 'tipo_id')).toBe('—');
  }));

  it('run com interrupt sem tool_calls define pending vazio', fakeAsync(() => {
    const c = makeComponent();
    tick();
    c.sessionId.set('s1');
    api.chat.and.resolveTo({ status: 'interrupt' } as ChatResponse);
    c.draft = 'vai';
    void c.send();
    tick();
    expect(c.pending().length).toBe(0);
  }));

  it('run recupera do histórico quando a chamada falha', fakeAsync(() => {
    const c = makeComponent();
    tick();
    c.sessionId.set('s1');
    api.chat.and.rejectWith(new ChassiApiError('timeout', 504));
    api.history.and.resolveTo({
      messages: [{ role: 'assistant', text: 'recuperado' }],
      pending: [],
    } as HistoryResponse);
    c.draft = 'vai';
    void c.send();
    tick();
    expect(c.messages().some((m) => m.text === 'recuperado')).toBeTrue();
  }));
});
