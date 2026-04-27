import { useMemo, useState } from 'react';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { Button } from '@/shared/ui/Button';
import { fmtDec, fmtInt, fmtPct } from '@/shared/lib/format';
import {
  approxRescaleCumDemand,
  recomputeOrderQty,
} from '@/entities/recommendation/policy';
import type { Recommendation } from '@/entities/sku/schema';
import { useCartStore } from '@/features/order-cart/cartStore';
import { toast } from '@/shared/ui/Toast';

export function OrderBreakdownCard({
  sku,
  recommendation,
  onRequestRerun,
}: {
  sku: string;
  recommendation: Recommendation;
  onRequestRerun?: () => void;
}) {
  const [moq, setMoq] = useState(recommendation.moq);
  const [lot, setLot] = useState(recommendation.lot_size);
  const [stock, setStock] = useState(recommendation.starting_stock);
  const [q, setQ] = useState(recommendation.q_target);
  const [hCover, setHCover] = useState(recommendation.h_cover);

  const add = useCartStore((s) => s.add);

  const adjustedDemand = useMemo(
    () =>
      approxRescaleCumDemand({
        origCumDemandQ: recommendation.cum_demand_q,
        origQ: recommendation.q_target,
        origHCover: recommendation.h_cover,
        newQ: q,
        newHCover: hCover,
      }),
    [recommendation, q, hCover],
  );

  const isApprox =
    q !== recommendation.q_target || hCover !== recommendation.h_cover;

  const { raw, rounded } = useMemo(
    () =>
      recomputeOrderQty({
        startingStock: stock,
        cumDemandQ: adjustedDemand,
        moq,
        lotSize: lot,
      }),
    [stock, adjustedDemand, moq, lot],
  );

  const reset = () => {
    setMoq(recommendation.moq);
    setLot(recommendation.lot_size);
    setStock(recommendation.starting_stock);
    setQ(recommendation.q_target);
    setHCover(recommendation.h_cover);
  };

  return (
    <Card>
      <CardHeader
        title="Sipariş Önerisi"
        subtitle="Hesap adımları şeffaf · MOQ ve lot ile yuvarlanır"
        action={
          isApprox ? (
            <span className="rounded bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800 ring-1 ring-amber-200">
              Yaklaşık
            </span>
          ) : null
        }
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
          <Row label={`Q-kantil talep${isApprox ? ' (yaklaşık)' : ''}`}>
            <span className="tabular-nums">{fmtDec(adjustedDemand)}</span>
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

        <div className="space-y-3 rounded-lg bg-slate-50 p-3">
          <div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-600">
                Servis seviyesi (q): <strong>{fmtPct(q)}</strong>
              </span>
              <button
                type="button"
                onClick={() => setQ(recommendation.q_target)}
                className="text-[10px] text-slate-500 hover:text-slate-800"
              >
                sıfırla
              </button>
            </div>
            <input
              type="range"
              min={0.5}
              max={0.99}
              step={0.01}
              value={q}
              onChange={(e) => setQ(Number(e.target.value))}
              className="mt-1 w-full"
            />
          </div>
          <div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-600">
                Kapsama ufku: <strong>{hCover} ay</strong>
              </span>
              <button
                type="button"
                onClick={() => setHCover(recommendation.h_cover)}
                className="text-[10px] text-slate-500 hover:text-slate-800"
              >
                sıfırla
              </button>
            </div>
            <input
              type="range"
              min={1}
              max={18}
              step={1}
              value={hCover}
              onChange={(e) => setHCover(Number(e.target.value))}
              className="mt-1 w-full"
            />
          </div>
          {isApprox && (
            <p className="text-[11px] leading-relaxed text-amber-800">
              q ve H_COVER değişiklikleri frontend'de yaklaşık ölçeklenir
              (lineer + normal yaklaşımı). Kesin hesap için modeli yeniden
              çalıştırın.
              {onRequestRerun && (
                <>
                  {' '}
                  <button
                    type="button"
                    onClick={onRequestRerun}
                    className="font-semibold underline hover:text-amber-900"
                  >
                    Yeniden çalıştır
                  </button>
                </>
              )}
            </p>
          )}
        </div>

        <div className="rounded-lg bg-slate-900 p-4 text-white">
          <div className="text-xs uppercase tracking-wide text-slate-400">
            Önerilen sipariş (yuvarlanmış)
          </div>
          <div className="mt-1 text-3xl font-semibold tabular-nums">
            {fmtInt(rounded)}
          </div>
          <div className="mt-1 text-xs text-slate-400">
            Politika: T_CHECK={recommendation.t_check}ay · q={fmtPct(q)} ·
            H={hCover}ay
          </div>
        </div>

        <div className="flex gap-2">
          <Button
            onClick={() => {
              add({ sku, suggested_qty: rounded, approved_qty: rounded });
              toast(`${sku} sepete eklendi`, 'success');
            }}
            className="flex-1"
          >
            Sepete Ekle
          </Button>
          <Button variant="secondary" onClick={reset}>
            Sıfırla
          </Button>
        </div>
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
