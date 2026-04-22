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
import type { SkuHistoryEntry } from '@/entities/sku/schema';

export function HistoryChart({ entries }: { entries: SkuHistoryEntry[] }) {
  const rows = [...entries]
    .reverse()
    .map((e) => ({
      run: e.run_id,
      mae: e.winning_mae,
      date: e.completed_at ? e.completed_at.slice(0, 10) : `#${e.run_id}`,
    }));

  return (
    <Card>
      <CardHeader
        title="Model Performans Trendi"
        subtitle="Run'lar arasında MAE değişimi"
      />
      <CardBody>
        <div className="h-56 w-full">
          <ResponsiveContainer>
            <LineChart data={rows}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Line
                type="monotone"
                dataKey="mae"
                stroke="#4f46e5"
                strokeWidth={2}
                name="MAE"
                dot={{ r: 3 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </CardBody>
    </Card>
  );
}
