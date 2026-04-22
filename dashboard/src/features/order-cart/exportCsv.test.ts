import { describe, it, expect } from 'vitest';
import { cartToCsv } from './exportCsv';

describe('cartToCsv', () => {
  it('produces header + rows', () => {
    const csv = cartToCsv([
      {
        sku: 'A1',
        suggested_qty: 100,
        approved_qty: 80,
        note: 'acil',
        added_at: '2026-01-01T00:00:00Z',
      },
    ]);
    const lines = csv.split('\n');
    expect(lines[0]).toBe('sku,suggested_qty,approved_qty,note,added_at');
    expect(lines[1]).toBe('A1,100,80,acil,2026-01-01T00:00:00Z');
  });

  it('escapes commas and quotes', () => {
    const csv = cartToCsv([
      {
        sku: 'B,2',
        suggested_qty: 50,
        approved_qty: 50,
        note: 'with "quote"',
        added_at: '2026-01-01',
      },
    ]);
    expect(csv).toContain('"B,2"');
    expect(csv).toContain('"with ""quote"""');
  });
});
