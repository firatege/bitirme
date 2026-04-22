import { describe, it, expect } from 'vitest';
import { recomputeOrderQty, roundMoqLot } from './policy';

describe('roundMoqLot', () => {
  it('returns 0 for non-positive raw', () => {
    expect(roundMoqLot(0, 100, 50)).toBe(0);
    expect(roundMoqLot(-5, 100, 50)).toBe(0);
  });

  it('lifts to MOQ floor when raw below MOQ', () => {
    expect(roundMoqLot(30, 100, 50)).toBe(100);
  });

  it('rounds up to lot granularity above MOQ', () => {
    expect(roundMoqLot(470, 100, 50)).toBe(500);
    expect(roundMoqLot(501, 100, 50)).toBe(550);
  });

  it('handles zero lot by ceiling', () => {
    expect(roundMoqLot(123.2, 0, 0)).toBe(124);
  });
});

describe('recomputeOrderQty', () => {
  it('subtracts stock from cum demand', () => {
    const r = recomputeOrderQty({
      startingStock: 150,
      cumDemandQ: 620,
      moq: 100,
      lotSize: 50,
    });
    expect(r.raw).toBe(470);
    expect(r.rounded).toBe(500);
  });

  it('floors raw at zero when stock covers demand', () => {
    const r = recomputeOrderQty({
      startingStock: 800,
      cumDemandQ: 620,
      moq: 100,
      lotSize: 50,
    });
    expect(r.raw).toBe(0);
    expect(r.rounded).toBe(0);
  });
});
