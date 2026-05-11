import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { fmtDec, fmtInt } from '@/shared/lib/format';
import type { SkuHistoryEntry } from '@/entities/sku/schema';

interface Props {
  history: SkuHistoryEntry[];
}

const ANOMALY_THRESHOLD = 0.5; // ±50% deviation
const LOOKBACK_RUNS = 6;

interface MetricDeviation {
  label: string;
  current: number;
  median: number;
  pct: number;
  format: (v: number) => string;
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 0) {
    return ((sorted[mid - 1] ?? 0) + (sorted[mid] ?? 0)) / 2;
  }
  return sorted[mid] ?? 0;
}

// Surfaces when this run's recommendation deviates more than ±50% from the
// running median of the last 6 runs. Without this, an autopilot drift can
// silently triple an order — the planner needs a visible "incele" cue.
export function AnomalyFlagCard({ history }: Props) {
  const { t } = useTranslation();

  const analysis = useMemo(() => {
    const completed = history.filter((h) => h.status === 'completed');
    if (completed.length < 3) return null; // need at least a few runs for a meaningful baseline

    const current = completed[0];
    if (!current) return null;
    const previous = completed.slice(1, 1 + LOOKBACK_RUNS);

    const collectMedian = (
      pickCurrent: (h: SkuHistoryEntry) => number | null | undefined,
    ): { current: number; median: number; pct: number } | null => {
      const curr = pickCurrent(current);
      if (curr == null) return null;
      const past = previous
        .map(pickCurrent)
        .filter((v): v is number => v != null);
      if (past.length === 0) return null;
      const med = median(past);
      if (med === 0) {
        // From 0 → nonzero is an anomaly in itself; expose it as +infinity-style.
        if (curr === 0) return { current: 0, median: 0, pct: 0 };
        return { current: curr, median: 0, pct: Infinity };
      }
      const pct = (curr - med) / Math.abs(med);
      return { current: curr, median: med, pct };
    };

    const order = collectMedian((h) => h.order_qty_rounded ?? null);
    const demand = collectMedian((h) => h.cum_demand_q ?? null);
    const stock = collectMedian((h) => h.starting_stock ?? null);
    if (!order) return null;

    const isAnomalous = Math.abs(order.pct) >= ANOMALY_THRESHOLD;

    // Did the winning model itself change vs previous run?
    const prevModel = previous[0]
      ? `${previous[0].winning_exog} · ${previous[0].winning_y_variant}`
      : null;
    const currModel = `${current.winning_exog} · ${current.winning_y_variant}`;
    const modelChanged = prevModel != null && prevModel !== currModel;

    const deviations: MetricDeviation[] = [];
    if (demand) {
      deviations.push({
        label: t('sku_detail.anomaly.demand'),
        current: demand.current,
        median: demand.median,
        pct: demand.pct,
        format: fmtDec,
      });
    }
    if (stock) {
      deviations.push({
        label: t('sku_detail.anomaly.stock'),
        current: stock.current,
        median: stock.median,
        pct: stock.pct,
        format: fmtDec,
      });
    }

    return {
      isAnomalous,
      order,
      deviations,
      modelChanged,
      prevModel,
      currModel,
      sampleSize: previous.length,
    };
  }, [history, t]);

  if (!analysis || !analysis.isAnomalous) return null;

  const { order, deviations, modelChanged, prevModel, currModel, sampleSize } =
    analysis;

  const direction = order.pct > 0 ? 'up' : 'down';
  const tone =
    direction === 'up'
      ? 'border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200'
      : 'border-sky-300 bg-sky-50 text-sky-900 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-200';

  return (
    <Card className={tone}>
      <CardHeader
        title={t(
          direction === 'up'
            ? 'sku_detail.anomaly.title_up'
            : 'sku_detail.anomaly.title_down',
        )}
        subtitle={t('sku_detail.anomaly.subtitle', {
          sample: sampleSize,
        })}
      />
      <CardBody className="space-y-3">
        <p className="text-sm leading-relaxed">
          {t('sku_detail.anomaly.body', {
            current: fmtInt(order.current),
            median: fmtInt(order.median),
            pct: `${order.pct > 0 ? '+' : ''}${(order.pct * 100).toFixed(0)}%`,
          })}
        </p>

        {deviations.length > 0 && (
          <div>
            <div className="mb-1 text-[11px] font-medium uppercase tracking-wide opacity-70">
              {t('sku_detail.anomaly.contributors')}
            </div>
            <ul className="space-y-1 text-xs">
              {deviations.map((d) => (
                <li
                  key={d.label}
                  className="flex items-center justify-between gap-2 tabular-nums"
                >
                  <span className="opacity-80">{d.label}</span>
                  <span>
                    {d.format(d.current)}{' '}
                    <span className="opacity-60">
                      (medyan {d.format(d.median)},{' '}
                      {Number.isFinite(d.pct)
                        ? `${d.pct > 0 ? '+' : ''}${(d.pct * 100).toFixed(0)}%`
                        : '∞'}
                      )
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {modelChanged && (
          <p className="text-xs">
            <strong className="font-medium">
              {t('sku_detail.anomaly.model_changed')}:
            </strong>{' '}
            <span className="tabular-nums">{prevModel}</span> →{' '}
            <span className="tabular-nums">{currModel}</span>
          </p>
        )}
      </CardBody>
    </Card>
  );
}
