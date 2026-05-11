import { useMemo } from 'react';
import {
  CartesianGrid,
  Line,
  Area,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Legend,
} from 'recharts';
import { useTranslation } from 'react-i18next';
import type { TooltipProps } from 'recharts';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { Skeleton } from '@/shared/ui/Skeleton';
import { useThemeStore } from '@/shared/lib/theme';
import type {
  SkuTimeseriesPoint,
  SkuPredictionPoint,
} from '@/entities/sku/schema';

interface Props {
  points: SkuTimeseriesPoint[] | undefined;
  predictions?: SkuPredictionPoint[] | undefined;
  isLoading?: boolean;
}

interface ChartRow {
  date: string;
  sales: number | null;
  orders: number | null;
  yhat: number | null;
  /** Recharts supports tuple [lo, hi] dataKey for Area to render a band. */
  pi80: [number, number] | null;
  pi95: [number, number] | null;
}

function mergeSeries(
  history: SkuTimeseriesPoint[],
  predictions: SkuPredictionPoint[],
): ChartRow[] {
  const byMonth = new Map<string, ChartRow>();

  const blank = (date: string): ChartRow => ({
    date,
    sales: null,
    orders: null,
    yhat: null,
    pi80: null,
    pi95: null,
  });

  for (const p of history) {
    const key = p.ds.slice(0, 7);
    const row = byMonth.get(key) ?? blank(key);
    row.sales = p.y;
    row.orders = p.orders;
    byMonth.set(key, row);
  }

  for (const p of predictions) {
    const key = p.ds.slice(0, 7);
    const row = byMonth.get(key) ?? blank(key);
    row.yhat = p.yhat;
    row.pi80 =
      p.pi80_lo != null && p.pi80_hi != null ? [p.pi80_lo, p.pi80_hi] : null;
    row.pi95 =
      p.pi95_lo != null && p.pi95_hi != null ? [p.pi95_lo, p.pi95_hi] : null;
    if (row.sales == null && p.y != null) row.sales = p.y;
    byMonth.set(key, row);
  }

  return [...byMonth.values()].sort((a, b) => a.date.localeCompare(b.date));
}

// Compact tooltip: null serileri atar, PI band'larını "lo … hi" formatında
// gösterir, dar bir kutuda kalır. Recharts default tooltip 5 seriyi alt alta
// listeleyince grafiği yukarı dogru kaplıyordu.
function CompactTooltip({
  active,
  payload,
  label,
  isDark,
}: TooltipProps<number | string | (number | string)[], string> & {
  isDark: boolean;
}) {
  if (!active || !payload || payload.length === 0) return null;

  const visible = payload.filter((item) => {
    const v = item.value;
    if (v == null) return false;
    if (Array.isArray(v) && v.every((x) => x == null)) return false;
    // Hide duplicate series caused by the band's tooltip echo when both lines
    // and areas register the same x — keep only meaningful entries.
    return true;
  });

  if (visible.length === 0) return null;

  const fmt = (val: unknown): string => {
    if (val == null) return '—';
    if (Array.isArray(val)) {
      const lo = Number(val[0]);
      const hi = Number(val[1]);
      if (!Number.isFinite(lo) || !Number.isFinite(hi)) return '—';
      return `${lo.toFixed(1)} … ${hi.toFixed(1)}`;
    }
    const n = Number(val);
    return Number.isFinite(n) ? n.toFixed(1) : '—';
  };

  return (
    <div
      className="pointer-events-none rounded-md border px-2 py-1.5 shadow-sm"
      style={{
        backgroundColor: isDark ? '#0e1118ee' : '#ffffffee',
        borderColor: isDark ? '#2a3140' : '#e2e8f0',
        backdropFilter: 'blur(4px)',
        maxWidth: 200,
      }}
    >
      <div
        className="mb-0.5 text-[11px] font-medium"
        style={{ color: isDark ? '#fafaf9' : '#0f172a' }}
      >
        {label}
      </div>
      <ul className="space-y-0.5 text-[11px] tabular-nums">
        {visible.map((item, idx) => (
          <li
            key={`${item.dataKey}-${idx}`}
            className="flex items-center gap-1.5"
          >
            <span
              aria-hidden
              className="inline-block h-1.5 w-1.5 shrink-0 rounded-full"
              style={{ backgroundColor: item.color }}
            />
            <span
              className="truncate"
              style={{ color: isDark ? '#cbd5e1' : '#475569' }}
            >
              {item.name}
            </span>
            <span
              className="ml-auto"
              style={{ color: isDark ? '#fafaf9' : '#0f172a' }}
            >
              {fmt(item.value)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function DemandHistoryChart({ points, predictions, isLoading }: Props) {
  const { t } = useTranslation();
  const theme = useThemeStore((s) => s.theme);
  const isDark =
    theme === 'dark' ||
    (theme === 'system' &&
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-color-scheme: dark)').matches);

  const rows = useMemo(
    () => mergeSeries(points ?? [], predictions ?? []),
    [points, predictions],
  );

  const palette = {
    grid: isDark ? '#2a3140' : '#e2e8f0',
    tick: isDark ? '#a8a29e' : '#334155',
    sales: isDark ? '#cda142' : '#9a6e1f',
    orders: isDark ? '#7dd3fc' : '#0284c7',
    forecast: isDark ? '#22d3ee' : '#0e7490',
    pi80: isDark ? 'rgba(34, 211, 238, 0.28)' : 'rgba(14, 116, 144, 0.25)',
    pi95: isDark ? 'rgba(34, 211, 238, 0.12)' : 'rgba(14, 116, 144, 0.12)',
  };

  const hasForecast = (predictions?.length ?? 0) > 0;

  return (
    <Card>
      <CardHeader
        title={t('sku_detail.demand_history.title')}
        subtitle={
          hasForecast
            ? t('sku_detail.demand_history.subtitle_with_forecast')
            : t('sku_detail.demand_history.subtitle')
        }
      />
      <CardBody>
        {isLoading ? (
          <Skeleton className="h-64" />
        ) : rows.length === 0 ? (
          <p className="py-12 text-center text-sm text-slate-500 dark:text-stone-400">
            {t('sku_detail.demand_history.empty')}
          </p>
        ) : (
          <div className="h-72 w-full">
            <ResponsiveContainer>
              <ComposedChart
                data={rows}
                margin={{ top: 8, right: 12, left: 0, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke={palette.grid} />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11, fill: palette.tick }}
                  minTickGap={20}
                />
                <YAxis tick={{ fontSize: 11, fill: palette.tick }} />
                <Tooltip
                  content={<CompactTooltip isDark={isDark} />}
                  cursor={{ stroke: palette.grid, strokeWidth: 1 }}
                  wrapperStyle={{ outline: 'none', zIndex: 50 }}
                  allowEscapeViewBox={{ x: false, y: true }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />

                {/* 95% PI band — outer */}
                {hasForecast && (
                  <Area
                    type="monotone"
                    dataKey="pi95"
                    stroke="none"
                    fill={palette.pi95}
                    name={t('sku_detail.demand_history.pi95')}
                    isAnimationActive={false}
                    connectNulls={false}
                  />
                )}
                {/* 80% PI band — inner, darker */}
                {hasForecast && (
                  <Area
                    type="monotone"
                    dataKey="pi80"
                    stroke="none"
                    fill={palette.pi80}
                    name={t('sku_detail.demand_history.pi80')}
                    isAnimationActive={false}
                    connectNulls={false}
                  />
                )}

                <Line
                  type="monotone"
                  dataKey="sales"
                  stroke={palette.sales}
                  strokeWidth={2}
                  name={t('sku_detail.demand_history.sales')}
                  dot={{ r: 2, fill: palette.sales, strokeWidth: 0 }}
                  activeDot={{ r: 5, fill: palette.sales }}
                  isAnimationActive={false}
                  connectNulls={false}
                />
                {hasForecast && (
                  <Line
                    type="monotone"
                    dataKey="yhat"
                    stroke={palette.forecast}
                    strokeWidth={2}
                    strokeDasharray="6 4"
                    name={t('sku_detail.demand_history.forecast')}
                    dot={{ r: 2, fill: palette.forecast, strokeWidth: 0 }}
                    activeDot={{ r: 5, fill: palette.forecast }}
                    isAnimationActive={false}
                    connectNulls={false}
                  />
                )}
                <Line
                  type="monotone"
                  dataKey="orders"
                  stroke={palette.orders}
                  strokeDasharray="2 3"
                  strokeWidth={1.25}
                  name={t('sku_detail.demand_history.orders')}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
