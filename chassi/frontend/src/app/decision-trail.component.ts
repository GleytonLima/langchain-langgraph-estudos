import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DecisionPillComponent, DecisionStatus } from './decision-pill.component';

export type { DecisionStatus };

export interface TrailDecision {
  id: string;
  label: string;
  status: DecisionStatus;
  animate?: boolean;
}

@Component({
  selector: 'app-decision-trail',
  standalone: true,
  imports: [CommonModule, DecisionPillComponent],
  template: `
    <aside class="rail" aria-label="Trilho de decisões">
      <header class="rail-header">
        <h2>Decisões</h2>
        @if (pendingCount > 0) {
          <span class="badge">{{ pendingCount }}</span>
        }
      </header>

      @if (decisions.length === 0 && pendingCount === 0) {
        <p class="rail-empty">As aprovações aparecem aqui.</p>
      }

      <ol class="rail-list">
        @for (d of decisions; track d.id) {
          <li>
            <app-decision-pill
              [label]="d.label"
              [status]="d.status"
              [animate]="d.animate ?? false"
            />
          </li>
        }
      </ol>
    </aside>
  `,
  styles: [`
    .rail {
      width: 100%;
    }

    .rail-header {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 20px;
    }

    .rail-header h2 {
      margin: 0;
      font-size: 0.8125rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-secondary);
    }

    .badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 20px;
      height: 20px;
      padding: 0 6px;
      border-radius: 999px;
      background: var(--text);
      color: var(--text-inverse);
      font-size: 0.6875rem;
      font-weight: 700;
    }

    .rail-empty {
      margin: 0;
      font-size: 0.8125rem;
      color: var(--text-muted);
      line-height: 1.5;
    }

    .rail-list {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
  `],
})
export class DecisionTrailComponent {
  @Input() decisions: TrailDecision[] = [];
  @Input() pendingCount = 0;
}
