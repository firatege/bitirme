import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useCartStore, cartCount } from './cartStore';
import { cartToCsv, downloadCsv } from './exportCsv';
import {
  groupBySupplier,
  loadSupplierMap,
  UNASSIGNED_SUPPLIER,
  type SupplierGroup,
} from './SupplierGrouping';
import { Button } from '@/shared/ui/Button';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { EmptyState } from '@/shared/ui/EmptyState';
import { fmtInt } from '@/shared/lib/format';
import { cn } from '@/shared/lib/cn';

export function CartView() {
  const items = useCartStore((s) => s.items);
  const update = useCartStore((s) => s.update);
  const remove = useCartStore((s) => s.remove);
  const clear = useCartStore((s) => s.clear);

  const [budgetMode, setBudgetMode] = useState(false);
  const [budget, setBudget] = useState<number>(100_000);
  const [unitCost, setUnitCost] = useState<number>(1);

  const { data: supplierMap = {} } = useQuery({
    queryKey: ['supplier-map'],
    queryFn: loadSupplierMap,
    staleTime: 5 * 60_000,
  });

  const rows = Object.values(items);
  const totalQty = rows.reduce((s, r) => s + r.approved_qty, 0);
  const totalCost = totalQty * unitCost;

  const groups = useMemo(
    () => groupBySupplier(rows, supplierMap),
    [rows, supplierMap],
  );

  const overBudgetSet = useMemo(() => {
    if (!budgetMode) return new Set<string>();
    const sorted = [...rows].sort(
      (a, b) => b.approved_qty - a.approved_qty,
    );
    let used = 0;
    const skipped = new Set<string>();
    for (const item of sorted) {
      const cost = item.approved_qty * unitCost;
      if (used + cost > budget) {
        skipped.add(item.sku);
      } else {
        used += cost;
      }
    }
    return skipped;
  }, [budgetMode, rows, unitCost, budget]);

  if (cartCount(items) === 0) {
    return (
      <EmptyState
        title="Sepet boş"
        description="SKU detay sayfasından 'Sepete Ekle' ile öneri ekleyin."
      />
    );
  }

  const exportAll = () => {
    const ts = new Date().toISOString().slice(0, 10);
    downloadCsv(cartToCsv(rows), `siparis-onerisi-${ts}.csv`);
  };

  const exportGroup = (g: SupplierGroup) => {
    const ts = new Date().toISOString().slice(0, 10);
    const slug = g.supplier.toLowerCase().replace(/\s+/g, '-');
    downloadCsv(cartToCsv(g.items), `siparis-${slug}-${ts}.csv`);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 print:hidden">
        <Button onClick={exportAll}>Tümünü CSV İndir</Button>
        <Button variant="secondary" onClick={() => window.print()}>
          Yazdır / PDF
        </Button>
        <Button variant="secondary" onClick={clear}>
          Sepeti Boşalt
        </Button>
        <span className="ml-auto text-xs text-slate-500">
          {rows.length} SKU · Toplam {fmtInt(totalQty)} adet · Tahmini{' '}
          {fmtInt(totalCost)} TL
        </span>
      </div>

      <Card className="print:hidden">
        <CardHeader
          title="Bütçe Modu"
          subtitle="Bütçeyi aşan satırlar grileşir; en yüksek miktardan başlar"
          action={
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={budgetMode}
                onChange={(e) => setBudgetMode(e.target.checked)}
              />
              Aktif
            </label>
          }
        />
        {budgetMode && (
          <CardBody className="grid grid-cols-2 gap-3 text-sm">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-500">Bütçe (TL)</span>
              <input
                type="number"
                value={budget}
                onChange={(e) => setBudget(Number(e.target.value))}
                className="rounded-md border border-slate-200 px-3 py-1.5 tabular-nums"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-500">Birim maliyet (TL)</span>
              <input
                type="number"
                step="0.1"
                value={unitCost}
                onChange={(e) => setUnitCost(Number(e.target.value))}
                className="rounded-md border border-slate-200 px-3 py-1.5 tabular-nums"
              />
            </label>
            <div className="col-span-2 text-xs text-slate-600">
              {overBudgetSet.size > 0 && (
                <span className="text-orange-700">
                  ⚠ {overBudgetSet.size} satır bütçe dışı kalıyor
                </span>
              )}
            </div>
          </CardBody>
        )}
      </Card>

      <div className="print-only mb-4 hidden print:block">
        <h1 className="text-xl font-semibold">Sipariş Önerisi</h1>
        <p className="text-xs text-slate-500">
          Tarih: {new Date().toLocaleDateString('tr-TR')} · {rows.length} SKU ·{' '}
          {fmtInt(totalQty)} adet
        </p>
      </div>

      <div className="space-y-4">
        {groups.map((g) => (
          <Card key={g.supplier} className="break-inside-avoid">
            <CardHeader
              title={g.supplier}
              subtitle={`${g.items.length} SKU · ${fmtInt(g.totalQty)} adet`}
              action={
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => exportGroup(g)}
                  className="print:hidden"
                >
                  Bu grubu CSV indir
                </Button>
              }
            />
            <CardBody className="p-0">
              <table className="w-full text-sm">
                <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-4 py-2 text-left">SKU</th>
                    <th className="px-4 py-2 text-right">Önerilen</th>
                    <th className="px-4 py-2 text-right">Onaylanan</th>
                    <th className="px-4 py-2 text-left">Not</th>
                    <th className="px-4 py-2 print:hidden"></th>
                  </tr>
                </thead>
                <tbody>
                  {g.items.map((r) => (
                    <tr
                      key={r.sku}
                      className={cn(
                        'border-b border-slate-100 last:border-0',
                        overBudgetSet.has(r.sku) &&
                          'bg-slate-50 text-slate-400',
                      )}
                    >
                      <td className="px-4 py-2 font-mono text-xs">{r.sku}</td>
                      <td className="px-4 py-2 text-right tabular-nums">
                        {fmtInt(r.suggested_qty)}
                      </td>
                      <td className="px-4 py-2 text-right">
                        <input
                          type="number"
                          value={r.approved_qty}
                          onChange={(e) =>
                            update(r.sku, {
                              approved_qty: Number(e.target.value),
                            })
                          }
                          className="w-24 rounded-md border border-slate-200 px-2 py-1 text-right tabular-nums print:border-0"
                        />
                      </td>
                      <td className="px-4 py-2">
                        <input
                          type="text"
                          value={r.note ?? ''}
                          onChange={(e) =>
                            update(r.sku, { note: e.target.value })
                          }
                          placeholder="Not…"
                          className="w-full rounded-md border border-slate-200 px-2 py-1 text-sm print:border-0"
                        />
                      </td>
                      <td className="px-4 py-2 text-right print:hidden">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => remove(r.sku)}
                        >
                          Kaldır
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardBody>
          </Card>
        ))}
      </div>

      {groups.some((g) => g.supplier === UNASSIGNED_SUPPLIER) && (
        <p className="text-xs text-slate-500 print:hidden">
          💡 Tedarikçi atanmamış SKU'lar için{' '}
          <code className="rounded bg-slate-100 px-1">
            dashboard/public/supplier_map.json
          </code>{' '}
          dosyasını düzenleyin.
        </p>
      )}
    </div>
  );
}
