import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { Badge } from '@/shared/ui/Badge';
import { fmtDec, fmtPct } from '@/shared/lib/format';
import type { WinningCombo } from '@/entities/sku/schema';

const NEUTRAL_BADGE =
  'bg-slate-100 text-slate-700 ring-slate-200 dark:bg-surface-2 dark:text-stone-200 dark:ring-surface-line';

// Y ensemble: ağırlıklar yalnız buralarda anlamlı. Saf RF/XGB/intermittent için
// w_rf ve w_xgb tasarımdan boş gelir — gereksiz "—" satırı göstermeyelim.
const ENSEMBLE_Y_VARIANTS = new Set(['Y-ENS', 'ENSEMBLE', 'ENS']);

export function ModelProvenancePanel({ win }: { win: WinningCombo }) {
  const isEnsemble = ENSEMBLE_Y_VARIANTS.has(win.y_variant.toUpperCase());

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
          {isEnsemble && (
            <>
              <Row label="w_RF">{fmtDec(win.w_rf)}</Row>
              <Row label="w_XGB">{fmtDec(win.w_xgb)}</Row>
            </>
          )}
        </dl>
        {!isEnsemble && (
          <p className="mt-3 text-[11px] leading-snug text-slate-500 dark:text-stone-400">
            Tek-model kazandı ({win.y_variant}); RF/XGB ağırlıkları yalnızca
            ensemble (Y-ENS) için anlamlıdır.
          </p>
        )}
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
