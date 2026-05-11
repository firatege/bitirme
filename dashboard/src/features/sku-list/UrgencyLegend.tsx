import { useTranslation } from 'react-i18next';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { urgencyDotColor, type UrgencyLevel } from '@/entities/sku/selectors';

const LEVELS: UrgencyLevel[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN'];

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
          </div>
        ))}
      </CardBody>
    </Card>
  );
}
