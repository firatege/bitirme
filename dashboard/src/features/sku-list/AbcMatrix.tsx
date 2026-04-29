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

  if (points.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader
        title="Aciliyet × Hacim Matrisi"
        subtitle="Sağ üst köşedeki SKU'lar öncelikli — yüksek stockout riski + yüksek hacim"
      />
      <CardBody>
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
              <ReferenceLine
                x={0.25}
                stroke="#fb923c"
                strokeDasharray="4 4"
              />
              <ReferenceLine
                x={0.5}
                stroke="#dc2626"
                strokeDasharray="4 4"
              />
              <Tooltip
                cursor={{ strokeDasharray: '3 3' }}
                formatter={(value: number, name: string) =>
                  name === 'p3m'
                    ? `${(value * 100).toFixed(1)}%`
                    : value.toFixed(0)
                }
                labelFormatter={() => ''}
                content={({ active, payload }) => {
                  if (!active || !payload || !payload[0]) return null;
                  const p = payload[0].payload as MatrixPoint;
                  return (
                    <div className="rounded-md border border-slate-200 bg-white p-2 text-xs shadow-md dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200">
                      <div className="font-mono">{p.sku}</div>
                      <div>Stockout 3m: {(p.p3m * 100).toFixed(1)}%</div>
                      <div>Sipariş: {p.qty.toFixed(0)}</div>
                    </div>
                  );
                }}
              />
              <Scatter
                data={points}
                fill={isDark ? '#38bdf8' : '#0f172a'}
                onClick={(p: MatrixPoint) =>
                  navigate(`/skus/${encodeURIComponent(p.sku)}`)
                }
                cursor="pointer"
              />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-2 text-[11px] text-slate-500">
          Turuncu çizgi: %25 risk eşiği · Kırmızı çizgi: %50 kritik eşik. SKU'ya
          tıklayarak detaya gidin.
        </p>
      </CardBody>
    </Card>
  );
}
