import { describe, it, expect } from 'vitest';
import { groupBySupplier, UNASSIGNED_SUPPLIER } from './SupplierGrouping';

const mk = (sku: string, qty: number) => ({
  sku,
  suggested_qty: qty,
  approved_qty: qty,
  added_at: '2026-01-01',
});

describe('groupBySupplier', () => {
  it('groups items by supplier and sums quantities', () => {
    const groups = groupBySupplier(
      [mk('A1', 100), mk('A2', 50), mk('B1', 200)],
      { A1: 'Supplier X', A2: 'Supplier X', B1: 'Supplier Y' },
    );
    expect(groups).toHaveLength(2);
    const x = groups.find((g) => g.supplier === 'Supplier X');
    const y = groups.find((g) => g.supplier === 'Supplier Y');
    expect(x?.items).toHaveLength(2);
    expect(x?.totalQty).toBe(150);
    expect(y?.totalQty).toBe(200);
  });

  it('puts unmapped SKUs into Belirsiz at the end', () => {
    const groups = groupBySupplier(
      [mk('A1', 100), mk('Unknown', 50)],
      { A1: 'X' },
    );
    expect(groups[groups.length - 1]?.supplier).toBe(UNASSIGNED_SUPPLIER);
  });

  it('sorts named suppliers alphabetically', () => {
    const groups = groupBySupplier(
      [mk('a', 1), mk('b', 1), mk('c', 1)],
      { a: 'Beta', b: 'Alpha', c: 'Gamma' },
    );
    expect(groups.map((g) => g.supplier)).toEqual(['Alpha', 'Beta', 'Gamma']);
  });
});
