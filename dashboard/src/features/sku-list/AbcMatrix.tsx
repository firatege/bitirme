import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
  ReferenceLine,
} from 'recharts';
import { useQueries } from '@tanstack/react-query';
import { dataSource } from '@/shared/api/source';
import { queryKeys } from '@/shared/api/queryKeys';
import { useSkuList } from '@/shared/api/hooks';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { useThemeStore } from '@/shared/lib/theme';

interface MatrixPoint {
  sku: string;
  p3m: number;
  qty: number;
}

type RiskBucket = 'low' | 'mid' | 'high';

function bucketOf(p3m: number): RiskBucket {
  if (p3m >= 0.5) return 'high';
  if (p3m >= 0.25) return 'mid';
  return 'low';
}

function median(xs: number[]): number {
  if (xs.length === 0) return 0;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  if (s.length % 2) return s[m] ?? 0;
  return ((s[m - 1] ?? 0) + (s[m] ?? 0)) / 2;
}

export function AbcMatrix() {
  const navigate = useNavigate();
  const { data: skus = [] } = useSkuList();
  const theme = useThemeStore((s) => s.theme);
  const isDark =
    theme === 'dark' ||
    (theme === 'system' &&
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-color-scheme: dark)').matches);

  const queries = useQueries({
    queries: skus.map((sku) => ({
      queryKey: queryKeys.skuLatest(sku),
      queryFn: () => dataSource.getSkuLatest(sku),
      staleTime: 30_000,
      retry: 0,
    })),
  });

  const points: MatrixPoint[] = useMemo(
    () =>
      queries
        .map((q, i) => {
          const d = q.data;
          const sku = skus[i] ?? '';
          if (!d?.winning || !d.recommendation) return null;
          const p3m = d.winning.p_stockout_3m;
          const qty = d.recommendation.order_qty_rounded;
          if (p3m === null || p3m === undefined) return null;
          return { sku, p3m, qty } satisfies MatrixPoint;
        })
        .filter((x): x is MatrixPoint => x !== null),
    [queries, skus],
  );

  const medianQty = useMemo(() => median(points.map((p) => p.qty)), [points]);

  const colors = {
    low: isDark ? '#34d399' : '#059669',
    mid: isDark ? '#fbbf24' : '#d97706',
    high: isDark ? '#fb7185' : '#dc2626',
  } as const;

  const buckets = useMemo(() => {
    const out: Record<RiskBucket, MatrixPoint[]> = { low: [], mid: [], high: [] };
    for (const p of points) out[bucketOf(p.p3m)].push(p);
    return out;
  }, [points]);

  if (points.length === 0) {
    return null;
  }

  const onPointClick = (p: MatrixPoint) =>
    navigate(`/skus/${encodeURIComponent(p.sku)}`);

  return (
    <Card>
      <CardHeader
        title="Aciliyet × Hacim Matrisi"
        subtitle="Her nokta bir SKU. Sağa gidildikçe stockout riski artar, yukarı çıkıldıkça sipariş hacmi büyür. Sağ üst köşedeki SKU'lar öncelikli."
      />
      <CardBody>
        {/* Renk açıklaması — eşikler */}
        <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-600 dark:text-slate-300">
          <LegendDot color={colors.low} label="Düşük risk (< %25)" />
          <LegendDot color={colors.mid} label="Orta risk (%25 – %50)" />
          <LegendDot color={colors.high} label="Kritik (> %50)" />
          <span className="ml-auto text-slate-400 dark:text-slate-500">
            {points.length} SKU
          </span>
        </div>

        <div className="h-72 w-full">
          <ResponsiveContainer>
            <ScatterChart margin={{ top: 10, right: 30, bottom: 30, left: 30 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={isDark ? '#334155' : '#e2e8f0'} />
              <XAxis
                type="number"
                dataKey="p3m"
                domain={[0, 1]}
                tick={{ fontSize: 11, fill: isDark ? '#94a3b8' : '#334155' }}
                label={{
                  value: '3-ay stockout olasılığı',
                  position: 'bottom',
                  fontSize: 11,
                  fill: '#64748b',
                }}
                tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
              />
              <YAxis
                type="number"
                dataKey="qty"
                tick={{ fontSize: 11, fill: isDark ? '#94a3b8' : '#334155' }}
                label={{
                  value: 'Önerilen sipariş',
                  angle: -90,
                  position: 'left',
                  fontSize: 11,
                  fill: '#64748b',
                }}
              />
              <ZAxis range={[60, 220]} />

              {/* Risk eşikleri (dikey) */}
              <ReferenceLine
                x={0.25}
                stroke={colors.mid}
                strokeDasharray="4 4"
                label={{
                  value: '%25',
                  position: 'top',
                  fontSize: 10,
                  fill: colors.mid,
                }}
              />
              <ReferenceLine
                x={0.5}
                stroke={colors.high}
                strokeDasharray="4 4"
                label={{
                  value: '%50',
                  position: 'top',
                  fontSize: 10,
                  fill: colors.high,
                }}
              />

              {/* Hacim medyanı (yatay) — yüksek/düşük hacim ayrımı */}
              {medianQty > 0 && (
                <ReferenceLine
                  y={medianQty}
                  stroke={isDark ? '#64748b' : '#94a3b8'}
                  strokeDasharray="2 4"
                  label={{
                    value: 'medyan hacim',
                    position: 'right',
                    fontSize: 10,
                    fill: isDark ? '#94a3b8' : '#64748b',
                  }}
                />
              )}

              <Tooltip
                cursor={{ strokeDasharray: '3 3' }}
                content={({ active, payload }) => {
                  if (!active || !payload || !payload[0]) return null;
                  const p = payload[0].payload as MatrixPoint;
                  const b = bucketOf(p.p3m);
                  const label =
                    b === 'high' ? 'Kritik' : b === 'mid' ? 'Orta risk' : 'Düşük risk';
                  return (
                    <div className="rounded-md border border-slate-200 bg-white p-2 text-xs shadow-md dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200">
                      <div className="font-mono">{p.sku}</div>
                      <div>Stockout 3m: {(p.p3m * 100).toFixed(1)}%</div>
                      <div>Sipariş: {p.qty.toFixed(0)}</div>
                      <div className="mt-1" style={{ color: colors[b] }}>
                        {label}
                      </div>
                    </div>
                  );
                }}
              />

              {/* Risk seviyesine göre 3 ayrı seri — her biri farklı renkte */}
              <Scatter
                name="low"
                data={buckets.low}
                fill={colors.low}
                onClick={(p: MatrixPoint) => onPointClick(p)}
                cursor="pointer"
              />
              <Scatter
                name="mid"
                data={buckets.mid}
                fill={colors.mid}
                onClick={(p: MatrixPoint) => onPointClick(p)}
                cursor="pointer"
              />
              <Scatter
                name="high"
                data={buckets.high}
                fill={colors.high}
                onClick={(p: MatrixPoint) => onPointClick(p)}
                cursor="pointer"
              />
            </ScatterChart>
          </ResponsiveContainer>
        </div>

        {/* 4 bölge açıklaması */}
        <div className="mt-4 grid grid-cols-1 gap-2 text-[11px] sm:grid-cols-2">
          <QuadrantNote
            tone="critical"
            title="Sağ üst — Öncelikli"
            text="Yüksek risk + yüksek hacim. Önce bunları sipariş et."
          />
          <QuadrantNote
            tone="warning"
            title="Sağ alt — Riskli ama küçük"
            text="Stockout riski var, hacim küçük; sipariş kolay ama gözden kaçırma."
          />
          <QuadrantNote
            tone="info"
            title="Sol üst — Sağlıklı çekirdek"
            text="Yüksek hacim, risk düşük. Stok seviyesini koru, agresif sipariş gerekmez."
          />
          <QuadrantNote
            tone="muted"
            title="Sol alt — Önemsiz"
            text="Düşük risk + düşük hacim. Rutin döngüde takip edilebilir."
          />
        </div>

        <p className="mt-3 text-[11px] text-slate-500 dark:text-slate-400">
          Bir SKU'ya tıklayarak detay sayfasına gidebilirsin.
        </p>
      </CardBody>
    </Card>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className="inline-block h-2.5 w-2.5 rounded-full"
        style={{ backgroundColor: color }}
        aria-hidden
      />
      <span>{label}</span>
    </span>
  );
}

function QuadrantNote({
  tone,
  title,
  text,
}: {
  tone: 'critical' | 'warning' | 'info' | 'muted';
  title: string;
  text: string;
}) {
  const toneClasses: Record<typeof tone, string> = {
    critical:
      'border-red-200 bg-red-50 dark:border-red-900/40 dark:bg-red-950/30',
    warning:
      'border-amber-200 bg-amber-50 dark:border-amber-900/40 dark:bg-amber-950/30',
    info:
      'border-emerald-200 bg-emerald-50 dark:border-emerald-900/40 dark:bg-emerald-950/30',
    muted:
      'border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900/40',
  };
  return (
    <div className={`rounded-md border px-2.5 py-1.5 ${toneClasses[tone]}`}>
      <div className="font-medium text-slate-700 dark:text-slate-200">{title}</div>
      <div className="mt-0.5 text-slate-600 dark:text-slate-400">{text}</div>
    </div>
  );
}
