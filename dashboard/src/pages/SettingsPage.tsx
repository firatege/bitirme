import { useTranslation } from 'react-i18next';
import { useThemeStore } from '@/shared/lib/theme';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { Button } from '@/shared/ui/Button';

export function SettingsPage() {
  const { t } = useTranslation();
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-medium text-slate-900 dark:text-stone-50">
        {t('settings.title')}
      </h1>

      <Card>
        <CardHeader title={t('settings.theme.title')} />
        <CardBody className="flex gap-2">
          {(['light', 'dark', 'system'] as const).map((option) => (
            <Button
              key={option}
              variant={theme === option ? 'primary' : 'secondary'}
              onClick={() => setTheme(option)}
            >
              {t(`settings.theme.${option}`)}
            </Button>
          ))}
        </CardBody>
      </Card>
    </div>
  );
}
