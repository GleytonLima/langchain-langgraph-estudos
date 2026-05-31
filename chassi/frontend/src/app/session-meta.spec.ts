import {
  fallbackTitle,
  metaFromBackend,
  metaFromSessionInfo,
  TONE_SORT,
} from './session-meta';
import { SessionMeta as BackendSessionMeta, SessionTone } from './chassi.service';

describe('session-meta', () => {
  describe('fallbackTitle', () => {
    it('usa a primeira fala do usuário', () => {
      expect(
        fallbackTitle([
          { role: 'assistant', text: 'oi, como ajudo?' },
          { role: 'user', text: 'quero abrir um relatório' },
        ]),
      ).toBe('quero abrir um relatório');
    });

    it('pula linhas de decisão HITL (aprovou/rejeitou/editou)', () => {
      expect(
        fallbackTitle([
          { role: 'user', text: 'aprovou Abrir relatório' },
          { role: 'user', text: 'rejeitou Enviar' },
          { role: 'user', text: 'editou e aprovou X' },
          { role: 'user', text: 'a pergunta real' },
        ]),
      ).toBe('a pergunta real');
    });

    it('retorna vazio quando não há fala de usuário aproveitável', () => {
      expect(fallbackTitle([{ role: 'assistant', text: 'oi' }])).toBe('');
      expect(fallbackTitle([])).toBe('');
    });

    it('trunca títulos longos no último espaço com reticências', () => {
      const longo =
        'preciso de ajuda para organizar a viagem de negócios para São Paulo na semana que vem';
      const out = fallbackTitle([{ role: 'user', text: longo }]);
      expect(out.length).toBeLessThanOrEqual(53);
      expect(out.endsWith('…')).toBeTrue();
    });

    it('normaliza espaços em branco', () => {
      expect(fallbackTitle([{ role: 'user', text: '  oi   mundo  ' }])).toBe('oi mundo');
    });
  });

  describe('metaFromBackend', () => {
    it('usa título e status do backend quando presentes', () => {
      const backend: BackendSessionMeta = {
        title: 'Viagem SP',
        status: { label: 'Enviado', tone: 'success' },
      };
      expect(metaFromBackend(backend)).toEqual({
        title: 'Viagem SP',
        status: 'Enviado',
        tone: 'success',
      });
    });

    it('cai no fallback de título a partir das mensagens', () => {
      const meta = metaFromBackend(undefined, [{ role: 'user', text: 'minha pergunta' }]);
      expect(meta.title).toBe('minha pergunta');
      expect(meta.status).toBe('Em andamento');
      expect(meta.tone).toBe('progress');
    });

    it('usa "Nova conversa" quando não há título nem mensagens', () => {
      expect(metaFromBackend(undefined, []).title).toBe('Nova conversa');
    });

    it('ignora título só com espaços e usa o fallback', () => {
      const meta = metaFromBackend(
        { title: '   ', status: { label: '', tone: 'neutral' } },
        [{ role: 'user', text: 'oi' }],
      );
      expect(meta.title).toBe('oi');
      expect(meta.tone).toBe('neutral');
    });
  });

  describe('TONE_SORT', () => {
    it('ordena atenção primeiro e concluído por último', () => {
      const ordem = ([...(['success', 'neutral', 'attention', 'progress'] as SessionTone[])]).sort(
        (a, b) => TONE_SORT[a] - TONE_SORT[b],
      );
      expect(ordem).toEqual(['attention', 'progress', 'neutral', 'success']);
    });
  });

  describe('metaFromSessionInfo (server-side, vindo da listagem)', () => {
    it('mapeia título e status da sessão', () => {
      expect(
        metaFromSessionInfo({ title: 'Viagem SP', status_label: 'Enviado', status_tone: 'success' }),
      ).toEqual({ title: 'Viagem SP', status: 'Enviado', tone: 'success' });
    });

    it('usa "Nova conversa" e defaults quando os campos vêm vazios', () => {
      expect(metaFromSessionInfo({ title: '', status_label: '', status_tone: undefined })).toEqual({
        title: 'Nova conversa',
        status: 'Em andamento',
        tone: 'progress',
      });
    });
  });
});
