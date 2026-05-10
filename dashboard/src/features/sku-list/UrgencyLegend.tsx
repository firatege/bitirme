import { useTranslation } from 'react-i18next';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { urgencyDotColor, type UrgencyLevel } from '@/entities/sku/selectors';

const LEVELS: UrgencyLevel[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN'];

const RULES: Record<UrgencyLevel, string> = {
  CRITICAL: 'P(stockout, 3 ay) ≥ %50',
  HIGH: 'P(stockout, 3 ay) ≥ %25 veya 6m ≥ %50',
  MEDIUM: 'P(stockout, 6 ay) ≥ %25 veya E[T] ≤ 6 ay',
  LOW: 'tahmin var, risk düşük',
  UNKNOWN: 'tahmin yok ya da hata',
};

export function UrgencyLegend() {
  const { t } = useTranslation();
  return (
    <Card>
      <CardHeader title="Aciliyet Seviyeleri" />
      <CardBody className="space-y-2">
        {LEVELS.map((level) => (
          <div key={level} className="flex items-center gap-2.5 text-sm">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: urgencyDotColor(level) }}
            />
            <span className="text-slate-700 dark:text-stone-200">
              {t(`urgency.${level}` as const)}
            </span>
            <span className="ml-auto text-xs text-slate-400 dark:text-stone-200/40">
              {RULES[level]}
            </span>
          </div>
        ))}
      </CardBody>
    </Card>
  );
}
