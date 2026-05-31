import { ComponentFixture, TestBed } from '@angular/core/testing';
import { DecisionTrailComponent, TrailDecision } from './decision-trail.component';

describe('DecisionTrailComponent', () => {
  let fixture: ComponentFixture<DecisionTrailComponent>;
  let comp: DecisionTrailComponent;

  function text(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [DecisionTrailComponent] }).compileComponents();
    fixture = TestBed.createComponent(DecisionTrailComponent);
    comp = fixture.componentInstance;
  });

  it('mostra o estado vazio sem decisões nem pendências', () => {
    fixture.detectChanges();
    expect(text()).toContain('As aprovações aparecem aqui.');
  });

  it('mostra o badge com a contagem de pendências', () => {
    comp.pendingCount = 3;
    fixture.detectChanges();
    const badge = (fixture.nativeElement as HTMLElement).querySelector('.badge');
    expect(badge?.textContent?.trim()).toBe('3');
  });

  it('renderiza uma pill por decisão', () => {
    const decisions: TrailDecision[] = [
      { id: 'a', label: 'Abrir relatório', status: 'approved' },
      { id: 'b', label: 'Enviar', status: 'rejected' },
    ];
    comp.decisions = decisions;
    fixture.detectChanges();
    const pills = (fixture.nativeElement as HTMLElement).querySelectorAll('app-decision-pill');
    expect(pills.length).toBe(2);
    expect(text()).toContain('Abrir relatório');
  });

  it('não mostra o estado vazio quando há pendências', () => {
    comp.pendingCount = 1;
    fixture.detectChanges();
    expect(text()).not.toContain('As aprovações aparecem aqui.');
  });
});
