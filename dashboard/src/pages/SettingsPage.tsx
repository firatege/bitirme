import { useTranslation } from 'react-i18next';
import { setLanguage } from '@/shared/i18n';
import { env } from '@/shared/config/env';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { Button } from '@/shared/ui/Button';

export function SettingsPage() {
  const { i18n } = useTranslation();
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-slate-900">Ayarlar</h1>

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
          <div className="flex justify-between border-b border-slate-100 py-1">
            <span className="text-slate-500">API Base URL</span>
            <span className="font-mono text-xs">{env.apiBaseUrl}</span>
          </div>
          <div className="flex justify-between border-b border-slate-100 py-1">
            <span className="text-slate-500">Grafana URL</span>
            <span className="font-mono text-xs">{env.grafanaUrl}</span>
          </div>
          <div className="flex justify-between py-1">
            <span className="text-slate-500">Statik JSON modu</span>
            <span className="font-mono text-xs">
              {env.useStaticSource ? 'Açık' : 'Kapalı'}
            </span>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
