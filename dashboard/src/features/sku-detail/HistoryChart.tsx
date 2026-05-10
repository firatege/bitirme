import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Legend,
} from 'recharts';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { useThemeStore } from '@/shared/lib/theme';
import type { SkuHistoryEntry } from '@/entities/sku/schema';

export function HistoryChart({ entries }: { entries: SkuHistoryEntry[] }) {
  const theme = useThemeStore((s) => s.theme);
  const isDark =
    theme === 'dark' ||
    (theme === 'system' &&
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-color-scheme: dark)').matches);

  const rows = [...entries]
    .reverse()
    .map((e) => ({
      run: e.run_id,
      mae: e.winning_mae,
      date: e.completed_at ? e.completed_at.slice(0, 10) : `#${e.run_id}`,
    }));

  const grid = isDark ? '#2a3140' : '#e2e8f0';
  const tickFill = isDark ? '#a8a29e' : '#334155';
  const stroke = isDark ? '#cda142' : '#9a6e1f';

  return (
    <Card>
      <CardHeader
        title="Model Performans Trendi"
        subtitle="Run'lar arasında MAE değişimi (düşük = iyi)"
      />
      <CardBody>
        <div className="h-56 w-full">
          <ResponsiveContainer>
            <LineChart data={rows} margin={{ top: 10, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={grid} />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: tickFill }} />
              <YAxis tick={{ fontSize: 11, fill: tickFill }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: isDark ? '#0e1118' : '#ffffff',
                  border: `1px solid ${isDark ? '#2a3140' : '#e2e8f0'}`,
                  borderRadius: 8,
                  fontSize: 12,
                }}
                labelStyle={{ color: isDark ? '#fafaf9' : '#0f172a' }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line
                type="monotone"
                dataKey="mae"
                stroke={stroke}
                strokeWidth={2}
                name="MAE"
                dot={{ r: 3, fill: stroke, strokeWidth: 0 }}
                activeDot={{ r: 5, fill: stroke }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </CardBody>
    </Card>
  );
}
