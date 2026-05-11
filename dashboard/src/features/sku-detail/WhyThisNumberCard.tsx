import { useTranslation } from 'react-i18next';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { fmtDec, fmtInt, fmtPct } from '@/shared/lib/format';
import type { Recommendation } from '@/entities/sku/schema';

interface Props {
  recommendation: Recommendation;
}

// Narrative breakdown of the order recommendation. Read-only story version of
// the data already in OrderBreakdownCard; the breakdown there is interactive.
// This card answers "neden bu sayı?" with a visual flow so the user understands
// the policy reasoning before tweaking sliders or approving.
export function WhyThisNumberCard({ recommendation }: Props) {
  const { t } = useTranslation();
  const r = recommendation;

  const rawGap = r.cum_demand_q - r.starting_stock;
  const stockSufficient = rawGap <= 0;

  return (
    <Card>
      <CardHeader
        title={t('sku_detail.why.title')}
        subtitle={t('sku_detail.why.subtitle')}
      />
      <CardBody className="space-y-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-4 md:gap-2">
          <Step
            index={1}
            label={t('sku_detail.why.step1.label')}
            value={fmtDec(r.cum_demand_q)}
            hint={t('sku_detail.why.step1.hint', {
              q: fmtPct(r.q_target),
              months: r.h_cover,
            })}
          />
          <Step
            index={2}
            label={t('sku_detail.why.step2.label')}
            value={fmtDec(r.starting_stock)}
            hint={t('sku_detail.why.step2.hint')}
            tone="neutral"
          />
          <Step
            index={3}
            label={t('sku_detail.why.step3.label')}
            value={fmtDec(rawGap)}
            hint={
              stockSufficient
                ? t('sku_detail.why.step3.hint_negative')
                : t('sku_detail.why.step3.hint_positive')
            }
            tone={stockSufficient ? 'success' : 'warning'}
          />
          <Step
            index={4}
            label={t('sku_detail.why.step4.label')}
            value={fmtInt(r.order_qty_rounded)}
            hint={
              r.moq > 0 || r.lot_size > 1
                ? t('sku_detail.why.step4.hint_round', {
                    moq: r.moq,
                    lot: r.lot_size,
                  })
                : t('sku_detail.why.step4.hint_plain')
            }
            tone={r.order_qty_rounded > 0 ? 'primary' : 'success'}
            emphasized
          />
        </div>

        {stockSufficient && r.order_qty_rounded === 0 && (
          <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200">
            <strong className="font-medium">
              {t('sku_detail.why.stock_sufficient.title')}
            </strong>
            <p className="mt-1 text-xs leading-relaxed">
              {t('sku_detail.why.stock_sufficient.body', {
                stock: fmtDec(r.starting_stock),
                demand: fmtDec(r.cum_demand_q),
                months: r.h_cover,
                q: fmtPct(r.q_target),
              })}
            </p>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

type Tone = 'neutral' | 'primary' | 'success' | 'warning';

function Step({
  index,
  label,
  value,
  hint,
  tone = 'neutral',
  emphasized = false,
}: {
  index: number;
  label: string;
  value: string;
  hint: string;
  tone?: Tone;
  emphasized?: boolean;
}) {
  const toneClasses: Record<Tone, string> = {
    neutral:
      'border-slate-200 bg-slate-50 dark:border-surface-line dark:bg-surface-2/40',
    primary:
      'border-brand-200 bg-brand-50 dark:border-brand-500/30 dark:bg-brand-500/10',
    success:
      'border-emerald-200 bg-emerald-50 dark:border-emerald-500/30 dark:bg-emerald-500/10',
    warning:
      'border-amber-200 bg-amber-50 dark:border-amber-500/30 dark:bg-amber-500/10',
  };

  const valueColor: Record<Tone, string> = {
    neutral: 'text-slate-900 dark:text-stone-50',
    primary: 'text-brand-800 dark:text-brand-200',
    success: 'text-emerald-900 dark:text-emerald-200',
    warning: 'text-amber-900 dark:text-amber-200',
  };

  return (
    <div
      className={`relative rounded-lg border p-3 ${toneClasses[tone]}`}
      aria-label={`${index}. ${label}`}
    >
      <div className="flex items-center gap-2">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-slate-200 text-[10px] font-semibold text-slate-700 dark:bg-surface-line dark:text-stone-200">
          {index}
        </span>
        <span className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-stone-400">
          {label}
        </span>
      </div>
      <div
        className={`mt-2 tabular-nums ${valueColor[tone]} ${
          emphasized ? 'text-2xl font-semibold' : 'text-xl font-medium'
        }`}
      >
        {value}
      </div>
      <p className="mt-1 text-[11px] leading-snug text-slate-500 dark:text-stone-400">
        {hint}
      </p>
    </div>
  );
}
