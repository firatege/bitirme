import type { SkuDetail, SkuHistory } from '@/entities/sku/schema';
import type { RunStatus } from '@/entities/run/schema';

export const FIXTURE_SKUS = [
  '303-104092',
  '303-104093',
  '303-104094',
  '303-104095',
  '303-104096',
  '303-104097',
] as const;

export function fixtureSkuDetail(sku: string): SkuDetail {
  const seed = hash(sku);
  const p3m = clamp(0.05 + (seed % 100) / 100, 0, 0.95);
  const p6m = clamp(p3m + 0.15, 0, 0.99);
  const eT = 12 - (seed % 11);
  const startingStock = 50 + (seed % 400);
  const cumDemand = 200 + (seed % 800);
  const moq = 100;
  const lot = 50;
  const orderRaw = Math.max(0, cumDemand - startingStock);
  const orderRounded =
    orderRaw > 0
      ? Math.ceil(Math.max(orderRaw, moq) / lot) * lot
      : 0;
  const phase = seed % 3 === 0 ? 'REFIT' : 'PRE';
  const exogChoices = ['ETS', 'Prophet', 'SARIMA', 'ML-Exog_XGB', 'Intermittent'];
  const yChoices = ['RF', 'XGB', 'Y-ENS'];
  return {
    run_id: 1000 + (seed % 50),
    sku,
    status: 'completed',
    mode: 'cold',
    winning: {
      horizon: seed % 4 === 0 ? 'Short3' : 'Full',
      exog: exogChoices[seed % exogChoices.length] ?? 'ETS',
      y_variant: yChoices[seed % yChoices.length] ?? 'Y-ENS',
      phase,
      mae: 5 + (seed % 20),
      rmse: 7 + (seed % 25),
      mape: 0.08 + (seed % 15) / 100,
      w_rf: 0.4 + (seed % 5) / 10,
      w_xgb: 0.6 - (seed % 5) / 10,
      p_stockout_3m: p3m,
      p_stockout_6m: p6m,
      e_t_stockout_mo: eT,
    },
    recommendation: {
      starting_stock: startingStock,
      t_check: 3,
      h_cover: 6,
      q_target: 0.7,
      moq,
      lot_size: lot,
      cum_demand_q: cumDemand,
      order_qty_raw: orderRaw,
      order_qty_rounded: orderRounded,
    },
  };
}

export function fixtureSkuHistory(sku: string): SkuHistory {
  const seed = hash(sku);
  const history = Array.from({ length: 8 }, (_, i) => ({
    run_id: 1000 + (seed % 50) - i,
    status: 'completed',
    mode: 'cold',
    winning_exog: 'ETS',
    winning_y_variant: 'Y-ENS',
    winning_phase: 'PRE',
    winning_mae: 5 + (seed % 20) + (Math.sin(i + seed) + 1) * 3,
    completed_at: new Date(Date.now() - i * 30 * 24 * 3600 * 1000).toISOString(),
  }));
  return { sku, history };
}

export function fixtureRunStatus(runId: number): RunStatus {
  const elapsed = (runId * 7) % 100;
  const completed = Math.min(FIXTURE_SKUS.length, Math.floor(elapsed / 8));
  const running = Math.min(2, FIXTURE_SKUS.length - completed);
  const queued = Math.max(0, FIXTURE_SKUS.length - completed - running);
  const isDone = queued === 0 && running === 0;
  return {
    run_id: runId,
    status: isDone ? 'completed' : 'running',
    started_at: new Date(Date.now() - 5 * 60_000).toISOString(),
    completed_at: isDone ? new Date().toISOString() : null,
    pipeline_version: 'v3.0.0-mock',
    jobs: { queued, running, completed, failed: 0 },
  };
}

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h * 31 + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}
