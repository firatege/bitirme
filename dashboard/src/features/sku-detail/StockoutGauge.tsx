import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { fmtMonths, fmtPct } from '@/shared/lib/format';

function Bar({ value }: { value: number | null | undefined }) {
  const pct = Math.min(1, Math.max(0, value ?? 0));
  const tone =
    pct >= 0.5 ? 'bg-rose-500' : pct >= 0.25 ? 'bg-orange-500' : 'bg-teal-500';
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-surface-2">
      <div
        className={`h-full transition-all ${tone}`}
        style={{ width: `${pct * 100}%` }}
      />
    </div>
  );
}

export function StockoutGauge({
  p3m,
  p6m,
  eT,
}: {
  p3m: number | null | undefined;
  p6m: number | null | undefined;
  eT: number | null | undefined;
}) {
  return (
    <Card>
      <CardHeader
        title="Stockout Riski"
        subtitle="Bootstrap simülasyonlarına göre"
      />
      <CardBody className="space-y-4">
        <div>
          <div className="flex justify-between text-xs text-slate-600 dark:text-stone-300">
            <span>3 ay içinde</span>
            <span className="font-mono font-semibold tabular-nums">{fmtPct(p3m)}</span>
          </div>
          <div className="mt-1.5">
            <Bar value={p3m} />
          </div>
        </div>
        <div>
          <div className="flex justify-between text-xs text-slate-600 dark:text-stone-300">
            <span>6 ay içinde</span>
            <span className="font-mono font-semibold tabular-nums">{fmtPct(p6m)}</span>
          </div>
          <div className="mt-1.5">
            <Bar value={p6m} />
          </div>
        </div>
        <div className="flex items-center justify-between border-t border-slate-200 pt-3 text-xs text-slate-500 dark:border-surface-line dark:text-stone-400">
          <span>Beklenen stockout zamanı</span>
          <span className="font-medium tabular-nums text-slate-700 dark:text-stone-200">
            {fmtMonths(eT)}
          </span>
        </div>
      </CardBody>
    </Card>
  );
}
