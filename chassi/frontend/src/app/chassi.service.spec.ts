import { TestBed } from '@angular/core/testing';
import { ChassiApiError, ChassiService } from './chassi.service';

describe('ChassiService', () => {
  let service: ChassiService;
  let fetchSpy: jasmine.Spy;

  function jsonResponse(body: unknown, init: { ok?: boolean; status?: number } = {}): Response {
    return {
      ok: init.ok ?? true,
      status: init.status ?? 200,
      json: async () => body,
    } as unknown as Response;
  }

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [ChassiService] });
    service = TestBed.inject(ChassiService);
    fetchSpy = spyOn(window, 'fetch');
  });

  it('agents() faz GET em /api/agents', async () => {
    fetchSpy.and.resolveTo(jsonResponse([{ id: 'a1' }]));
    const out = await service.agents();
    expect(out).toEqual([{ id: 'a1' }] as any);
    expect(fetchSpy).toHaveBeenCalledWith('http://localhost:8000/api/agents');
  });

  it('listSessions() faz GET em /api/sessions', async () => {
    fetchSpy.and.resolveTo(jsonResponse([{ id: 's1' }]));
    await service.listSessions();
    expect(fetchSpy).toHaveBeenCalledWith('http://localhost:8000/api/sessions');
  });

  it('history() inclui o sessionId na URL', async () => {
    fetchSpy.and.resolveTo(jsonResponse({ messages: [], pending: [] }));
    await service.history('s1');
    expect(fetchSpy).toHaveBeenCalledWith('http://localhost:8000/api/sessions/s1/history');
  });

  it('createSession() faz POST com o agent_id', async () => {
    fetchSpy.and.resolveTo(jsonResponse({ id: 's1', agent_id: 'ag', thread_id: 's1' }));
    const out = await service.createSession('ag');
    expect(out.id).toBe('s1');
    const [url, init] = fetchSpy.calls.mostRecent().args;
    expect(url).toBe('http://localhost:8000/api/sessions');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ agent_id: 'ag' });
  });

  it('chat() faz POST com o input e devolve o ChatResponse', async () => {
    fetchSpy.and.resolveTo(jsonResponse({ status: 'final', text: 'oi' }));
    const out = await service.chat('s1', 'olá');
    expect(out.text).toBe('oi');
    const [url, init] = fetchSpy.calls.mostRecent().args;
    expect(url).toBe('http://localhost:8000/api/sessions/s1/chat');
    expect(JSON.parse(init.body)).toEqual({ input: 'olá' });
  });

  it('resume() faz POST com as decisões', async () => {
    fetchSpy.and.resolveTo(jsonResponse({ status: 'final', text: 'feito' }));
    const decisions = [{ tool_call_id: 'a', action: 'approve' as const }];
    await service.resume('s1', decisions);
    const [url, init] = fetchSpy.calls.mostRecent().args;
    expect(url).toBe('http://localhost:8000/api/sessions/s1/resume');
    expect(JSON.parse(init.body)).toEqual({ decisions });
  });

  describe('tratamento de erro no post()', () => {
    it('lança ChassiApiError com o detail do backend', async () => {
      fetchSpy.and.resolveTo(jsonResponse({ detail: 'O agente demorou' }, { ok: false, status: 504 }));
      await expectAsync(service.chat('s1', 'oi')).toBeRejectedWith(
        jasmine.objectContaining({ message: 'O agente demorou', status: 504 }),
      );
    });

    it('usa o campo message quando não há detail', async () => {
      fetchSpy.and.resolveTo(jsonResponse({ message: 'falhou' }, { ok: false, status: 502 }));
      try {
        await service.chat('s1', 'oi');
        fail('deveria ter lançado');
      } catch (e) {
        expect((e as ChassiApiError).message).toBe('falhou');
      }
    });

    it('serializa detail não-string como JSON', async () => {
      fetchSpy.and.resolveTo(jsonResponse({ detail: { campo: 'x' } }, { ok: false, status: 400 }));
      try {
        await service.chat('s1', 'oi');
        fail('deveria ter lançado');
      } catch (e) {
        expect((e as ChassiApiError).message).toBe('{"campo":"x"}');
      }
    });

    it('cai para "Erro <status>" quando o corpo não é JSON', async () => {
      fetchSpy.and.resolveTo({
        ok: false,
        status: 500,
        json: async () => {
          throw new Error('not json');
        },
      } as unknown as Response);
      try {
        await service.chat('s1', 'oi');
        fail('deveria ter lançado');
      } catch (e) {
        expect((e as ChassiApiError).message).toBe('Erro 500');
        expect((e as ChassiApiError).status).toBe(500);
      }
    });
  });
});
