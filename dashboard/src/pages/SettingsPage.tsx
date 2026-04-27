import { useTranslation } from 'react-i18next';
import { setLanguage } from '@/shared/i18n';
import { useThemeStore } from '@/shared/lib/theme';
import { env } from '@/shared/config/env';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { Button } from '@/shared/ui/Button';

export function SettingsPage() {
  const { i18n } = useTranslation();
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Ayarlar</h1>

      <Card>
        <CardHeader title="Tema" />
        <CardBody className="flex gap-2">
          {(['light', 'dark', 'system'] as const).map((t) => (
            <Button
              key={t}
              variant={theme === t ? 'primary' : 'secondary'}
              onClick={() => setTheme(t)}
            >
              {t === 'light' ? 'Açık' : t === 'dark' ? 'Koyu' : 'Sistem'}
            </Button>
          ))}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Dil" />
        <CardBody className="flex gap-2">
          <Button
            variant={i18n.language === 'tr' ? 'primary' : 'secondary'}
            onClick={() => setLanguage('tr')}
          >
            Türkçe
          </Button>
          <Button
            variant={i18n.language === 'en' ? 'primary' : 'secondary'}
            onClick={() => setLanguage('en')}
          >
            English
          </Button>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Backend Konfigürasyonu" />
        <CardBody className="space-y-2 text-sm">
          <Row label="API Base URL" value={env.apiBaseUrl} />
          <Row label="Grafana URL" value={env.grafanaUrl} />
          <Row
            label="Statik JSON modu"
            value={env.useStaticSource ? 'Açık' : 'Kapalı'}
          />
          <Row label="Mock (MSW) modu" value={env.useMsw ? 'Açık' : 'Kapalı'} />
        </CardBody>
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between border-b border-slate-100 py-1 last:border-0 dark:border-slate-800">
      <span className="text-slate-500 dark:text-slate-400">{label}</span>
      <span className="font-mono text-xs">{value}</span>
    </div>
  );
}
