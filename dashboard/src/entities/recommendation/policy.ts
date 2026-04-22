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
