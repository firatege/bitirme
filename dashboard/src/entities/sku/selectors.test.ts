import { describe, it, expect } from 'vitest';
import { urgencyOf } from './selectors';

describe('urgencyOf', () => {
  it('CRITICAL when p3m >= 0.5', () => {
    expect(urgencyOf({ horizon: 'Full', exog: 'ETS', y_variant: 'RF', phase: 'PRE', p_stockout_3m: 0.6 })).toBe('CRITICAL');
  });
  it('HIGH when p3m in [0.25, 0.5)', () => {
    expect(urgencyOf({ horizon: 'Full', exog: 'ETS', y_variant: 'RF', phase: 'PRE', p_stockout_3m: 0.3 })).toBe('HIGH');
  });
  it('MEDIUM on p6m >= 0.25 only', () => {
    expect(urgencyOf({ horizon: 'Full', exog: 'ETS', y_variant: 'RF', phase: 'PRE', p_stockout_6m: 0.3 })).toBe('MEDIUM');
  });
  it('UNKNOWN when no winning', () => {
    expect(urgencyOf(null)).toBe('UNKNOWN');
  });
});
