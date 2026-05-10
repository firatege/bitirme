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

/**
 * Risk preset'leri. Tüm aciliyet seviyelerinin demoda gözükmesi için
 * SKU'lar deterministik şekilde 6 bucket'a dağıtılır.
 */
const RISK_PRESETS = [
  // LOW · stok bol, talep düşük → sipariş gerekmez
  { p3m: 0.04, p6m: 0.09, eT: 18, stock: 480, demand: 220 },
  // LOW · biraz daha yüklü ama hala güvende
  { p3m: 0.11, p6m: 0.18, eT: 14, stock: 360, demand: 250 },
  // MEDIUM · 6 ay penceresinde dikkat
  { p3m: 0.19, p6m: 0.34, eT: 9, stock: 240, demand: 320 },
  // HIGH · 3 ay sınırda
  { p3m: 0.31, p6m: 0.55, eT: 6, stock: 180, demand: 480 },
  // CRITICAL · acil
  { p3m: 0.58, p6m: 0.78, eT: 4, stock: 90, demand: 720 },
  // CRITICAL · çok acil
  { p3m: 0.84, p6m: 0.95, eT: 2, stock: 40, demand: 980 },
] as const;

function bucketIndex(sku: string): number {
  const last = sku.slice(-1);
  const n = Number.parseInt(last, 10);
  if (Number.isNaN(n)) return 0;
  return n % RISK_PRESETS.length;
}

export function fixtureSkuDetail(sku: string): SkuDetail {
  const seed = hash(sku);
  const preset = RISK_PRESETS[bucketIndex(sku)] ?? RISK_PRESETS[0];
  const moq = 100;
  const lot = 50;
  const orderRaw = Math.max(0, preset.demand - preset.stock);
  const orderRounded =
    orderRaw > 0 ? Math.ceil(Math.max(orderRaw, moq) / lot) * lot : 0;
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
      mae: 4 + (seed % 18),
      rmse: 6 + (seed % 22),
      mape: 0.06 + (seed % 14) / 100,
      w_rf: 0.4 + (seed % 5) / 10,
      w_xgb: 0.6 - (seed % 5) / 10,
      p_stockout_3m: preset.p3m,
      p_stockout_6m: preset.p6m,
      e_t_stockout_mo: preset.eT,
    },
    recommendation: {
      starting_stock: preset.stock,
      t_check: 3,
      h_cover: 6,
      q_target: 0.7,
      moq,
      lot_size: lot,
      cum_demand_q: preset.demand,
      order_qty_raw: orderRaw,
      order_qty_rounded: orderRounded,
    },
  };
}

export function fixtureSkuHistory(sku: string): SkuHistory {
  const seed = hash(sku);
  const baseMae = 5 + (seed % 18);
  const history = Array.from({ length: 8 }, (_, i) => ({
    run_id: 1000 + (seed % 50) - i,
    status: 'completed',
    mode: 'cold',
    winning_exog: 'ETS',
    winning_y_variant: 'Y-ENS',
    winning_phase: 'PRE',
    winning_mae: baseMae + (Math.sin(i + seed) + 1) * 2.5,
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
