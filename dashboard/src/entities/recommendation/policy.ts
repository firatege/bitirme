/**
 * Frontend replica of services/worker/oms/policy.py:round_moq_lot.
 * Kept deterministic and pure so what-if sliders can recompute locally.
 */
export function roundMoqLot(
  rawQty: number,
  moq: number,
  lotSize: number,
): number {
  if (rawQty <= 0) return 0;
  const base = Math.max(rawQty, moq || 0);
  if (!lotSize || lotSize <= 0) return Math.ceil(base);
  return Math.ceil(base / lotSize) * lotSize;
}

export interface WhatIfInput {
  startingStock: number;
  cumDemandQ: number;
  moq: number;
  lotSize: number;
}

export function recomputeOrderQty(input: WhatIfInput): {
  raw: number;
  rounded: number;
} {
  const raw = Math.max(0, input.cumDemandQ - input.startingStock);
  const rounded = roundMoqLot(raw, input.moq, input.lotSize);
  return { raw, rounded };
}

/**
 * Approximate inverse standard normal (probit) using Beasley-Springer-Moro.
 * Used for what-if quantile rescaling on the frontend without bootstrap residuals.
 */
function probit(p: number): number {
  const clamped = Math.min(0.99999, Math.max(0.00001, p));
  const [a0, a1, a2, a3, a4, a5] = [
    -3.969683028665376e1, 2.209460984245205e2, -2.759285104469687e2,
    1.38357751867269e2, -3.066479806614716e1, 2.506628277459239,
  ] as const;
  const [b0, b1, b2, b3, b4] = [
    -5.447609879822406e1, 1.615858368580409e2, -1.556989798598866e2,
    6.680131188771972e1, -1.328068155288572e1,
  ] as const;
  const [c0, c1, c2, c3, c4, c5] = [
    -7.784894002430293e-3, -3.223964580411365e-1, -2.400758277161838,
    -2.549732539343734, 4.374664141464968, 2.938163982698783,
  ] as const;
  const [d0, d1, d2, d3] = [
    7.784695709041462e-3, 3.224671290700398e-1, 2.445134137142996,
    3.754408661907416,
  ] as const;
  const pLow = 0.02425;
  const pHigh = 1 - pLow;
  if (clamped < pLow) {
    const q = Math.sqrt(-2 * Math.log(clamped));
    return (
      (((((c0 * q + c1) * q + c2) * q + c3) * q + c4) * q + c5) /
      ((((d0 * q + d1) * q + d2) * q + d3) * q + 1)
    );
  }
  if (clamped <= pHigh) {
    const q = clamped - 0.5;
    const r = q * q;
    return (
      ((((((a0 * r + a1) * r + a2) * r + a3) * r + a4) * r + a5) * q) /
      (((((b0 * r + b1) * r + b2) * r + b3) * r + b4) * r + 1)
    );
  }
  const q = Math.sqrt(-2 * Math.log(1 - clamped));
  return -(
    (((((c0 * q + c1) * q + c2) * q + c3) * q + c4) * q + c5) /
    ((((d0 * q + d1) * q + d2) * q + d3) * q + 1)
  );
}

/**
 * Frontend-side cum_demand_q rescale when q_target or H_COVER changes.
 * This is APPROXIMATE — assumes:
 *   - linear scaling with horizon (mean demand per month constant)
 *   - normal-shaped tail for quantile rescaling
 * Real backend re-run is needed for an exact figure; the UI must mark this as approx.
 */
export interface RescaleInput {
  origCumDemandQ: number;
  origQ: number;
  origHCover: number;
  newQ: number;
  newHCover: number;
}

export function approxRescaleCumDemand(input: RescaleInput): number {
  const { origCumDemandQ, origQ, origHCover, newQ, newHCover } = input;
  if (origHCover <= 0 || origCumDemandQ <= 0) return origCumDemandQ;
  const horizonScale = newHCover / origHCover;
  const zOrig = probit(origQ);
  const zNew = probit(newQ);
  const denom = Math.max(0.01, 1 + zOrig);
  const numer = Math.max(0.01, 1 + zNew);
  const quantileScale = numer / denom;
  return origCumDemandQ * horizonScale * quantileScale;
}
