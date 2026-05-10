import { useState } from 'react';
import { env } from '@/shared/config/env';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { Button } from '@/shared/ui/Button';
import { cn } from '@/shared/lib/cn';

const PANELS = [
  { key: 'model-performance', label: 'Model Performans Trendi', uid: 'model-performance' },
  { key: 'portfolio-kpi', label: 'Portföy KPI', uid: 'portfolio-kpi' },
  { key: 'stockout-calibration', label: 'Stockout Kalibrasyonu', uid: 'stockout-calibration' },
  { key: 'run-ops', label: 'Run & Drift Operasyonu', uid: 'run-ops' },
] as const;

export function AnalyticsPage() {
  const [active, setActive] = useState<(typeof PANELS)[number]>(PANELS[0]);
  // Grafana `/d/<uid>` çağrısında slug'ı otomatik tamamlar; biz hardcode etmeyelim
  // (provisioning slug'ı dashboard title'ından türettiği için her zaman uid !== slug).
  const embedUrl = `${env.grafanaUrl}/d/${active.uid}?orgId=1&kiosk=tv&theme=dark`;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-medium text-slate-900 dark:text-stone-50">
            Analiz
          </h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-stone-400">
            Grafana panelleri: zaman serileri, kalibrasyon, operasyon metrikleri.
          </p>
        </div>
        <a href={env.grafanaUrl} target="_blank" rel="noreferrer">
          <Button variant="secondary">Grafana&apos;yı aç ↗</Button>
        </a>
      </header>

      <div className="flex flex-wrap gap-1">
        {PANELS.map((p) => (
          <button
            key={p.key}
            type="button"
            onClick={() => setActive(p)}
            className={cn(
              'h-9 rounded-md px-3 text-xs transition-colors',
              active.key === p.key
                ? 'bg-brand-700 text-white dark:bg-brand-600'
                : 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 dark:border-surface-line dark:bg-surface-1 dark:text-stone-300 dark:hover:bg-surface-2',
            )}
          >
            {p.label}
          </button>
        ))}
      </div>

      <Card>
        <CardHeader title={active.label} subtitle="Grafana embed" />
        <CardBody className="p-0">
          <iframe
            src={embedUrl}
            className="h-[720px] w-full rounded-b-lg border-0"
            title={active.label}
          />
        </CardBody>
      </Card>
    </div>
  );
}
