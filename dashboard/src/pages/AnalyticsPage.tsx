import { useState } from 'react';
import { env } from '@/shared/config/env';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { Button } from '@/shared/ui/Button';

const PANELS = [
  {
    key: 'model-performance',
    label: 'Model Performans Trendi',
    uid: 'model-performance',
  },
  { key: 'portfolio-kpi', label: 'Portföy KPI', uid: 'portfolio-kpi' },
  {
    key: 'stockout-calibration',
    label: 'Stockout Kalibrasyonu',
    uid: 'stockout-calibration',
  },
  { key: 'run-ops', label: 'Run & Drift Operasyonu', uid: 'run-ops' },
] as const;

export function AnalyticsPage() {
  const [active, setActive] = useState<(typeof PANELS)[number]>(PANELS[0]);
  const embedUrl = `${env.grafanaUrl}/d/${active.uid}/${active.key}?orgId=1&kiosk=tv&theme=light`;

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Analiz</h1>
          <p className="text-sm text-slate-500">
            Grafana panelleri: zaman serileri, kalibrasyon, operasyon metrikleri.
          </p>
        </div>
        <a href={env.grafanaUrl} target="_blank" rel="noreferrer">
          <Button variant="secondary">Grafana'yı aç ↗</Button>
        </a>
      </div>

      <div className="flex flex-wrap gap-2">
        {PANELS.map((p) => (
          <button
            key={p.key}
            onClick={() => setActive(p)}
            className={`h-9 rounded-lg px-3 text-xs font-medium transition-colors ${
              active.key === p.key
                ? 'bg-slate-900 text-white'
                : 'bg-white text-slate-700 ring-1 ring-inset ring-slate-200 hover:bg-slate-50'
            }`}
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
            className="h-[720px] w-full rounded-b-xl border-0"
            title={active.label}
          />
        </CardBody>
      </Card>
    </div>
  );
}
