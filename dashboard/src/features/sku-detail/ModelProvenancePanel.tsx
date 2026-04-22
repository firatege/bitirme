import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { Badge } from '@/shared/ui/Badge';
import { fmtDec, fmtPct } from '@/shared/lib/format';
import type { WinningCombo } from '@/entities/sku/schema';

export function ModelProvenancePanel({ win }: { win: WinningCombo }) {
  return (
    <Card>
      <CardHeader
        title="Kazanan Model"
        subtitle="Validation ve test verisinde en düşük MAE'yi veren konfigürasyon"
      />
      <CardBody>
        <div className="flex flex-wrap gap-2">
          <Badge className="bg-slate-100 text-slate-700 ring-slate-200">
            Horizon: {win.horizon}
          </Badge>
          <Badge className="bg-indigo-100 text-indigo-800 ring-indigo-200">
            EXOG: {win.exog}
          </Badge>
          <Badge className="bg-emerald-100 text-emerald-800 ring-emerald-200">
            Y: {win.y_variant}
          </Badge>
          <Badge className="bg-amber-100 text-amber-800 ring-amber-200">
            {win.phase}
          </Badge>
        </div>
        <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <dt className="text-slate-500">MAE</dt>
          <dd className="text-right tabular-nums">{fmtDec(win.mae)}</dd>
          <dt className="text-slate-500">RMSE</dt>
          <dd className="text-right tabular-nums">{fmtDec(win.rmse)}</dd>
          <dt className="text-slate-500">MAPE</dt>
          <dd className="text-right tabular-nums">{fmtPct(win.mape)}</dd>
          <dt className="text-slate-500">w_RF</dt>
          <dd className="text-right tabular-nums">{fmtDec(win.w_rf)}</dd>
          <dt className="text-slate-500">w_XGB</dt>
          <dd className="text-right tabular-nums">{fmtDec(win.w_xgb)}</dd>
        </dl>
      </CardBody>
    </Card>
  );
}
