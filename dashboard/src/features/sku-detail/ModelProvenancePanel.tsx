import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { Badge } from '@/shared/ui/Badge';
import { fmtDec, fmtPct } from '@/shared/lib/format';
import type { WinningCombo } from '@/entities/sku/schema';

const NEUTRAL_BADGE =
  'bg-slate-100 text-slate-700 ring-slate-200 dark:bg-surface-2 dark:text-stone-200 dark:ring-surface-line';

export function ModelProvenancePanel({ win }: { win: WinningCombo }) {
  return (
    <Card>
      <CardHeader
        title="Kazanan Model"
        subtitle="VAL+TEST'te en düşük MAE'yi veren konfigürasyon"
      />
      <CardBody>
        <div className="flex flex-wrap gap-1.5">
          <Badge className={NEUTRAL_BADGE}>H · {win.horizon}</Badge>
          <Badge className={NEUTRAL_BADGE}>EXOG · {win.exog}</Badge>
          <Badge className={NEUTRAL_BADGE}>Y · {win.y_variant}</Badge>
          <Badge className={NEUTRAL_BADGE}>{win.phase}</Badge>
        </div>
        <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm">
          <Row label="MAE">{fmtDec(win.mae)}</Row>
          <Row label="RMSE">{fmtDec(win.rmse)}</Row>
          <Row label="MAPE">{fmtPct(win.mape)}</Row>
          <Row label="w_RF">{fmtDec(win.w_rf)}</Row>
          <Row label="w_XGB">{fmtDec(win.w_xgb)}</Row>
        </dl>
      </CardBody>
    </Card>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="text-slate-500 dark:text-stone-200/50">{label}</dt>
      <dd className="text-right tabular-nums text-slate-800 dark:text-stone-200">
        {children}
      </dd>
    </>
  );
}
