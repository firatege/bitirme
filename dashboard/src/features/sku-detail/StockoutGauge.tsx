import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { fmtMonths, fmtPct } from '@/shared/lib/format';

function Bar({ value }: { value: number | null | undefined }) {
  const pct = Math.min(1, Math.max(0, value ?? 0));
  const tone =
    pct >= 0.5 ? 'bg-red-500' : pct >= 0.25 ? 'bg-orange-500' : 'bg-green-500';
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
      <div
        className={`h-full ${tone}`}
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
          <div className="flex justify-between text-xs text-slate-600">
            <span>3 ay içinde</span>
            <span className="tabular-nums font-semibold">{fmtPct(p3m)}</span>
          </div>
          <div className="mt-1">
            <Bar value={p3m} />
          </div>
        </div>
        <div>
          <div className="flex justify-between text-xs text-slate-600">
            <span>6 ay içinde</span>
            <span className="tabular-nums font-semibold">{fmtPct(p6m)}</span>
          </div>
          <div className="mt-1">
            <Bar value={p6m} />
          </div>
        </div>
        <div className="rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">
          Beklenen stockout zamanı:{' '}
          <span className="font-semibold tabular-nums">{fmtMonths(eT)}</span>
        </div>
      </CardBody>
    </Card>
  );
}
