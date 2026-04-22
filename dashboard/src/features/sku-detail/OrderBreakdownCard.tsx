import { useMemo, useState } from 'react';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { Button } from '@/shared/ui/Button';
import { fmtDec, fmtInt } from '@/shared/lib/format';
import { recomputeOrderQty } from '@/entities/recommendation/policy';
import type { Recommendation } from '@/entities/sku/schema';
import { useCartStore } from '@/features/order-cart/cartStore';

export function OrderBreakdownCard({
  sku,
  recommendation,
}: {
  sku: string;
  recommendation: Recommendation;
}) {
  const [moq, setMoq] = useState(recommendation.moq);
  const [lot, setLot] = useState(recommendation.lot_size);
  const [stock, setStock] = useState(recommendation.starting_stock);
  const add = useCartStore((s) => s.add);

  const { raw, rounded } = useMemo(
    () =>
      recomputeOrderQty({
        startingStock: stock,
        cumDemandQ: recommendation.cum_demand_q,
        moq,
        lotSize: lot,
      }),
    [stock, recommendation.cum_demand_q, moq, lot],
  );

  return (
    <Card>
      <CardHeader
        title="Sipariş Önerisi"
        subtitle="Hesap adımları şeffaftır · MOQ ve lot ile yuvarlanır"
      />
      <CardBody className="space-y-4">
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <Row label="Mevcut Stok">
            <input
              type="number"
              value={stock}
              onChange={(e) => setStock(Number(e.target.value))}
              className="w-28 rounded-md border border-slate-200 px-2 py-1 text-right tabular-nums"
            />
          </Row>
          <Row label="Q-kantil kümülatif talep">
            <span className="tabular-nums">
              {fmtDec(recommendation.cum_demand_q)}
            </span>
          </Row>
          <Row label="Ham Sipariş (talep − stok)">
            <span className="tabular-nums text-slate-600">{fmtDec(raw)}</span>
          </Row>
          <Row label="MOQ tabanı">
            <input
              type="number"
              value={moq}
              onChange={(e) => setMoq(Number(e.target.value))}
              className="w-28 rounded-md border border-slate-200 px-2 py-1 text-right tabular-nums"
            />
          </Row>
          <Row label="Lot boyutu">
            <input
              type="number"
              value={lot}
              onChange={(e) => setLot(Number(e.target.value))}
              className="w-28 rounded-md border border-slate-200 px-2 py-1 text-right tabular-nums"
            />
          </Row>
        </dl>

        <div className="rounded-lg bg-slate-900 p-4 text-white">
          <div className="text-xs uppercase tracking-wide text-slate-400">
            Önerilen sipariş (yuvarlanmış)
          </div>
          <div className="mt-1 text-3xl font-semibold tabular-nums">
            {fmtInt(rounded)}
          </div>
          <div className="mt-1 text-xs text-slate-400">
            Politika: T_CHECK={recommendation.t_check}ay · H_COVER=
            {recommendation.h_cover}ay · q={recommendation.q_target}
          </div>
        </div>

        <Button
          onClick={() =>
            add({
              sku,
              suggested_qty: rounded,
              approved_qty: rounded,
            })
          }
          className="w-full"
        >
          Sepete Ekle
        </Button>
      </CardBody>
    </Card>
  );
}

function Row({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="flex justify-end">{children}</dd>
    </>
  );
}
