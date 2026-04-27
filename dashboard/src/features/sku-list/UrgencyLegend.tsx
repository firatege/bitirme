import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { UrgencyBadge } from './UrgencyBadge';
import type { UrgencyLevel } from '@/entities/sku/selectors';

const ROWS: Array<{ level: UrgencyLevel; rule: string }> = [
  { level: 'CRITICAL', rule: '3 ay içinde stockout olasılığı ≥ %50' },
  { level: 'HIGH', rule: '3 ay riski ≥ %25 veya 6 ay riski ≥ %50' },
  { level: 'MEDIUM', rule: '6 ay riski ≥ %25 veya beklenen stockout ≤ 6 ay' },
  { level: 'LOW', rule: 'Risk verisi var, eşiklerin altında' },
  { level: 'UNKNOWN', rule: 'Henüz çalıştırılmamış SKU' },
];

export function UrgencyLegend() {
  return (
    <Card>
      <CardHeader title="Aciliyet Seviyeleri" />
      <CardBody className="space-y-2 text-xs">
        {ROWS.map((r) => (
          <div key={r.level} className="flex items-center gap-3">
            <UrgencyBadge level={r.level} />
            <span className="text-slate-600 dark:text-slate-400">{r.rule}</span>
          </div>
        ))}
      </CardBody>
    </Card>
  );
}
