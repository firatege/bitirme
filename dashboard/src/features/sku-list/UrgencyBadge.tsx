import { useTranslation } from 'react-i18next';
import { Badge } from '@/shared/ui/Badge';
import {
  urgencyColorClass,
  type UrgencyLevel,
} from '@/entities/sku/selectors';

export function UrgencyBadge({ level }: { level: UrgencyLevel }) {
  const { t } = useTranslation();
  return (
    <Badge className={urgencyColorClass(level)}>
      {t(`urgency.${level}` as const)}
    </Badge>
  );
}
