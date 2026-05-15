import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { fmtPct } from '@/shared/lib/format';
import type {
  SkuTimeseriesPoint,
  SkuPredictionPoint,
} from '@/entities/sku/schema';

interface Props {
  timeseries: SkuTimeseriesPoint[] | undefined;
  predictions: SkuPredictionPoint[] | undefined;
}

// wMAPE = sum(|e|) / sum(y) — weighted by actual volume so zero months
// don't create division-by-zero explosions (classic MAPE on intermittent
// demand can exceed 1000% even when the model is reasonable).
function wmape(actuals: number[], preds: number[]): number | null {
  let sumError = 0;
  let sumActual = 0;
  for (let i = 0; i < actuals.length; i++) {
    const y = actuals[i];
    const yhat = preds[i];
    if (y == null || yhat == null) continue;
    sumError += Math.abs(y - yhat);
    sumActual += Math.abs(y);
  }
  if (sumActual < 1e-9) return null;
  return sumError / sumActual;
}

// MASE = MAE_model / MAE_naive — scale-free, <1 means better than naive.
function mase(
  actuals: number[],
  preds: number[],
  naivePreds: number[],
): number | null {
  if (actuals.length === 0) return null;
  const modelMae =
    actuals.reduce((s, y, i) => s + Math.abs(y - (preds[i] ?? 0)), 0) /
    actuals.length;
  const naiveMae =
    actuals.reduce((s, y, i) => s + Math.abs(y - (naivePreds[i] ?? 0)), 0) /
    actuals.length;
  if (naiveMae < 1e-9) return null;
  return modelMae / naiveMae;
}

interface Comparison {
  pipelineWmape: number | null;
  naiveWmape: number | null;
  seasonalWmape: number | null;
  maseVsNaive: number | null;
  // Positive = pipeline is better; negative = pipeline is worse.
  improvementVsNaive: number | null;
  improvementVsSeasonal: number | null;
}

function buildComparison(
  history: SkuTimeseriesPoint[],
  predictions: SkuPredictionPoint[],
): Comparison | null {
  // Test rows: months where the model produced a prediction AND we know y.
  const testRows = predictions.filter(
    (p) => p.y != null && Number.isFinite(p.y),
  );
  if (testRows.length === 0) return null;

  // Index historical y by YYYY-MM for naive lookups.
  const histByMonth = new Map<string, number>();
  for (const p of history) {
    if (p.y != null) histByMonth.set(p.ds.slice(0, 7), p.y);
  }

  const actuals: number[] = [];
  const pipelinePreds: number[] = [];
  const naivePreds: number[] = [];
  const seasonalPreds: number[] = [];

  for (const row of testRows) {
    const dt = new Date(row.ds);
    if (Number.isNaN(dt.getTime())) continue;

    // Naive baseline: average of last 3 observed months before this row's ds.
    const lastThree: number[] = [];
    for (let back = 1; back <= 3; back++) {
      const d = new Date(dt);
      d.setUTCMonth(d.getUTCMonth() - back);
      const key = d.toISOString().slice(0, 7);
      const v = histByMonth.get(key);
      if (v != null) lastThree.push(v);
    }
    if (lastThree.length === 0) continue;
    const naive =
      lastThree.reduce((s, v) => s + v, 0) / lastThree.length;

    // Seasonal naive baseline: same month a year ago.
    const seasonalDate = new Date(dt);
    seasonalDate.setUTCFullYear(seasonalDate.getUTCFullYear() - 1);
    const seasonalKey = seasonalDate.toISOString().slice(0, 7);
    const seasonal = histByMonth.get(seasonalKey);

    actuals.push(row.y as number);
    pipelinePreds.push(row.yhat);
    naivePreds.push(naive);
    seasonalPreds.push(seasonal ?? naive); // fall back if no Y/Y data
  }

  if (actuals.length === 0) return null;

  const pipelineWmape = wmape(actuals, pipelinePreds);
  const naiveWmape = wmape(actuals, naivePreds);
  const seasonalWmape = wmape(actuals, seasonalPreds);
  const maseVsNaive = mase(actuals, pipelinePreds, naivePreds);

  const improvement = (baseline: number | null): number | null => {
    if (
      baseline == null ||
      pipelineWmape == null ||
      Math.abs(baseline) < 1e-9
    ) {
      return null;
    }
    return (baseline - pipelineWmape) / baseline;
  };

  return {
    pipelineWmape,
    naiveWmape,
    seasonalWmape,
    maseVsNaive,
    improvementVsNaive: improvement(naiveWmape),
    improvementVsSeasonal: improvement(seasonalWmape),
  };
}

export function BaselineComparisonCard({ timeseries, predictions }: Props) {
  const { t } = useTranslation();
  const cmp = useMemo(
    () => buildComparison(timeseries ?? [], predictions ?? []),
    [timeseries, predictions],
  );

  if (!cmp || cmp.pipelineWmape == null) return null;

  const headline =
    cmp.improvementVsNaive != null
      ? cmp.improvementVsNaive > 0
        ? t('sku_detail.baseline.headline_better', {
            pct: `${(cmp.improvementVsNaive * 100).toFixed(0)}%`,
          })
        : t('sku_detail.baseline.headline_worse', {
            pct: `${Math.abs(cmp.improvementVsNaive * 100).toFixed(0)}%`,
          })
      : t('sku_detail.baseline.headline_unknown');

  return (
    <Card>
      <CardHeader
        title={t('sku_detail.baseline.title')}
        subtitle={t('sku_detail.baseline.subtitle')}
      />
      <CardBody className="space-y-3">
        <p className="text-sm text-slate-700 dark:text-stone-200">
          {headline}
        </p>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <BaselineCell
            label={t('sku_detail.baseline.pipeline')}
            value={cmp.pipelineWmape}
            improvement={null}
            tone="primary"
          />
          <BaselineCell
            label={t('sku_detail.baseline.naive')}
            value={cmp.naiveWmape}
            improvement={cmp.improvementVsNaive}
          />
          <BaselineCell
            label={t('sku_detail.baseline.seasonal')}
            value={cmp.seasonalWmape}
            improvement={cmp.improvementVsSeasonal}
          />
        </div>
        {cmp.maseVsNaive != null && (
          <p className="text-xs text-slate-500 dark:text-stone-400">
            MASE = {cmp.maseVsNaive.toFixed(2)}{' '}
            {cmp.maseVsNaive < 1
              ? '— naive\'den iyi'
              : '— naive\'den kötü'}
          </p>
        )}
      </CardBody>
    </Card>
  );
}

function BaselineCell({
  label,
  value,
  improvement,
  tone = 'neutral',
}: {
  label: string;
  value: number | null;
  improvement: number | null;
  tone?: 'neutral' | 'primary';
}) {
  const cardClasses =
    tone === 'primary'
      ? 'border-brand-200 bg-brand-50 dark:border-brand-500/30 dark:bg-brand-500/10'
      : 'border-slate-200 bg-slate-50 dark:border-surface-line dark:bg-surface-2/40';
  const valueClasses =
    tone === 'primary'
      ? 'text-brand-800 dark:text-brand-200'
      : 'text-slate-900 dark:text-stone-50';

  let improvementText: string | null = null;
  let improvementTone = 'text-slate-500 dark:text-stone-400';
  if (improvement != null && Number.isFinite(improvement)) {
    const pct = improvement * 100;
    const sign = pct > 0 ? '+' : '';
    improvementText = `${sign}${pct.toFixed(0)}%`;
    improvementTone =
      pct > 0
        ? 'text-emerald-700 dark:text-emerald-300'
        : 'text-rose-700 dark:text-rose-300';
  }

  return (
    <div className={`rounded-lg border p-3 ${cardClasses}`}>
      <div className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-stone-400">
        {label}
      </div>
      <div className={`mt-1 text-2xl font-medium tabular-nums ${valueClasses}`}>
        {value == null ? '—' : fmtPct(value)}
      </div>
      {improvementText && (
        <div className={`mt-1 text-xs tabular-nums ${improvementTone}`}>
          {improvementText}
        </div>
      )}
    </div>
  );
}
