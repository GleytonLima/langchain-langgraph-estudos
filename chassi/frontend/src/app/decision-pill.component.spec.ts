import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { DecisionPillComponent } from './decision-pill.component';

describe('DecisionPillComponent', () => {
  let fixture: ComponentFixture<DecisionPillComponent>;
  let comp: DecisionPillComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [DecisionPillComponent] }).compileComponents();
    fixture = TestBed.createComponent(DecisionPillComponent);
    comp = fixture.componentInstance;
  });

  describe('título e subtítulo', () => {
    it('edited mostra "Editou & aprovou" + label como subtítulo', () => {
      comp.label = 'Abrir relatório';
      comp.status = 'edited';
      expect(comp.title).toBe('Editou & aprovou');
      expect(comp.subtitle).toBe('Abrir relatório');
    });

    it('approved usa o label e subtítulo "Feito."', () => {
      comp.label = 'Abrir relatório';
      comp.status = 'approved';
      expect(comp.title).toBe('Abrir relatório');
      expect(comp.subtitle).toBe('Feito.');
    });

    it('rejected e pending têm subtítulos próprios', () => {
      comp.status = 'rejected';
      expect(comp.subtitle).toBe('Rejeitado');
      comp.status = 'pending';
      expect(comp.subtitle).toBe('Aguardando');
    });
  });

  describe('isReady', () => {
    it('true para approved/edited sem animação', () => {
      comp.animate = false;
      comp.status = 'approved';
      expect(comp.isReady).toBeTrue();
      comp.status = 'edited';
      expect(comp.isReady).toBeTrue();
    });

    it('false quando vai animar ou status não conclusivo', () => {
      comp.animate = true;
      comp.status = 'approved';
      expect(comp.isReady).toBeFalse();
      comp.animate = false;
      comp.status = 'rejected';
      expect(comp.isReady).toBeFalse();
    });
  });

  describe('applyState via ngOnChanges', () => {
    it('pending/rejected expandem o texto sem animar', () => {
      comp.status = 'rejected';
      comp.ngOnChanges();
      expect(comp.draw()).toBeFalse();
      expect(comp.expanded()).toBeTrue();
      expect(comp.showText()).toBeTrue();
    });

    it('sem animação: estado final imediato', () => {
      comp.status = 'approved';
      comp.animate = false;
      comp.ngOnChanges();
      expect(comp.draw()).toBeFalse();
      expect(comp.showText()).toBeTrue();
    });

    it('com animação: desenha e revela o texto via timers', fakeAsync(() => {
      comp.status = 'approved';
      comp.animate = true;
      comp.ngOnChanges();
      expect(comp.draw()).toBeTrue();
      expect(comp.expanded()).toBeFalse();
      expect(comp.showText()).toBeFalse();
      tick(550);
      expect(comp.expanded()).toBeTrue();
      tick(100);
      expect(comp.showText()).toBeTrue();
    }));

    it('limpa os timers ao re-disparar ngOnChanges (sem vazar)', fakeAsync(() => {
      comp.status = 'approved';
      comp.animate = true;
      comp.ngOnChanges();
      comp.ngOnChanges(); // re-dispara: clearTimers + reaplica
      tick(650);
      expect(comp.showText()).toBeTrue();
    }));
  });

  it('renderiza o título no template', () => {
    comp.label = 'Abrir relatório';
    comp.status = 'approved';
    fixture.detectChanges();
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Abrir relatório');
  });
});
