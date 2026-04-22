import type { CartItem } from './cartStore';

export function cartToCsv(items: CartItem[]): string {
  const header = ['sku', 'suggested_qty', 'approved_qty', 'note', 'added_at'];
  const rows = items.map((i) =>
    [
      escapeCsv(i.sku),
      i.suggested_qty,
      i.approved_qty,
      escapeCsv(i.note ?? ''),
      i.added_at,
    ].join(','),
  );
  return [header.join(','), ...rows].join('\n');
}

function escapeCsv(v: string): string {
  if (v.includes(',') || v.includes('"') || v.includes('\n')) {
    return `"${v.replace(/"/g, '""')}"`;
  }
  return v;
}

export function downloadCsv(content: string, filename: string): void {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
