import { Injectable } from '@angular/core';

const BASE = 'http://localhost:8000';

export interface Manifest {
  agent_id: string;
  name: string;
  description: string;
  capabilities: string[];
  examples: string[];
  hitl_tools: string[];
}
export interface AgentEntry { id: string; url: string; manifest: Manifest | null; }
export interface FieldOption { value: string; label: string; }
export interface PendingToolCall {
  tool_call_id: string;
  tool_name: string;
  tool_label: string;
  args: any;
  field_options?: Record<string, FieldOption[]>;
  field_labels?: Record<string, string>;
  readonly_fields?: string[];
}
/** Botão de próximo passo que o AGENTE sugere; o chassi só renderiza. */
export interface Suggestion { label: string; message: string; primary?: boolean; }
export type SessionTone = 'neutral' | 'progress' | 'attention' | 'success';
/** Status da sessão: rótulo do agente + tom genérico (chassi mapeia p/ cor/ícone). */
export interface SessionStatus { label: string; tone: SessionTone; }
export interface SessionMeta { title: string; status: SessionStatus; }
export interface ChatResponse {
  status: 'final' | 'interrupt';
  text?: string | null;
  tool_calls?: PendingToolCall[];
  messages?: HistoryMessage[];
  suggestions?: Suggestion[];
  session?: SessionMeta;
}
export interface ToolDecision { tool_call_id: string; action: 'approve' | 'reject'; edited_args?: any; }
export interface SessionInfo {
  id: string;
  agent_id: string;
  created_at: string;
  // metadados de exibição persistidos pelo chassi (não precisa cachear no cliente)
  title?: string;
  status_label?: string;
  status_tone?: SessionTone;
}
export interface HistoryMessage { role: 'user' | 'assistant'; text: string; }
export interface HistoryResponse {
  messages: HistoryMessage[];
  pending: PendingToolCall[];
  suggestions?: Suggestion[];
  session?: SessionMeta;
}

export class ChassiApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ChassiApiError';
  }
}

@Injectable({ providedIn: 'root' })
export class ChassiService {
  async agents(): Promise<AgentEntry[]> {
    return (await fetch(`${BASE}/api/agents`)).json();
  }

  async listSessions(): Promise<SessionInfo[]> {
    return (await fetch(`${BASE}/api/sessions`)).json();
  }

  async history(sessionId: string): Promise<HistoryResponse> {
    return (await fetch(`${BASE}/api/sessions/${sessionId}/history`)).json();
  }

  async createSession(agentId: string): Promise<{ id: string; agent_id: string; thread_id: string }> {
    const r = await fetch(`${BASE}/api/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_id: agentId }),
    });
    return r.json();
  }

  async chat(sessionId: string, input: string): Promise<ChatResponse> {
    return this.post(`${BASE}/api/sessions/${sessionId}/chat`, { input });
  }

  async resume(sessionId: string, decisions: ToolDecision[]): Promise<ChatResponse> {
    return this.post(`${BASE}/api/sessions/${sessionId}/resume`, { decisions });
  }

  private async post(url: string, body: unknown): Promise<ChatResponse> {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      throw new ChassiApiError(await this.errorDetail(resp), resp.status);
    }
    return resp.json();
  }

  private async errorDetail(resp: Response): Promise<string> {
    try {
      const data = await resp.json();
      const detail = data?.detail ?? data?.message;
      if (typeof detail === 'string') return detail;
      if (detail != null) return JSON.stringify(detail);
    } catch {
      /* corpo não-JSON */
    }
    return `Erro ${resp.status}`;
  }
}
