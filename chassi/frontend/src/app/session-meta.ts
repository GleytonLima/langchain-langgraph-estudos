import { SessionMeta as BackendSessionMeta, SessionTone } from './chassi.service';

/** Meta de sessão como o chassi guarda/exibe: rótulo de status + tom (cor/ícone). */
export interface SessionMeta {
  title: string;
  status: string;
  tone: SessionTone;
}

const DEFAULT_META: SessionMeta = { title: '', status: 'Em andamento', tone: 'progress' };

/** Ordem na sidebar por TOM (genérico): precisa de atenção primeiro, concluído por último. */
export const TONE_SORT: Record<SessionTone, number> = {
  attention: 0,
  progress: 1,
  neutral: 2,
  success: 3,
};

function truncateTitle(text: string, maxLen = 52): string {
  const oneLine = text.replace(/\s+/g, ' ').trim();
  if (oneLine.length <= maxLen) return oneLine;
  const cut = oneLine.slice(0, maxLen);
  const lastSpace = cut.lastIndexOf(' ');
  const base = lastSpace > 20 ? cut.slice(0, lastSpace) : cut;
  return `${base.trim()}…`;
}

/** Fallback de título quando o agente não mandou um: 1ª fala do usuário (genérico). */
export function fallbackTitle(messages: Array<{ role: string; text: string }>): string {
  for (const m of messages) {
    if (m.role !== 'user') continue;
    if (/^(aprovou|rejeitou|editou e aprovou) /.test(m.text)) continue;
    const t = m.text.trim();
    if (t) return truncateTitle(t);
  }
  return '';
}

/** Traduz o SessionMeta do backend (agente) no meta exibido pelo chassi. */
export function metaFromBackend(
  backend: BackendSessionMeta | undefined,
  messages: Array<{ role: string; text: string }> = [],
): SessionMeta {
  const title = backend?.title?.trim() || fallbackTitle(messages);
  const status = backend?.status?.label?.trim();
  return {
    title: title || 'Nova conversa',
    status: status || DEFAULT_META.status,
    tone: backend?.status?.tone ?? DEFAULT_META.tone,
  };
}

/** Meta a partir do que a LISTAGEM do chassi já traz (server-side, sem localStorage). */
export function metaFromSessionInfo(s: {
  title?: string;
  status_label?: string;
  status_tone?: SessionTone;
}): SessionMeta {
  return {
    title: (s.title || '').trim() || 'Nova conversa',
    status: s.status_label || DEFAULT_META.status,
    tone: s.status_tone || DEFAULT_META.tone,
  };
}
