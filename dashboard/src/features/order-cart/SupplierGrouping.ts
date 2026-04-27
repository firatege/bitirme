import type { CartItem } from './cartStore';

export const UNASSIGNED_SUPPLIER = 'Belirsiz';

export interface SupplierGroup {
  supplier: string;
  items: CartItem[];
  totalQty: number;
}

export function groupBySupplier(
  items: CartItem[],
  supplierMap: Record<string, string>,
): SupplierGroup[] {
  const buckets = new Map<string, CartItem[]>();
  for (const item of items) {
    const supplier = supplierMap[item.sku] ?? UNASSIGNED_SUPPLIER;
    const existing = buckets.get(supplier) ?? [];
    existing.push(item);
    buckets.set(supplier, existing);
  }
  return [...buckets.entries()]
    .map(([supplier, items]) => ({
      supplier,
      items,
      totalQty: items.reduce((s, i) => s + i.approved_qty, 0),
    }))
    .sort((a, b) => {
      if (a.supplier === UNASSIGNED_SUPPLIER) return 1;
      if (b.supplier === UNASSIGNED_SUPPLIER) return -1;
      return a.supplier.localeCompare(b.supplier);
    });
}

export async function loadSupplierMap(): Promise<Record<string, string>> {
  try {
    const res = await fetch('/supplier_map.json', { cache: 'no-store' });
    if (!res.ok) return {};
    const payload = (await res.json()) as { suppliers?: Record<string, string> };
    return payload.suppliers ?? {};
  } catch {
    return {};
  }
}
