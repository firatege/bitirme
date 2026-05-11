import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useCartStore, cartCount } from './cartStore';
import { cartToCsv, downloadCsv } from './exportCsv';
import {
  groupBySupplier,
  loadSupplierMap,
  type SupplierGroup,
} from './SupplierGrouping';
import { Button } from '@/shared/ui/Button';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { EmptyState } from '@/shared/ui/EmptyState';
import { fmtInt, fmtPct } from '@/shared/lib/format';
import { cn } from '@/shared/lib/cn';
import {
  approxRescaleCumDemand,
  recomputeOrderQty,
} from '@/entities/recommendation/policy';

export function CartView() {
  const items = useCartStore((s) => s.items);
  const update = useCartStore((s) => s.update);
  const remove = useCartStore((s) => s.remove);
  const clear = useCartStore((s) => s.clear);

  const [budgetMode, setBudgetMode] = useState(false);
  const [budget, setBudget] = useState<number>(100_000);
  const [unitCost, setUnitCost] = useState<number>(1);

  // Portfolio-wide what-if knobs. Null means "use each item's original q/H".
  const [sensitivityOn, setSensitivityOn] = useState(false);
  const [qOverride, setQOverride] = useState<number>(0.5);
  const [hCoverOverride, setHCoverOverride] = useState<number>(6);

  const { data: supplierMap = {} } = useQuery({
    queryKey: ['supplier-map'],
    queryFn: loadSupplierMap,
    staleTime: 5 * 60_000,
  });

  const rows = Object.values(items);

  // Apply the portfolio-wide what-if to compute a preview qty per SKU. We
  // don't mutate approved_qty — the slider preview is non-destructive so
  // the user can compare and choose to "apply" if they like the result.
  const previewByeSku = useMemo(() => {
    if (!sensitivityOn) return new Map<string, number>();
    const m = new Map<string, number>();
    for (const r of rows) {
      const p = r.policy;
      if (!p) continue;
      const adjustedDemand = approxRescaleCumDemand({
        origCumDemandQ: p.cum_demand_q,
        origQ: p.q_target,
        origHCover: p.h_cover,
        newQ: qOverride,
        newHCover: hCoverOverride,
      });
      const { rounded } = recomputeOrderQty({
        startingStock: p.starting_stock,
        cumDemandQ: adjustedDemand,
        moq: p.moq,
        lotSize: p.lot_size,
      });
      m.set(r.sku, rounded);
    }
    return m;
  }, [sensitivityOn, rows, qOverride, hCoverOverride]);

  const applySensitivity = () => {
    for (const [sku, qty] of previewByeSku) {
      update(sku, { approved_qty: qty });
    }
    setSensitivityOn(false);
  };

  const skusMissingContext = sensitivityOn
    ? rows.filter((r) => !r.policy).length
    : 0;

  const totalQty = rows.reduce(
    (s, r) => s + (previewByeSku.get(r.sku) ?? r.approved_qty),
    0,
  );
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
        <span className="ml-auto text-xs text-slate-500 dark:text-stone-400">
          {rows.length} SKU · {fmtInt(totalQty)} adet · ~{fmtInt(totalCost)} TL
        </span>
      </div>

      <Card className="print:hidden">
        <CardHeader
          title="Senaryo (ne-eğer)"
          subtitle="Hizmet seviyesi ve kapsama ufkunu portföy genelinde değiştir; önizleme grileşmiş satırlarda görünür"
          action={
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={sensitivityOn}
                onChange={(e) => setSensitivityOn(e.target.checked)}
              />
              Aktif
            </label>
          }
        />
        {sensitivityOn && (
          <CardBody className="space-y-3 text-sm">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <div className="mb-1 flex items-center justify-between text-xs">
                  <span className="text-slate-600 dark:text-stone-300">
                    Hizmet seviyesi (q):{' '}
                    <strong>{fmtPct(qOverride)}</strong>
                  </span>
                </div>
                <input
                  type="range"
                  min={0.5}
                  max={0.99}
                  step={0.01}
                  value={qOverride}
                  onChange={(e) => setQOverride(Number(e.target.value))}
                  className="w-full"
                />
              </div>
              <div>
                <div className="mb-1 flex items-center justify-between text-xs">
                  <span className="text-slate-600 dark:text-stone-300">
                    Kapsama ufku:{' '}
                    <strong>{hCoverOverride} ay</strong>
                  </span>
                </div>
                <input
                  type="range"
                  min={1}
                  max={18}
                  step={1}
                  value={hCoverOverride}
                  onChange={(e) =>
                    setHCoverOverride(Number(e.target.value))
                  }
                  className="w-full"
                />
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Button size="sm" onClick={applySensitivity}>
                Tüm satırlara uygula
              </Button>
              {skusMissingContext > 0 && (
                <span className="ml-auto text-amber-700 dark:text-amber-300">
                  {skusMissingContext} satırda politika bağlamı yok
                </span>
              )}
            </div>
          </CardBody>
        )}
      </Card>

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
                className="rounded-md border border-slate-200 bg-white px-3 py-1.5 tabular-nums dark:border-surface-line dark:bg-surface-2"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-500">Birim maliyet (TL)</span>
              <input
                type="number"
                step="0.1"
                value={unitCost}
                onChange={(e) => setUnitCost(Number(e.target.value))}
                className="rounded-md border border-slate-200 bg-white px-3 py-1.5 tabular-nums dark:border-surface-line dark:bg-surface-2"
              />
            </label>
            <div className="col-span-2 text-xs text-slate-600">
              {overBudgetSet.size > 0 && (
                <span className="text-orange-700">
                  {overBudgetSet.size} satır bütçe dışı kalıyor
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
                <thead className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500 dark:border-surface-line dark:bg-surface-2/30 dark:text-stone-400">
                  <tr>
                    <th className="px-4 py-2 text-left font-medium">SKU</th>
                    <th className="px-4 py-2 text-right font-medium">Önerilen</th>
                    {sensitivityOn && (
                      <th className="px-4 py-2 text-right font-medium text-amber-700 dark:text-amber-300">
                        Önizleme
                      </th>
                    )}
                    <th className="px-4 py-2 text-right font-medium">Onaylanan</th>
                    <th className="px-4 py-2 text-left font-medium">Not</th>
                    <th className="px-4 py-2 print:hidden"></th>
                  </tr>
                </thead>
                <tbody>
                  {g.items.map((r) => (
                    <tr
                      key={r.sku}
                      className={cn(
                        'border-b border-slate-100 transition-colors last:border-0 hover:bg-brand-50/40 dark:border-surface-line/50 dark:hover:bg-surface-2/40',
                        overBudgetSet.has(r.sku) &&
                          'bg-slate-50 text-slate-400 dark:bg-surface-2/30 dark:text-stone-200/30',
                      )}
                    >
                      <td className="px-4 py-2 font-mono text-xs text-slate-800 dark:text-stone-100">
                        {r.sku}
                      </td>
                      <td className="px-4 py-2 text-right font-mono tabular-nums text-slate-700 dark:text-stone-300">
                        {fmtInt(r.suggested_qty)}
                      </td>
                      {sensitivityOn && (
                        <td className="px-4 py-2 text-right font-mono tabular-nums">
                          {previewByeSku.has(r.sku) ? (
                            <PreviewCell
                              preview={previewByeSku.get(r.sku) ?? 0}
                              baseline={r.approved_qty}
                            />
                          ) : (
                            <span className="text-slate-400 dark:text-stone-500">
                              —
                            </span>
                          )}
                        </td>
                      )}
                      <td className="px-4 py-2 text-right">
                        <input
                          type="number"
                          value={r.approved_qty}
                          onChange={(e) =>
                            update(r.sku, {
                              approved_qty: Number(e.target.value),
                            })
                          }
                          className="w-24 rounded-md border border-slate-200 bg-white px-2 py-1 text-right font-mono tabular-nums dark:border-surface-line dark:bg-surface-2 print:border-0"
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
                          className="w-full rounded-md border border-slate-200 bg-white px-2 py-1 text-sm dark:border-surface-line dark:bg-surface-2 print:border-0"
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

    </div>
  );
}

function PreviewCell({
  preview,
  baseline,
}: {
  preview: number;
  baseline: number;
}) {
  const diff = preview - baseline;
  const tone =
    diff === 0
      ? 'text-slate-500 dark:text-stone-400'
      : diff > 0
        ? 'text-amber-700 dark:text-amber-300'
        : 'text-emerald-700 dark:text-emerald-300';
  const arrow = diff === 0 ? '=' : diff > 0 ? '▲' : '▼';
  return (
    <span className={tone}>
      {fmtInt(preview)}{' '}
      <span className="ml-1 text-[10px]">
        {arrow} {diff > 0 ? '+' : ''}
        {fmtInt(diff)}
      </span>
    </span>
  );
}
