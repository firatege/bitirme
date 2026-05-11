import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { fmtDec, fmtInt } from '@/shared/lib/format';
import type { SkuHistoryEntry } from '@/entities/sku/schema';

interface Props {
  history: SkuHistoryEntry[];
}

interface DeltaRow {
  label: string;
  current: number | null;
  previous: number | null;
  format: (v: number | null) => string;
  /** When true, increase is good (e.g. cum_demand_q higher = more we expect to sell). */
  higherIsBetter?: boolean;
}

// Compares the latest completed run vs the run before it. Helps the user
// answer "neden bu ay öneri değişti": sipariş değişti çünkü ya talep tahmini
// değişti, ya stok değişti, ya da model bambaşka bir kombinasyon seçti.
export function RunDeltaCard({ history }: Props) {
  const { t } = useTranslation();

  const [current, previous] = useMemo(() => {
    const completed = history.filter((h) => h.status === 'completed');
    return [completed[0] ?? null, completed[1] ?? null];
  }, [history]);

  if (!current || !previous) return null;

  const rows: DeltaRow[] = [
    {
      label: t('sku_detail.delta.order'),
      current: current.order_qty_rounded ?? null,
      previous: previous.order_qty_rounded ?? null,
      format: (v) => fmtInt(v),
    },
    {
      label: t('sku_detail.delta.demand'),
      current: current.cum_demand_q ?? null,
      previous: previous.cum_demand_q ?? null,
      format: (v) => fmtDec(v),
    },
    {
      label: t('sku_detail.delta.stock'),
      current: current.starting_stock ?? null,
      previous: previous.starting_stock ?? null,
      format: (v) => fmtDec(v),
    },
    {
      label: t('sku_detail.delta.mae'),
      current: current.winning_mae ?? null,
      previous: previous.winning_mae ?? null,
      format: (v) => fmtDec(v),
      higherIsBetter: false,
    },
  ];

  const modelChanged =
    `${current.winning_exog} · ${current.winning_y_variant}` !==
    `${previous.winning_exog} · ${previous.winning_y_variant}`;

  return (
    <Card>
      <CardHeader
        title={t('sku_detail.delta.title')}
        subtitle={t('sku_detail.delta.subtitle', {
          current: current.run_id,
          previous: previous.run_id,
        })}
      />
      <CardBody className="space-y-3">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
          {rows.map((r) => (
            <DeltaCell key={r.label} {...r} />
          ))}
        </div>

        {modelChanged && (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
            <strong className="font-medium">
              {t('sku_detail.delta.model_changed')}:
            </strong>{' '}
            <span className="tabular-nums">
              {previous.winning_exog} · {previous.winning_y_variant}
            </span>
            {' → '}
            <span className="tabular-nums">
              {current.winning_exog} · {current.winning_y_variant}
            </span>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function DeltaCell({
  label,
  current,
  previous,
  format,
  higherIsBetter,
}: DeltaRow) {
  const hasBoth = current != null && previous != null;
  const diff = hasBoth ? current - previous : null;
  const pctChange =
    hasBoth && previous !== 0 ? (diff! / Math.abs(previous)) * 100 : null;

  let tone: 'neutral' | 'good' | 'bad' = 'neutral';
  if (diff != null && diff !== 0) {
    const isIncrease = diff > 0;
    const good = higherIsBetter === undefined ? null : isIncrease === higherIsBetter;
    if (good === true) tone = 'good';
    else if (good === false) tone = 'bad';
  }

  const toneClass = {
    neutral: 'text-slate-600 dark:text-stone-300',
    good: 'text-emerald-700 dark:text-emerald-300',
    bad: 'text-rose-700 dark:text-rose-300',
  }[tone];

  const arrow = diff == null || diff === 0 ? '—' : diff > 0 ? '▲' : '▼';

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-surface-line dark:bg-surface-2/40">
      <div className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-stone-400">
        {label}
      </div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className="text-xl font-medium tabular-nums text-slate-900 dark:text-stone-50">
          {format(current)}
        </span>
        <span className="text-[11px] tabular-nums text-slate-400 dark:text-stone-500">
          ← {format(previous)}
        </span>
      </div>
      <div className={`mt-1 text-xs tabular-nums ${toneClass}`}>
        {arrow}{' '}
        {diff == null
          ? '—'
          : `${diff > 0 ? '+' : ''}${format(diff)}${
              pctChange != null
                ? ` (${pctChange > 0 ? '+' : ''}${pctChange.toFixed(1)}%)`
                : ''
            }`}
      </div>
    </div>
  );
}
