import { useTranslation } from 'react-i18next';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { urgencyColorClass, type UrgencyLevel } from '@/entities/sku/selectors';

const LEVELS: UrgencyLevel[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN'];

export function UrgencyLegend() {
  const { t } = useTranslation();
  return (
    <Card>
      <CardHeader title="Aciliyet Seviyeleri" />
      <CardBody className="space-y-2">
        {LEVELS.map((level) => (
          <div key={level} className="flex items-center gap-2 text-sm">
            <span
              className={`inline-block h-3 w-3 rounded-full ring-1 ring-inset ${urgencyColorClass(level)}`}
            />
            <span className="text-slate-700 dark:text-slate-300">
              {t(`urgency.${level}` as const)}
            </span>
          </div>
        ))}
      </CardBody>
    </Card>
  );
}
