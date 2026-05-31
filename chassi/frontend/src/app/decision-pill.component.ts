import { Component, Input, OnChanges, signal } from '@angular/core';
import { CommonModule } from '@angular/common';

export type DecisionStatus = 'approved' | 'edited' | 'rejected' | 'pending';

@Component({
  selector: 'app-decision-pill',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div
      class="pill timeline-entry"
      [class.draw]="draw()"
      [class.expanded]="expanded()"
      [class.show-text]="showText()"
      [class.status-edited]="status === 'edited'"
      [class.status-approved]="status === 'approved'"
      [class.status-rejected]="status === 'rejected'"
      [class.status-pending]="status === 'pending'"
      [class.ready]="isReady"
      aria-hidden="false"
    >
      <div class="icon-wrap">
        @if (status === 'rejected') {
          <svg viewBox="0 0 80 80" aria-hidden="true">
            <path class="cross" d="M28 28 L52 52 M52 28 L28 52" />
          </svg>
        } @else if (status === 'pending') {
          <span class="pending-ring" aria-hidden="true"></span>
        } @else {
          <svg viewBox="0 0 80 80" aria-hidden="true">
            <circle class="circle" cx="40" cy="40" r="35"></circle>
            <path class="check" d="M24 41 L35 52 L57 29"></path>
          </svg>
        }
      </div>
      <div class="text">
        <div class="title">{{ title }}</div>
        @if (subtitle) {
          <div class="pill-subtitle">{{ subtitle }}</div>
        }
      </div>
    </div>
  `,
  styles: [`
    .timeline-entry {
      display: flex;
      align-items: center;
      gap: 10px;
      width: 100%;
      max-width: 420px;
      padding: 4px 0 4px 10px;
      margin: 0;
      border: none;
      border-left: 2px solid var(--border-strong);
      border-radius: 0;
      background: transparent;
      box-shadow: none;
      cursor: default;
      pointer-events: none;
      user-select: none;
    }

    .timeline-entry.status-approved {
      border-left-color: var(--success-muted);
    }

    .timeline-entry.status-edited {
      border-left-color: var(--brand);
    }

    .timeline-entry.status-rejected {
      border-left-color: #e8a0a0;
    }

    .timeline-entry:not(.status-rejected):not(.status-pending):not(.status-approved) {
      border-left-color: var(--brand-muted);
    }

    .timeline-entry.status-approved:not(.status-rejected):not(.status-pending) {
      border-left-color: var(--success-muted);
    }

    .pill {
      width: 100%;
      min-height: unset;
      height: auto;
      overflow: visible;
      transition: opacity 0.35s ease;
    }

    .pill.draw {
      opacity: 0.85;
    }

    .pill.status-pending {
      border-left-color: var(--border-strong);
    }

    .icon-wrap {
      width: 26px;
      min-width: 26px;
      height: 26px;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }

    svg {
      width: 24px;
      height: 24px;
    }

    .circle {
      fill: none;
      stroke: var(--brand);
      stroke-width: 3.5;
      stroke-dasharray: 220;
      stroke-dashoffset: 220;
    }

    .check {
      fill: none;
      stroke: var(--brand);
      stroke-width: 4;
      stroke-linecap: round;
      stroke-linejoin: round;
      stroke-dasharray: 50;
      stroke-dashoffset: 50;
    }

    .status-approved .circle,
    .status-approved .check {
      stroke: var(--success);
    }

    .status-edited .circle,
    .status-edited .check {
      stroke: var(--brand-hover);
    }

    .cross {
      fill: none;
      stroke: #d64545;
      stroke-width: 4;
      stroke-linecap: round;
    }

    .pending-ring {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      border: 2px solid var(--border-strong);
      border-top-color: var(--brand);
      animation: spin 0.7s linear infinite;
    }

    .text {
      white-space: normal;
      opacity: 1;
      transform: none;
      padding: 0;
      min-width: 0;
      overflow: visible;
      flex: 1;
    }

    .pill.draw .text {
      opacity: 0;
    }

    .pill:not(.draw) .text,
    .pill.show-text .text,
    .pill.ready .text {
      opacity: 1;
    }

    .pill.show-text .text {
      animation: textReveal 0.35s ease forwards;
    }

    .pill.ready .circle,
    .pill.ready .check {
      stroke-dashoffset: 0;
    }

    .title {
      font-size: 0.8125rem;
      font-weight: 600;
      color: var(--text);
      line-height: 1.35;
    }

    .status-approved .title {
      color: var(--text-secondary);
    }

    .pill-subtitle {
      margin-top: 1px;
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--text-muted);
      line-height: 1.3;
    }

    .status-approved .pill-subtitle {
      color: var(--success);
    }

    .draw .circle {
      animation: drawCircle 0.35s ease forwards;
    }

    .draw .check {
      animation: drawCheck 0.25s ease forwards;
      animation-delay: 0.3s;
    }

    @keyframes drawCircle {
      to { stroke-dashoffset: 0; }
    }

    @keyframes drawCheck {
      to { stroke-dashoffset: 0; }
    }

    @keyframes textReveal {
      from {
        opacity: 0;
        transform: translateX(-6px);
      }
      to {
        opacity: 1;
        transform: translateX(0);
      }
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }
  `],
})
export class DecisionPillComponent implements OnChanges {
  @Input() label = '';
  @Input() status: DecisionStatus = 'approved';
  @Input() animate = false;

  draw = signal(false);
  expanded = signal(false);
  showText = signal(false);

  private timers: ReturnType<typeof setTimeout>[] = [];

  get title(): string {
    if (this.status === 'edited') return 'Editou & aprovou';
    return this.label;
  }

  get subtitle(): string {
    if (this.status === 'edited') return this.label;
    if (this.status === 'approved') return 'Feito.';
    if (this.status === 'rejected') return 'Rejeitado';
    if (this.status === 'pending') return 'Aguardando';
    return '';
  }

  get isReady(): boolean {
    return !this.animate && (this.status === 'approved' || this.status === 'edited');
  }

  ngOnChanges(): void {
    this.clearTimers();
    this.applyState();
  }

  private applyState(): void {
    if (this.status === 'pending' || this.status === 'rejected') {
      this.draw.set(false);
      this.expanded.set(true);
      this.showText.set(true);
      return;
    }

    if (this.animate) {
      this.draw.set(true);
      this.expanded.set(false);
      this.showText.set(false);
      this.timers.push(setTimeout(() => this.expanded.set(true), 550));
      this.timers.push(setTimeout(() => this.showText.set(true), 650));
      return;
    }

    this.draw.set(false);
    this.expanded.set(true);
    this.showText.set(true);
  }

  private clearTimers(): void {
    for (const t of this.timers) clearTimeout(t);
    this.timers = [];
  }
}
