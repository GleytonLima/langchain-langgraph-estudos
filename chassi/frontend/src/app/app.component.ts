import { Component, ElementRef, ViewChild, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  AgentEntry,
  ChassiService,
  ChatResponse,
  ChassiApiError,
  PendingToolCall,
  SessionInfo,
  SessionMeta as BackendSessionMeta,
  Suggestion,
  ToolDecision,
} from './chassi.service';
import { DecisionPillComponent } from './decision-pill.component';
import { DecisionTrailComponent, TrailDecision } from './decision-trail.component';
import {
  metaFromBackend,
  metaFromSessionInfo,
  SessionMeta,
  TONE_SORT,
} from './session-meta';

/** Trilho lateral — desligado por enquanto; código mantido para reativar. */
const ENABLE_DECISION_RAIL = false;

interface Msg {
  role: 'user' | 'assistant';
  text: string;
  decision?: 'approved' | 'edited' | 'rejected';
  decisionLabel?: string;
  decisionDetail?: string;
  decisionAnimate?: boolean;
}

function parseDecisionText(text: string): Pick<Msg, 'decision' | 'decisionLabel'> | null {
  const edited = /^editou e aprovou (.+)$/.exec(text);
  if (edited) return { decision: 'edited', decisionLabel: edited[1] };
  const approved = /^aprovou (.+)$/.exec(text);
  if (approved) return { decision: 'approved', decisionLabel: approved[1] };
  const rejected = /^rejeitou (.+)$/.exec(text);
  if (rejected) return { decision: 'rejected', decisionLabel: rejected[1] };
  return null;
}

function enrichMessage(m: { role: 'user' | 'assistant'; text: string }): Msg {
  if (m.role !== 'user') return m;
  const parsed = parseDecisionText(m.text);
  return parsed ? { ...m, ...parsed } : m;
}

interface SessionGroup {
  label: string;
  sessions: SessionInfo[];
}

type PendingAction = 'start' | 'open' | 'chat' | 'resume';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule, DecisionPillComponent, DecisionTrailComponent],
  template: `
    <div class="shell" [class.sidebar-open]="sidebarOpen()">
      <div
        class="sidebar-backdrop"
        *ngIf="sidebarOpen()"
        (click)="closeSidebar()"
        aria-hidden="true"
      ></div>

      <aside class="sidebar" id="app-sidebar" aria-label="Conversas">
        <header class="sidebar-header">
          <div class="brand-lockup">
            <span class="brand-mark" aria-hidden="true">C</span>
            <span class="brand">chassi</span>
          </div>
          <div class="sidebar-header-actions">
            <button
              type="button"
              class="btn-icon sidebar-close"
              (click)="closeSidebar()"
              aria-label="Fechar menu"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path
                  d="M6 6l12 12M18 6L6 18"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                />
              </svg>
            </button>
          </div>
        </header>

        <button class="btn-new" (click)="newConversation()" [disabled]="busy()">
          Nova conversa
        </button>

        <nav class="conversations scroll-subtle" *ngIf="loadingSessions() || sessions().length">
          <p class="section-label">Conversas</p>
          <div *ngIf="loadingSessions()" class="sidebar-loading" role="status" aria-live="polite">
            <span class="spinner spinner-sm" aria-hidden="true"></span>
            <span>Carregando…</span>
          </div>
          <div *ngFor="let group of sessionGroups()" class="date-group">
            <p class="date-label">{{ group.label }}</p>
            <button
              *ngFor="let s of group.sessions"
              class="conv-item"
              [class.active]="sessionId() === s.id"
              (click)="selectSession(s)"
              [disabled]="busy()"
            >
              <span class="avatar avatar-sm">{{ agentInitials(s.agent_id) }}</span>
              <span class="conv-text">
                <span class="conv-head">
                  <span class="conv-title">{{ sessionMeta(s).title }}</span>
                  <span class="conv-time">{{ formatSessionTime(s) }}</span>
                </span>
                <span class="conv-meta">
                  <span
                    class="status-badge"
                    [class]="sessionStatusClass(sessionMeta(s).tone)"
                  >
                    @switch (sessionMeta(s).tone) {
                      @case ('attention') {
                        <svg class="status-icon" viewBox="0 0 16 16" aria-hidden="true">
                          <circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" stroke-width="1.5"/>
                          <path d="M8 4.5V8l2.5 1.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                        </svg>
                      }
                      @case ('success') {
                        <svg class="status-icon" viewBox="0 0 16 16" aria-hidden="true">
                          <path d="M3.5 8.5l3 3 6-6.5" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                      }
                      @case ('neutral') {
                        <svg class="status-icon" viewBox="0 0 16 16" aria-hidden="true">
                          <path d="M10.5 2.5l3 3L5.5 13.5H2.5v-3L10.5 2.5z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
                        </svg>
                      }
                      @default {
                        <svg class="status-icon" viewBox="0 0 16 16" aria-hidden="true">
                          <circle cx="8" cy="8" r="2.25" fill="currentColor"/>
                        </svg>
                      }
                    }
                    {{ sessionMeta(s).status }}
                  </span>
                </span>
              </span>
            </button>
          </div>
        </nav>

        <footer class="sidebar-footer">
          <span class="avatar avatar-sm avatar-user">VL</span>
          <span class="user-label">Você</span>
        </footer>
      </aside>

      <main class="main" [class.main-chat]="!!sessionId()">
        <header class="mobile-toolbar" *ngIf="!sessionId()">
          <button
            type="button"
            class="btn-menu"
            (click)="toggleSidebar()"
            [attr.aria-expanded]="sidebarOpen()"
            aria-controls="app-sidebar"
            aria-label="Abrir menu"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M4 7h16M4 12h16M4 17h16"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
              />
            </svg>
          </button>
          <span class="mobile-toolbar-title">chassi</span>
        </header>

        <!-- Carregando catálogo (agentes) -->
        <section *ngIf="!sessionId() && loadingAgents()" class="catalog">
          <header class="catalog-header">
            <h1>Escolha um agente</h1>
            <p class="subtitle">
              Escolha um agente para começar. Cada um é especializado em um tipo de tarefa.
            </p>
          </header>
          <div class="loading-block" role="status" aria-live="polite">
            <span class="spinner" aria-hidden="true"></span>
            <p>Carregando agentes…</p>
          </div>
        </section>

        <!-- Catálogo de agentes -->
        <section *ngIf="!sessionId() && !loadingAgents()" class="catalog">
          <header class="catalog-header">
            <h1>Escolha um agente</h1>
            <p class="subtitle">
              Escolha um agente para começar. Cada um é especializado em um tipo de tarefa.
            </p>
          </header>

          <div *ngIf="busy() && pendingAction() === 'start'" class="loading-overlay" role="status" aria-live="polite">
            <span class="spinner" aria-hidden="true"></span>
            <p>{{ loadingMessage() }}</p>
          </div>

          <ul class="agent-list" [class.is-dimmed]="busy() && pendingAction() === 'start'">
            <li *ngFor="let a of agents()">
              <button
                class="agent-row"
                [class.is-offline]="!a.manifest"
                (click)="start(a.id)"
                [disabled]="!a.manifest || busy()"
              >
                <span class="avatar">{{ agentInitialsFromName(a.manifest?.name || a.id) }}</span>
                <span class="agent-info">
                  <span class="agent-name">{{ a.manifest?.name || a.id }}</span>
                  <span class="agent-desc" *ngIf="a.manifest">{{ a.manifest.description }}</span>
                  <span class="agent-desc agent-desc-offline" *ngIf="!a.manifest">
                    Indisponível no momento — o serviço deste agente não respondeu.
                  </span>
                </span>
                <span class="agent-badge-offline" *ngIf="!a.manifest">offline</span>
              </button>
            </li>
          </ul>
        </section>

        <!-- Conversa ativa -->
        <div *ngIf="sessionId()" class="chat-workspace" [class.single-column]="!showDecisionRail()">
        <section class="chat-view" [class.chat-empty]="isEmptyChat()" [class.chat-active]="!isEmptyChat()">
          <div *ngIf="busy() && pendingAction() === 'open'" class="chat-loading" role="status" aria-live="polite">
            <span class="spinner" aria-hidden="true"></span>
            <p>{{ loadingMessage() }}</p>
          </div>

          <header class="chat-header">
            <button
              type="button"
              class="btn-menu"
              (click)="toggleSidebar()"
              [attr.aria-expanded]="sidebarOpen()"
              aria-controls="app-sidebar"
              aria-label="Abrir menu"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path
                  d="M4 7h16M4 12h16M4 17h16"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                />
              </svg>
            </button>
            <div class="chat-meta">
              <span class="avatar avatar-sm">{{ agentInitials(activeAgentId()) }}</span>
              <span>
                <strong>{{ activeAgent() }}</strong>
                <span class="chat-session muted">{{ chatSessionTitle() }}</span>
              </span>
            </div>
            <button
              type="button"
              class="btn-ghost btn-leave"
              (click)="endSession()"
              title="Volta ao catálogo de agentes"
            >
              <svg class="btn-leave-icon" viewBox="0 0 16 16" aria-hidden="true">
                <path d="M3 8h10M7 4.5L3 8l4 3.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              Voltar ao início
            </button>
          </header>

          <div #chatScroll class="chat-scroll scroll-subtle" [class.is-dimmed]="busy() && pendingAction() === 'open'">
            <div *ngIf="isEmptyChat()" class="empty-center">
              <div class="empty-prompt">
                <h2>O que você precisa?</h2>
                <p>Descreva a tarefa e o agente cuida do resto.</p>
              </div>
              <div class="composer composer-centered">
                <textarea
                  [(ngModel)]="draft"
                  placeholder="Mensagem…"
                  rows="1"
                  (keydown.enter)="onComposerEnter($event)"
                  [disabled]="busy()"
                ></textarea>
                <button
                  type="button"
                  class="btn-send"
                  (click)="send()"
                  [disabled]="busy() || !draft.trim()"
                  [attr.aria-label]="'Enviar'"
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path
                      d="M5 12h14M13 6l6 6-6 6"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                  </svg>
                </button>
              </div>
            </div>

            <div class="chat" *ngIf="messages().length || waitingReply()">
              <ng-container *ngFor="let m of messages(); let i = index">
                <div
                  class="bubble"
                  [class.user]="m.role === 'user' && !m.decision"
                  [class.assistant]="m.role === 'assistant'"
                  [class.decision]="!!m.decision"
                >
                  <ng-container *ngIf="m.decision">
                    <app-decision-pill
                      [label]="m.decisionLabel!"
                      [status]="m.decision"
                      [animate]="m.decisionAnimate ?? false"
                    />
                  </ng-container>

                  <ng-container *ngIf="!m.decision">
                    <p>{{ m.text }}</p>
                  </ng-container>
                </div>

                <div
                  *ngIf="quickReplyAnchor() === i"
                  class="quick-replies-inline"
                  role="group"
                  aria-label="Respostas rápidas"
                >
                  <button
                    *ngFor="let q of quickReplies()"
                    type="button"
                    [class.quick-reply-primary]="q.primary"
                    [class.quick-reply-secondary]="!q.primary"
                    (click)="sendQuick(q.message)"
                    [disabled]="busy()"
                  >
                    {{ q.label }}
                  </button>
                </div>
              </ng-container>

              <div *ngIf="waitingReply()" class="bubble typing" role="status" aria-live="polite">
                <p class="typing-dots" aria-label="Aguardando resposta">
                  <span></span><span></span><span></span>
                </p>
              </div>
            </div>
          </div>

          <div *ngIf="pending().length" class="hitl">
            <p class="hitl-title">Aprovação necessária</p>
            <p class="hitl-desc">Revise os dados abaixo. Para alterar, use o botão Editar.</p>
            <div *ngFor="let tc of pending()" class="hitl-card">
              <code class="tool-name">{{ tc.tool_label || tc.tool_name }}</code>
              <div *ngFor="let k of argKeys(tc)" class="field">
                <label>{{ fieldLabel(tc, k) }}</label>
                <p *ngIf="!isHitlEditing(tc) || isFieldReadonly(tc, k)" class="field-value"
                   [class.field-value-locked]="isFieldReadonly(tc, k)">
                  {{ displayValue(tc, k) }}
                </p>
                <select *ngIf="isHitlEditing(tc) && !isFieldReadonly(tc, k) && optionsFor(tc, k)"
                        [(ngModel)]="argsDraft[tc.tool_call_id][k]">
                  <option *ngFor="let o of optionsFor(tc, k)" [ngValue]="o.value">{{ o.label }}</option>
                </select>
                <input *ngIf="isHitlEditing(tc) && !isFieldReadonly(tc, k) && !optionsFor(tc, k) && isNumber(tc, k)"
                       type="number" [(ngModel)]="argsDraft[tc.tool_call_id][k]" />
                <input *ngIf="isHitlEditing(tc) && !isFieldReadonly(tc, k) && !optionsFor(tc, k) && !isNumber(tc, k)"
                       type="text" [(ngModel)]="argsDraft[tc.tool_call_id][k]" />
              </div>
              <button *ngIf="hasEditableFields(tc)" type="button" class="btn-edit"
                      (click)="toggleHitlEditing(tc)" [disabled]="busy()">
                {{ isHitlEditing(tc) ? 'Cancelar edição' : 'Editar' }}
              </button>
            </div>
            <div class="hitl-actions">
              <button class="btn-primary" (click)="decide('approve')" [disabled]="busy()">
                <span *ngIf="busy() && pendingAction() === 'resume'" class="btn-spinner" aria-hidden="true"></span>
                {{ busy() && pendingAction() === 'resume' ? 'Processando…' : 'Aprovar' }}
              </button>
              <button class="btn-ghost" (click)="decide('reject')" [disabled]="busy()">Rejeitar</button>
            </div>
          </div>

          <div class="composer-footer" *ngIf="!pending().length && !isEmptyChat()">
            <div class="composer">
              <textarea
                #composerInput
                [(ngModel)]="draft"
                placeholder="Mensagem…"
                rows="1"
                (keydown.enter)="onComposerEnter($event)"
                [disabled]="busy()"
              ></textarea>
              <button
                type="button"
                class="btn-send"
                (click)="send()"
                [disabled]="busy() || !draft.trim()"
                [attr.aria-label]="busy() && pendingAction() === 'chat' ? 'Enviando…' : 'Enviar'"
              >
                <span
                  *ngIf="busy() && pendingAction() === 'chat'"
                  class="btn-spinner btn-spinner-dark"
                  aria-hidden="true"
                ></span>
                <svg *ngIf="!(busy() && pendingAction() === 'chat')" viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    d="M5 12h14M13 6l6 6-6 6"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </button>
            </div>
          </div>
        </section>

        <app-decision-trail
          *ngIf="showDecisionRail()"
          class="decision-rail"
          [decisions]="decisions()"
          [pendingCount]="pending().length"
        />
        </div>
      </main>
    </div>
  `,
  styles: [`
    .shell {
      display: flex;
      height: 100dvh;
      min-height: 100dvh;
      max-height: 100dvh;
      overflow: hidden;
    }

    .sidebar {
      width: var(--sidebar-width);
      flex-shrink: 0;
      display: flex;
      flex-direction: column;
      background: var(--surface);
      border-right: 1px solid var(--border);
      padding: 24px 20px;
      box-shadow: var(--shadow-sm);
      min-height: 0;
      overflow: hidden;
    }

    .sidebar-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 24px;
    }

    .sidebar-header-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .sidebar-backdrop {
      display: none;
    }

    .btn-icon,
    .btn-menu {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 40px;
      height: 40px;
      padding: 0;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: var(--surface);
      color: var(--text);
      flex-shrink: 0;
      transition: background 0.15s, border-color 0.15s;
    }

    .btn-icon svg,
    .btn-menu svg {
      width: 20px;
      height: 20px;
    }

    .btn-icon:hover:not(:disabled),
    .btn-menu:hover:not(:disabled) {
      background: var(--bg);
      border-color: var(--border-strong);
    }

    .btn-menu,
    .sidebar-close {
      display: none;
    }

    .mobile-toolbar {
      display: none;
    }

    .brand-lockup {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .brand-mark {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      border-radius: var(--radius-sm);
      background: var(--brand);
      color: var(--text-inverse);
      font-size: 0.875rem;
      font-weight: 700;
    }

    .brand {
      font-size: 1.25rem;
      font-weight: 700;
      letter-spacing: -0.03em;
      color: var(--text);
    }

    .avatar {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 36px;
      height: 36px;
      border-radius: 50%;
      background: var(--trust-light);
      border: 2px solid var(--surface);
      box-shadow: var(--shadow-sm);
      font-size: 0.6875rem;
      font-weight: 700;
      color: var(--trust);
      flex-shrink: 0;
    }

    .avatar-sm {
      width: 32px;
      height: 32px;
      font-size: 0.625rem;
    }

    .avatar-xs {
      width: 24px;
      height: 24px;
      font-size: 0.5625rem;
    }

    .avatar-user {
      background: transparent;
      color: var(--text-secondary);
      border: 1.5px solid var(--border-strong);
      box-shadow: none;
    }

    .avatar:not(.avatar-user) {
      background: var(--brand-light);
      color: var(--brand);
      border: none;
      box-shadow: none;
    }

    /* avatar vazado/monocromático (sem preenchimento laranja): lista de agentes e de conversas */
    .agent-row .avatar,
    .conv-item .avatar {
      background: transparent;
      color: var(--text-secondary);
      border: 1.5px solid var(--border-strong);
      box-shadow: none;
    }

    .btn-new {
      width: 100%;
      padding: 12px 16px;
      border: none;
      border-radius: var(--radius-sm);
      background: var(--brand-solid);
      color: var(--text-inverse);
      font-size: 0.9375rem;
      font-weight: 700;
      transition: background 0.15s, transform 0.1s;
    }

    .btn-new:hover:not(:disabled) {
      background: var(--brand-solid-hover);
    }

    .btn-new:active:not(:disabled) {
      transform: scale(0.98);
    }

    .conversations {
      flex: 1;
      overflow-y: auto;
      margin-top: 28px;
      min-height: 0;
    }

    .section-label {
      font-size: 0.6875rem;
      font-weight: 700;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin: 0 0 12px 8px;
    }

    .date-group + .date-group {
      margin-top: 20px;
    }

    .date-label {
      font-size: 0.8125rem;
      font-weight: 600;
      color: var(--text-secondary);
      margin: 0 0 8px 8px;
    }

    .conv-item {
      display: flex;
      align-items: flex-start;
      gap: 12px;
      width: 100%;
      padding: 10px 12px;
      border: none;
      border-radius: var(--radius);
      background: transparent;
      text-align: left;
      color: inherit;
      transition: background 0.15s;
      min-height: 52px;
    }

    .conv-item:hover:not(:disabled) {
      background: var(--bg);
    }

    .conv-item.active {
      background: var(--trust-light);
      box-shadow: inset 3px 0 0 var(--trust);
    }

    .conv-text {
      display: flex;
      flex-direction: column;
      flex: 1;
      min-width: 0;
      gap: 4px;
    }

    .conv-head {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      width: 100%;
      min-width: 0;
    }

    .conv-title {
      flex: 1;
      min-width: 0;
      font-size: 0.875rem;
      font-weight: 600;
      line-height: 1.35;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
      white-space: normal;
      word-break: break-word;
    }

    .conv-meta {
      display: flex;
      align-items: center;
      min-width: 0;
    }

    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 3px 8px;
      border-radius: var(--radius-pill);
      font-size: 0.6875rem;
      font-weight: 600;
      line-height: 1.3;
      white-space: nowrap;
    }

    .status-icon {
      width: 12px;
      height: 12px;
      flex-shrink: 0;
    }

    .status-badge.status-sent {
      background: var(--success-light);
      color: var(--success);
    }

    .status-badge.status-waiting {
      background: var(--brand-light);
      color: var(--brand-hover);
      box-shadow: inset 0 0 0 1px var(--brand-muted);
    }

    .status-badge.status-draft {
      background: #eef2ff;
      color: #3b4fc9;
    }

    .status-badge.status-default {
      background: var(--bg);
      color: var(--text-secondary);
    }

    .conv-time {
      flex-shrink: 0;
      font-size: 0.6875rem;
      font-weight: 500;
      line-height: 1.35;
      color: var(--text-muted);
      white-space: nowrap;
    }

    .sidebar-footer {
      display: flex;
      align-items: center;
      gap: 12px;
      padding-top: 20px;
      margin-top: auto;
      border-top: 1px solid var(--border);
    }

    .user-label {
      font-size: 0.875rem;
      font-weight: 500;
      color: var(--text-secondary);
    }

    .main {
      flex: 1;
      min-width: 0;
      min-height: 0;
      overflow-x: hidden;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
    }

    .main.main-chat {
      overflow: hidden;
    }

    .catalog,
    .chat-workspace {
      flex: 1;
      min-width: 0;
      width: 100%;
      padding: var(--main-padding);
    }

    .main.main-chat .chat-workspace {
      flex: 1;
      min-height: 0;
      display: grid;
      grid-template-columns: minmax(0, 1fr) var(--rail-width);
      gap: clamp(16px, 2vw, 32px);
      align-items: stretch;
      padding-bottom: 0;
    }

    .main.main-chat .chat-workspace.single-column {
      grid-template-columns: minmax(0, 1fr);
    }

    .chat-workspace {
      display: grid;
      grid-template-columns: minmax(0, 1fr) var(--rail-width);
      gap: clamp(16px, 2vw, 32px);
      align-items: start;
    }

    .chat-workspace.single-column {
      grid-template-columns: minmax(0, 1fr);
    }

    .decision-rail {
      position: sticky;
      top: 0;
      min-width: 0;
      align-self: start;
      max-height: calc(100dvh - 2 * var(--main-padding));
      overflow-y: auto;
    }

    .main.main-chat .decision-rail {
      align-self: stretch;
      max-height: none;
      overflow-y: auto;
    }

    .catalog {
      overflow: visible;
    }

    .catalog-header h1 {
      font-size: 2rem;
      font-weight: 700;
      letter-spacing: -0.04em;
      line-height: 1.2;
      margin: 0 0 12px;
      color: var(--text);
    }

    .subtitle {
      color: var(--text-secondary);
      margin: 0 0 40px;
      font-size: 1.0625rem;
      line-height: 1.55;
      max-width: 42rem;
    }

    .agent-list {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .agent-row {
      display: flex;
      align-items: center;
      gap: 16px;
      width: 100%;
      padding: 20px 22px;
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      background: var(--surface);
      box-shadow: var(--shadow-sm);
      text-align: left;
      color: inherit;
      transition: box-shadow 0.2s, border-color 0.2s, transform 0.15s;
    }

    .agent-row:hover:not(:disabled) {
      border-color: var(--brand-muted);
      box-shadow: var(--shadow-hover);
      transform: translateY(-1px);
    }

    .agent-row:disabled {
      cursor: not-allowed;
    }

    .agent-row:disabled:not(.is-offline) {
      opacity: 0.45;
    }

    .agent-row.is-offline {
      opacity: 0.8;
    }

    .agent-desc-offline {
      color: var(--text-muted, #8a8f98);
      font-style: italic;
    }

    .agent-badge-offline {
      align-self: center;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 0.7rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      color: #9a3412;
      background: #ffedd5;
    }

    .agent-info {
      flex: 1;
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .agent-name {
      font-size: 1.0625rem;
      font-weight: 700;
      letter-spacing: -0.02em;
    }

    .agent-desc {
      font-size: 0.875rem;
      color: var(--text-secondary);
      line-height: 1.5;
    }

    .btn-primary {
      align-self: flex-start;
      padding: 14px 28px;
      border: none;
      border-radius: var(--radius-sm);
      background: var(--brand-solid);
      color: var(--text-inverse);
      font-size: 1rem;
      font-weight: 700;
      transition: background 0.15s;
    }

    .btn-primary:hover:not(:disabled) {
      background: var(--brand-solid-hover);
    }

    .btn-primary:disabled {
      opacity: 0.35;
      cursor: not-allowed;
      background: var(--text-muted);
    }

    .btn-ghost {
      padding: 10px 18px;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      background: var(--surface);
      color: var(--text-secondary);
      font-size: 0.875rem;
      font-weight: 600;
    }

    .btn-ghost:hover {
      background: var(--bg);
      color: var(--text);
      border-color: var(--text-muted);
    }

    .btn-leave {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      flex-shrink: 0;
    }

    .btn-leave-icon {
      width: 14px;
      height: 14px;
    }

    .chat-view {
      display: flex;
      flex-direction: column;
      min-width: 0;
      position: relative;
      max-width: 820px;
      margin: 0 auto;
      width: 100%;
    }

    .chat-view.chat-empty {
      height: 100%;
      min-height: 0;
    }

    .chat-view.chat-active {
      height: 100%;
      min-height: 0;
      overflow: hidden;
    }

    .chat-scroll {
      display: flex;
      flex-direction: column;
      min-width: 0;
      min-height: 0;
    }

    .chat-view.chat-active .chat-scroll {
      flex: 1;
      overflow-y: auto;
      overflow-x: hidden;
    }

    .empty-center {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 28px;
      width: 100%;
      max-width: 720px;
      margin: 0 auto;
      padding: 24px var(--main-padding);
    }

    .empty-prompt {
      text-align: center;
    }

    .empty-prompt h2 {
      margin: 0 0 10px;
      font-size: clamp(1.5rem, 3vw, 2rem);
      font-weight: 700;
      letter-spacing: -0.03em;
    }

    .empty-prompt p {
      margin: 0;
      color: var(--text-secondary);
      font-size: 1rem;
      line-height: 1.5;
    }

    .composer-centered {
      width: 100%;
      box-shadow: var(--shadow-hover);
    }

    .composer-footer {
      flex-shrink: 0;
      padding: 12px 0 var(--main-padding);
      background: var(--bg);
    }

    .quick-replies-inline {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      max-width: min(36rem, 100%);
      margin: -6px 0 14px;
    }

    .quick-reply-primary {
      padding: 10px 18px;
      border: none;
      border-radius: var(--radius-sm);
      background: var(--brand);
      color: var(--text-inverse);
      font-size: 0.875rem;
      font-weight: 700;
      transition: background 0.15s;
    }

    .quick-reply-primary:hover:not(:disabled) {
      background: var(--brand-hover);
    }

    .quick-reply-secondary {
      padding: 10px 18px;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      background: var(--surface);
      color: var(--text);
      font-size: 0.875rem;
      font-weight: 600;
      transition: border-color 0.15s, background 0.15s;
    }

    .quick-reply-secondary:hover:not(:disabled) {
      border-color: var(--brand-muted);
      background: var(--brand-light);
    }

    .quick-reply-primary:disabled,
    .quick-reply-secondary:disabled {
      opacity: 0.45;
      cursor: not-allowed;
    }

    .chat-view.chat-active .hitl {
      flex-shrink: 0;
    }

    .chat-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-shrink: 0;
      padding: 16px 20px;
      margin-bottom: 16px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      box-shadow: var(--shadow-sm);
    }

    .chat-header .chat-meta {
      flex: 1;
    }

    .chat-meta {
      display: flex;
      align-items: center;
      gap: 14px;
      min-width: 0;
    }

    .chat-meta strong {
      display: block;
      font-size: 1rem;
      font-weight: 700;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .chat-session {
      display: block;
      font-size: 0.8125rem;
      font-weight: 400;
    }

    .muted {
      color: var(--text-muted);
    }

    .chat {
      width: 100%;
      max-width: 680px;
      margin: 0 auto;
      padding: 8px 0 12px;
    }

    .bubble {
      margin-bottom: 12px;
      max-width: min(520px, 88%);
    }

    .bubble.assistant {
      max-width: min(36rem, 100%);
    }

    .bubble:not(.user) p {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      border-top-left-radius: 0;
      padding: 12px 16px;
      box-shadow: none;
      color: var(--text);
      font-size: 0.9375rem;
      line-height: 1.55;
    }

    .bubble.assistant p {
      display: inline-block;
      max-width: 36rem;
      width: 100%;
    }

    .bubble.user {
      margin-left: auto;
      text-align: right;
    }

    .bubble.user p {
      background: var(--trust);
      color: var(--text-inverse);
      border: 1px solid var(--trust);
      border-radius: var(--radius-lg);
      border-bottom-right-radius: 0;
      padding: 12px 16px;
      display: inline-block;
      text-align: left;
      font-size: 0.9375rem;
      line-height: 1.55;
    }

    .bubble-author {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 6px;
    }

    .bubble-author-user {
      justify-content: flex-end;
    }

    .bubble-author-name {
      font-size: 0.8125rem;
      font-weight: 600;
      color: var(--text-secondary);
      letter-spacing: -0.01em;
    }

    .bubble-author-user .bubble-author-name {
      color: var(--text-secondary);
    }

    .bubble-label {
      display: block;
      font-size: 0.6875rem;
      font-weight: 700;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 6px;
    }

    .bubble.user .bubble-label {
      color: var(--brand);
    }

    .bubble.decision {
      max-width: 100%;
      width: 100%;
    }

    .bubble.decision app-decision-pill {
      display: block;
      max-width: 420px;
    }

    .bubble p {
      margin: 0;
      font-size: 0.9375rem;
      line-height: 1.55;
      white-space: pre-wrap;
    }

    .hitl {
      background: var(--surface);
      border: 1px solid var(--border);
      border-left: 3px solid var(--brand);
      border-radius: var(--radius-lg);
      padding: 20px;
      margin-bottom: 12px;
      flex-shrink: 0;
      overflow-x: auto;
      box-shadow: var(--shadow-sm);
    }

    .hitl-title {
      font-weight: 700;
      font-size: 1rem;
      margin: 0 0 4px;
      color: var(--text);
    }

    .hitl-desc {
      font-size: 0.875rem;
      color: var(--text-secondary);
      margin: 0 0 16px;
    }

    .hitl-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 16px;
      margin-bottom: 12px;
      box-shadow: var(--shadow-sm);
    }

    .tool-name {
      font-size: 0.8125rem;
      font-weight: 600;
      color: var(--trust);
    }

    .field {
      display: flex;
      flex-direction: column;
      margin-top: 12px;
    }

    .field label {
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--text-secondary);
      margin-bottom: 6px;
    }

    .field-value {
      margin: 0;
      padding: 10px 12px;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      font-size: 0.9375rem;
      color: var(--text);
    }

    .field-value-locked {
      color: var(--text-muted);
      font-family: ui-monospace, monospace;
      font-size: 0.8125rem;
    }

    .btn-edit {
      margin-top: 4px;
      padding: 0;
      border: none;
      background: none;
      color: var(--trust);
      font-size: 0.8125rem;
      font-weight: 600;
      text-decoration: underline;
      text-underline-offset: 3px;
    }

    .btn-edit:hover:not(:disabled) {
      color: var(--trust-hover);
    }

    .btn-edit:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .field input,
    .field select {
      padding: 10px 12px;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      background: var(--surface);
    }

    .hitl-actions {
      display: flex;
      gap: 10px;
    }

    .composer {
      display: flex;
      gap: 10px;
      padding: 16px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      box-shadow: var(--shadow-md);
    }

    .chat-view.chat-empty .composer {
      box-shadow: var(--shadow-hover);
    }

    .composer textarea {
      flex: 1;
      padding: 12px 16px;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      font-size: 0.9375rem;
      background: var(--bg);
      resize: none;
      min-height: 48px;
      max-height: 160px;
      line-height: 1.5;
    }

    .composer textarea:focus {
      border-color: var(--border-strong);
      background: var(--surface);
    }

    .btn-send {
      flex-shrink: 0;
      align-self: stretch;
      width: 48px;
      min-width: 48px;
      padding: 0;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border: 1px solid transparent;
      border-radius: var(--radius);
      background: var(--brand-solid);
      color: var(--text-inverse);
      transition: background 0.15s, box-shadow 0.15s, transform 0.1s;
    }

    .btn-send:hover:not(:disabled) {
      background: var(--brand-solid-hover);
      box-shadow: 0 2px 10px rgba(255, 98, 0, 0.35);
    }

    .btn-send:active:not(:disabled) {
      transform: scale(0.97);
    }

    .btn-send:disabled {
      opacity: 1;
      cursor: not-allowed;
      background: var(--bg);
      color: var(--text-muted);
      border-color: var(--border);
      box-shadow: none;
    }

    .btn-send svg {
      width: 20px;
      height: 20px;
    }

    .btn-spinner-dark {
      border-color: rgba(255, 255, 255, 0.35);
      border-top-color: #fff;
    }

    /* No botão Enviar, quando carregando, o botão fica claro (disabled):
       um spinner branco sumiria. Centraliza e usa a cor da marca. */
    .btn-send .btn-spinner {
      margin-right: 0;
      border-color: var(--brand-muted);
      border-top-color: var(--brand);
    }

    .spinner {
      display: inline-block;
      width: 28px;
      height: 28px;
      border: 3px solid var(--brand-muted);
      border-top-color: var(--brand);
      border-radius: 50%;
      animation: spin 0.7s linear infinite;
    }

    .spinner-sm {
      width: 16px;
      height: 16px;
      border-width: 2px;
    }

    .btn-spinner {
      display: inline-block;
      width: 14px;
      height: 14px;
      margin-right: 8px;
      border: 2px solid rgba(255, 255, 255, 0.35);
      border-top-color: #fff;
      border-radius: 50%;
      animation: spin 0.7s linear infinite;
      vertical-align: -2px;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    .loading-block,
    .loading-overlay,
    .chat-loading {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 14px;
      color: var(--text-secondary);
      font-size: 0.9375rem;
    }

    .loading-block {
      padding: 48px 0;
    }

    .loading-overlay {
      position: absolute;
      inset: 0;
      z-index: 2;
      background: rgba(244, 244, 246, 0.82);
      border-radius: var(--radius-lg);
    }

    .catalog {
      position: relative;
    }

    .is-dimmed {
      opacity: 0.45;
      pointer-events: none;
    }

    .sidebar-loading {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 12px;
      color: var(--text-muted);
      font-size: 0.8125rem;
    }

    .chat-loading {
      position: absolute;
      inset: 0;
      z-index: 2;
      background: rgba(244, 244, 246, 0.88);
      border-radius: var(--radius-lg);
    }

    .bubble.typing p {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      border-top-left-radius: var(--radius-sm);
      padding: 14px 18px;
      box-shadow: var(--shadow-sm);
    }

    .typing-dots {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      margin: 0;
    }

    .typing-dots span {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--brand);
      opacity: 0.35;
      animation: typing 1.2s infinite;
    }

    .typing-dots span:nth-child(2) { animation-delay: 0.15s; }
    .typing-dots span:nth-child(3) { animation-delay: 0.3s; }

    @keyframes typing {
      0%, 60%, 100% { opacity: 0.35; transform: translateY(0); }
      30% { opacity: 1; transform: translateY(-3px); }
    }

    @media (max-width: 1100px) {
      :host {
        --rail-width: 220px;
      }
    }

    @media (max-width: 900px) {
      .main.main-chat .chat-workspace {
        grid-template-columns: minmax(0, 1fr);
        overflow-y: auto;
      }

      .main.main-chat {
        overflow-y: auto;
      }

      .chat-view.chat-active {
        height: auto;
        min-height: min(70dvh, 600px);
        overflow: visible;
      }

      .chat-view.chat-active .chat-scroll {
        overflow: visible;
      }

      .decision-rail {
        position: static;
        align-self: auto;
        padding-top: 8px;
        border-top: 1px solid var(--border);
      }
    }

    @media (max-width: 768px) {
      .sidebar-backdrop {
        display: block;
        position: fixed;
        inset: 0;
        z-index: 40;
        background: rgba(15, 23, 42, 0.45);
        animation: fade-in 0.2s ease;
      }

      @keyframes fade-in {
        from { opacity: 0; }
        to { opacity: 1; }
      }

      .sidebar {
        position: fixed;
        top: 0;
        left: 0;
        bottom: 0;
        z-index: 50;
        width: min(var(--sidebar-width), 88vw);
        max-height: none;
        border-bottom: none;
        transform: translateX(-100%);
        transition: transform 0.25s ease;
        box-shadow: var(--shadow-md);
      }

      .shell.sidebar-open .sidebar {
        transform: translateX(0);
      }

      .btn-menu,
      .sidebar-close {
        display: inline-flex;
      }

      .sidebar-header .avatar-user {
        display: none;
      }

      .mobile-toolbar {
        display: flex;
        align-items: center;
        gap: 12px;
        flex-shrink: 0;
        padding: 12px 16px;
        background: var(--surface);
        border-bottom: 1px solid var(--border);
      }

      .mobile-toolbar-title {
        font-size: 1.0625rem;
        font-weight: 700;
        letter-spacing: -0.03em;
      }

      .main {
        padding: 0;
        width: 100%;
      }

      .catalog,
      .chat-workspace {
        padding: 16px;
      }

      .catalog-header h1 {
        font-size: 1.5rem;
      }

      .agent-row {
        padding: 16px;
      }

      .chat-header {
        flex-wrap: nowrap;
        padding: 12px 16px;
        margin-bottom: 12px;
        border-radius: 0;
        border-left: none;
        border-right: none;
      }

      .chat-view.chat-active {
        border-radius: 0;
      }

      .btn-ghost {
        flex-shrink: 0;
      }

      .bubble {
        max-width: 90%;
      }

      .quick-replies-inline {
        margin-left: 0;
      }

      .hitl-actions {
        flex-wrap: wrap;
      }

      .hitl-actions .btn-primary,
      .hitl-actions .btn-ghost {
        flex: 1;
        min-width: 120px;
      }
    }

    @media (max-width: 480px) {
      .composer {
        flex-direction: column;
        align-items: stretch;
      }

      .btn-send {
        width: 100%;
        min-height: 48px;
      }

      .chat-view.chat-empty {
        min-height: calc(100dvh - 56px);
      }

      .chat-header .chat-session {
        max-width: 10rem;
      }
    }
  `],
})
export class AppComponent {
  @ViewChild('chatScroll') private chatScroll?: ElementRef<HTMLElement>;
  @ViewChild('composerInput') private composerInput?: ElementRef<HTMLTextAreaElement>;

  draft = '';
  agents = signal<AgentEntry[]>([]);
  messages = signal<Msg[]>([]);
  pending = signal<PendingToolCall[]>([]);
  argsDraft: Record<string, Record<string, any>> = {};
  sessions = signal<SessionInfo[]>([]);
  sessionId = signal<string | null>(null);
  activeAgent = signal<string>('');
  activeAgentId = signal<string>('');
  loadingAgents = signal(true);
  loadingSessions = signal(true);
  busy = signal(false);
  pendingAction = signal<PendingAction | null>(null);
  decisions = signal<TrailDecision[]>([]);
  hitlEditing = signal<Record<string, boolean>>({});
  suggestions = signal<Suggestion[]>([]);

  // Meta em memória: semeada pela listagem do chassi (server-side) e atualizada ao
  // vivo a cada chat/resume. Sem localStorage — o servidor é a fonte da verdade.
  sessionMetaMap = signal<Record<string, SessionMeta>>({});
  sidebarOpen = signal(false);

  sessionGroups = computed(() => this.groupSessions(this.sessions()));

  showDecisionRail = computed(
    () =>
      ENABLE_DECISION_RAIL &&
      (this.decisions().length > 0 || this.pending().length > 0),
  );

  isEmptyChat = computed(() => {
    if (!this.sessionId()) return false;
    if (this.busy() && this.pendingAction() === 'open') return false;
    return this.messages().length === 0 && this.pending().length === 0;
  });

  loadingMessage = computed(() => {
    switch (this.pendingAction()) {
      case 'start':
        return 'Iniciando conversa…';
      case 'open':
        return 'Carregando conversa…';
      case 'chat':
        return 'Aguardando resposta…';
      case 'resume':
        return 'Processando aprovação…';
      default:
        return 'Carregando…';
    }
  });

  waitingReply = computed(
    () =>
      this.busy() &&
      (this.pendingAction() === 'chat' || this.pendingAction() === 'resume'),
  );

  // Âncora das sugestões: logo após a última fala do assistant (sem pendência/loading).
  // As sugestões vêm prontas do agente (resp.suggestions); o chassi só renderiza.
  quickReplyAnchor = computed((): number => {
    if (this.pending().length || this.busy() || !this.suggestions().length) return -1;
    const msgs = this.messages();
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === 'assistant' && !msgs[i].decision) return i;
    }
    return -1;
  });

  quickReplies = computed((): Suggestion[] =>
    this.quickReplyAnchor() < 0 ? [] : this.suggestions(),
  );

  constructor(private api: ChassiService) {
    this.loadAgents();
    this.loadSessions();
  }

  /** Rola a área de mensagens até o fim (após o Angular renderizar a nova msg). */
  private scrollToBottom() {
    setTimeout(() => {
      const el = this.chatScroll?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }

  /** Devolve o foco ao campo de digitação — só quando ele está visível/ativo
      (sem card HITL aberto e fora de loading). */
  private focusComposer() {
    if (this.pending().length || this.busy()) return;
    setTimeout(() => this.composerInput?.nativeElement?.focus());
  }

  activeSession(): SessionInfo | null {
    const id = this.sessionId();
    return id ? this.sessions().find((s) => s.id === id) ?? null : null;
  }

  newConversation() {
    this.sessionId.set(null);
    this.setPending([]);
    this.messages.set([]);
    this.decisions.set([]);
    this.closeSidebar();
  }

  toggleSidebar() {
    this.sidebarOpen.update((open) => !open);
  }

  closeSidebar() {
    this.sidebarOpen.set(false);
  }

  async selectSession(s: SessionInfo) {
    await this.open(s);
    this.closeSidebar();
  }

  private async loadAgents() {
    this.loadingAgents.set(true);
    try {
      this.agents.set(await this.api.agents());
    } finally {
      this.loadingAgents.set(false);
    }
  }

  private async loadSessions(showLoading = true) {
    if (showLoading) this.loadingSessions.set(true);
    try {
      const list = await this.api.listSessions();
      this.sessions.set(list);
      // semeia o meta a partir da própria listagem (o chassi já manda título/status)
      const seeded: Record<string, SessionMeta> = { ...this.sessionMetaMap() };
      for (const s of list) seeded[s.id] = metaFromSessionInfo(s);
      this.sessionMetaMap.set(seeded);
    } finally {
      if (showLoading) this.loadingSessions.set(false);
    }
  }

  private refreshSessions() {
    void this.loadSessions(false);
  }

  agentName(id: string): string {
    return this.agents().find((a) => a.id === id)?.manifest?.name ?? id;
  }

  agentInitials(agentId: string): string {
    return this.agentInitialsFromName(this.agentName(agentId));
  }

  agentInitialsFromName(name: string): string {
    const words = name.split(/[\s&]+/).filter(Boolean);
    if (words.length >= 2) {
      return (words[0][0] + words[1][0]).toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
  }

  chatSessionTitle(): string {
    const sid = this.sessionId();
    if (!sid) return '';
    const meta = this.sessionMetaMap()[sid];
    if (!meta) return '';
    if (meta.title === 'Nova conversa') return meta.status;
    return `${meta.title} · ${meta.status}`;
  }

  sessionMeta(s: SessionInfo): SessionMeta {
    return this.sessionMetaMap()[s.id] ?? this.defaultMeta();
  }

  sessionStatusClass(tone: SessionMeta['tone']): string {
    switch (tone) {
      case 'success':
        return 'status-sent';
      case 'attention':
        return 'status-waiting';
      case 'neutral':
        return 'status-draft';
      default:
        return 'status-default';
    }
  }

  formatSessionTime(s: SessionInfo): string {
    const d = new Date(s.created_at);
    const now = new Date();
    const sameDay =
      d.getFullYear() === now.getFullYear() &&
      d.getMonth() === now.getMonth() &&
      d.getDate() === now.getDate();
    if (sameDay) {
      return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    }
    return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' });
  }

  private defaultMeta(): SessionMeta {
    return { title: 'Nova conversa', status: 'Em andamento', tone: 'progress' };
  }

  private patchSessionMeta(sessionId: string, meta: SessionMeta) {
    this.sessionMetaMap.set({ ...this.sessionMetaMap(), [sessionId]: meta });
  }

  /** Grava o meta vindo do backend (agente) para esta sessão. */
  private applySessionMeta(
    sessionId: string,
    backend: BackendSessionMeta | undefined,
    messages: Array<{ role: string; text: string }>,
  ) {
    this.patchSessionMeta(sessionId, metaFromBackend(backend, messages));
  }

  groupSessions(list: SessionInfo[]): SessionGroup[] {
    const groups = new Map<string, SessionInfo[]>();
    const order: string[] = [];

    for (const s of list) {
      const label = this.dateLabel(s.created_at);
      if (!groups.has(label)) {
        groups.set(label, []);
        order.push(label);
      }
      groups.get(label)!.push(s);
    }

    return order.map((label) => ({
      label,
      sessions: [...groups.get(label)!].sort((a, b) => this.compareSessions(a, b)),
    }));
  }

  private compareSessions(a: SessionInfo, b: SessionInfo): number {
    const pa = TONE_SORT[this.sessionMeta(a).tone] ?? 1;
    const pb = TONE_SORT[this.sessionMeta(b).tone] ?? 1;
    if (pa !== pb) return pa - pb;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  }

  private dateLabel(iso: string): string {
    const date = new Date(iso);
    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const startOfDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const diffDays = Math.round((startOfToday.getTime() - startOfDate.getTime()) / 86400000);

    if (diffDays === 0) return 'Hoje';
    if (diffDays === 1) return 'Ontem';
    return date.toLocaleDateString('pt-BR', { day: '2-digit', month: 'long' });
  }

  async start(agentId: string) {
    this.busy.set(true);
    this.pendingAction.set('start');
    try {
      const s = await this.api.createSession(agentId);
      this.sessionId.set(s.id);
      this.activeAgent.set(this.agentName(agentId));
      this.activeAgentId.set(agentId);
      this.messages.set([]);
      this.decisions.set([]);
      this.suggestions.set([]);
      this.patchSessionMeta(s.id, this.defaultMeta());
      await this.loadSessions(false);
      this.closeSidebar();
    } finally {
      this.busy.set(false);
      this.pendingAction.set(null);
    }
  }

  async open(s: SessionInfo) {
    this.busy.set(true);
    this.pendingAction.set('open');
    this.sessionId.set(s.id);
    this.activeAgent.set(this.agentName(s.agent_id));
    this.activeAgentId.set(s.agent_id);
    this.messages.set([]);
    this.setPending([]);
    this.decisions.set([]);
    this.suggestions.set([]);
    try {
      const h = await this.api.history(s.id);
      this.messages.set(h.messages.map((m) => enrichMessage(m)));
      this.setPending(h.pending ?? []);
      this.decisions.set(this.buildDecisionsFromMessages(h.messages));
      this.suggestions.set(h.suggestions ?? []);
      this.applySessionMeta(s.id, h.session, h.messages);
    } finally {
      this.busy.set(false);
      this.pendingAction.set(null);
      this.scrollToBottom();
      this.focusComposer();
    }
  }

  async send() {
    const text = this.draft.trim();
    if (!text) return;
    this.draft = '';
    const sid = this.sessionId()!;
    this.messages.update((m) => [...m, { role: 'user', text }]);
    this.suggestions.set([]);
    this.scrollToBottom();
    await this.run(this.api.chat(sid, text), 'chat');
  }

  sendQuick(message: string) {
    if (this.busy()) return;
    this.draft = message;
    void this.send();
  }

  onComposerEnter(event: Event) {
    const e = event as KeyboardEvent;
    if (e.shiftKey) return;
    e.preventDefault();
    void this.send();
  }

  private decisionMessage(
    status: 'approved' | 'edited' | 'rejected',
    label: string,
    detail?: string,
    animate = false,
  ): Msg {
    const text =
      status === 'edited'
        ? `editou e aprovou ${label}`
        : status === 'approved'
          ? `aprovou ${label}`
          : `rejeitou ${label}`;
    return {
      role: 'user',
      text,
      decision: status,
      decisionLabel: label,
      decisionDetail: detail,
      decisionAnimate: animate,
    };
  }

  private editedSummary(tc: PendingToolCall): string | undefined {
    const edited = this.editedArgs(tc);
    if (!edited) return undefined;
    const parts: string[] = [];
    for (const k of this.argKeys(tc)) {
      if (JSON.stringify(edited[k]) === JSON.stringify(tc.args[k])) continue;
      const from = this.formatArgValue(tc, k, tc.args[k]);
      const to = this.formatArgValue(tc, k, edited[k]);
      parts.push(`${from} → ${to}`);
    }
    return parts.length ? `(${parts.join(', ')})` : undefined;
  }

  private formatArgValue(tc: PendingToolCall, key: string, val: unknown): string {
    const opts = this.optionsFor(tc, key);
    if (opts?.length) {
      const match = opts.find((o) => o.value === val);
      if (match) return match.label;
    }
    if (key === 'valor' && typeof val === 'number') {
      return val.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    }
    return String(val);
  }

  async decide(action: 'approve' | 'reject') {
    const decisions: ToolDecision[] = [];
    const falas: Msg[] = [];
    const trailAdds: TrailDecision[] = [];
    for (const tc of this.pending()) {
      const label = tc.tool_label || tc.tool_name;
      if (action === 'reject') {
        decisions.push({ tool_call_id: tc.tool_call_id, action });
        falas.push(this.decisionMessage('rejected', label, undefined, true));
        trailAdds.push({
          id: `${tc.tool_call_id}-reject-${Date.now()}`,
          label,
          status: 'rejected',
        });
      } else {
        const edited = this.editedArgs(tc);
        decisions.push({ tool_call_id: tc.tool_call_id, action, edited_args: edited });
        const detail = edited ? this.editedSummary(tc) : undefined;
        falas.push(
          this.decisionMessage(edited ? 'edited' : 'approved', label, detail, true),
        );
        trailAdds.push({
          id: `${tc.tool_call_id}-approve-${Date.now()}`,
          label,
          status: edited ? 'edited' : 'approved',
          animate: true,
        });
      }
    }
    this.setPending([]);
    await this.run(this.api.resume(this.sessionId()!, decisions), 'resume', falas);
    if (trailAdds.length) {
      this.decisions.update((d) => [...d, ...trailAdds]);
    }
  }

  private buildDecisionsFromMessages(
    messages: Array<{ role: string; text: string }>,
  ): TrailDecision[] {
    const out: TrailDecision[] = [];
    let i = 0;
    for (const m of messages) {
      if (m.role !== 'user') continue;
      const parsed = parseDecisionText(m.text);
      if (!parsed) continue;
      out.push({
        id: `hist-${i++}`,
        label: parsed.decisionLabel!,
        status: parsed.decision!,
      });
    }
    return out;
  }

  private editedArgs(tc: PendingToolCall): any | undefined {
    if (!this.isHitlEditing(tc)) return undefined;
    const draft = this.argsDraft[tc.tool_call_id];
    const original = { ...tc.args };
    for (const k of tc.readonly_fields ?? []) {
      draft[k] = original[k];
    }
    return JSON.stringify(draft) === JSON.stringify(original) ? undefined : draft;
  }

  private setPending(calls: PendingToolCall[]) {
    this.pending.set(calls);
    this.hitlEditing.set({});
    this.argsDraft = {};
    for (const tc of calls) this.argsDraft[tc.tool_call_id] = { ...tc.args };
  }

  fieldLabel(tc: PendingToolCall, key: string): string {
    return tc.field_labels?.[key] ?? key;
  }

  isFieldReadonly(tc: PendingToolCall, key: string): boolean {
    return tc.readonly_fields?.includes(key) ?? false;
  }

  hasEditableFields(tc: PendingToolCall): boolean {
    return this.argKeys(tc).some((k) => !this.isFieldReadonly(tc, k));
  }

  isHitlEditing(tc: PendingToolCall): boolean {
    return this.hitlEditing()[tc.tool_call_id] ?? false;
  }

  toggleHitlEditing(tc: PendingToolCall): void {
    const id = tc.tool_call_id;
    const current = this.hitlEditing();
    if (current[id]) {
      for (const k of this.argKeys(tc)) {
        if (!this.isFieldReadonly(tc, k)) {
          this.argsDraft[id][k] = tc.args[k];
        }
      }
      this.hitlEditing.set({ ...current, [id]: false });
      return;
    }
    this.hitlEditing.set({ ...current, [id]: true });
  }

  displayValue(tc: PendingToolCall, key: string): string {
    const val = this.argsDraft[tc.tool_call_id]?.[key] ?? tc.args?.[key];
    const opts = this.optionsFor(tc, key);
    if (opts?.length) {
      const match = opts.find((o) => o.value === val);
      return match?.label ?? String(val ?? '—');
    }
    if (typeof val === 'number') {
      if (key === 'valor') {
        return val.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
      }
      return String(val);
    }
    return val != null && val !== '' ? String(val) : '—';
  }

  argKeys(tc: PendingToolCall): string[] {
    return Object.keys(tc.args ?? {});
  }

  optionsFor(tc: PendingToolCall, key: string) {
    return tc.field_options?.[key];
  }

  isNumber(tc: PendingToolCall, key: string): boolean {
    return typeof tc.args?.[key] === 'number';
  }

  endSession() {
    this.sessionId.set(null);
    this.setPending([]);
    this.decisions.set([]);
    this.refreshSessions();
  }

  private syncMessagesFromResponse(resp: ChatResponse, animateDecisions?: Msg[]): boolean {
    if (!resp.messages?.length) return false;
    const msgs = resp.messages.map((m) => enrichMessage(m));
    if (animateDecisions?.length) {
      this.applyDecisionAnimation(msgs, animateDecisions);
    }
    this.messages.set(msgs);
    return true;
  }

  private applyDecisionAnimation(msgs: Msg[], animated: Msg[]) {
    for (const src of animated) {
      if (!src.decision || !src.decisionLabel) continue;
      for (let i = msgs.length - 1; i >= 0; i--) {
        const m = msgs[i];
        if (
          m.decision === src.decision &&
          m.decisionLabel === src.decisionLabel &&
          !m.decisionAnimate
        ) {
          m.decisionAnimate = true;
          if (src.decisionDetail) m.decisionDetail = src.decisionDetail;
          break;
        }
      }
    }
  }

  private async run(
    call: Promise<ChatResponse>,
    action: PendingAction,
    pendingMessages?: Msg[],
  ) {
    this.busy.set(true);
    this.pendingAction.set(action);
    try {
      const resp = await call;
      if (!this.syncMessagesFromResponse(resp, pendingMessages)) {
        if (pendingMessages?.length) {
          this.messages.update((m) => [...m, ...pendingMessages]);
        }
        if (resp.status === 'interrupt') {
          this.setPending(resp.tool_calls ?? []);
        } else if (resp.text) {
          this.messages.update((m) => [...m, { role: 'assistant', text: resp.text! }]);
        }
      } else if (resp.status === 'interrupt') {
        this.setPending(resp.tool_calls ?? []);
      }
      this.suggestions.set(resp.suggestions ?? []);
      const sid = this.sessionId();
      if (sid) {
        this.applySessionMeta(sid, resp.session, this.messages());
      }
    } catch (err) {
      const sid = this.sessionId();
      if (sid && (await this.tryRecoverFromHistory(sid))) {
        return;
      }
      this.messages.update((m) => [
        ...m,
        { role: 'assistant', text: this.apiErrorMessage(err) },
      ]);
    } finally {
      this.busy.set(false);
      this.pendingAction.set(null);
      this.scrollToBottom();
      this.focusComposer();
    }
  }

  private async tryRecoverFromHistory(sessionId: string): Promise<boolean> {
    try {
      const h = await this.api.history(sessionId);
      this.messages.set(h.messages.map((m) => enrichMessage(m)));
      this.setPending(h.pending ?? []);
      this.suggestions.set(h.suggestions ?? []);
      this.applySessionMeta(sessionId, h.session, h.messages);
      return true;
    } catch {
      return false;
    }
  }

  private apiErrorMessage(err: unknown): string {
    if (err instanceof ChassiApiError) {
      return err.message;
    }
    if (err instanceof Error && err.message) {
      return `Não foi possível concluir: ${err.message}`;
    }
    return 'Não foi possível concluir a solicitação. Tente novamente.';
  }
}
