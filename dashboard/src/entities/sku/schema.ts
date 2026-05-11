import { z } from 'zod';

export const WinningComboSchema = z.object({
  horizon: z.string(),
  exog: z.string(),
  y_variant: z.string(),
  phase: z.string(),
  mae: z.number().nullable().optional(),
  rmse: z.number().nullable().optional(),
  mape: z.number().nullable().optional(),
  w_rf: z.number().nullable().optional(),
  w_xgb: z.number().nullable().optional(),
  p_stockout_3m: z.number().nullable().optional(),
  p_stockout_6m: z.number().nullable().optional(),
  e_t_stockout_mo: z.number().nullable().optional(),
});
export type WinningCombo = z.infer<typeof WinningComboSchema>;

export const RecommendationSchema = z.object({
  starting_stock: z.number(),
  t_check: z.number(),
  h_cover: z.number(),
  q_target: z.number(),
  moq: z.number(),
  lot_size: z.number(),
  cum_demand_q: z.number(),
  order_qty_raw: z.number(),
  order_qty_rounded: z.number(),
});
export type Recommendation = z.infer<typeof RecommendationSchema>;

export const SkuDetailSchema = z.object({
  run_id: z.number(),
  sku: z.string(),
  status: z.string(),
  mode: z.string().optional(),
  winning: WinningComboSchema.nullable(),
  recommendation: RecommendationSchema.nullable(),
});
export type SkuDetail = z.infer<typeof SkuDetailSchema>;

export const SkuHistoryEntrySchema = z.object({
  run_id: z.number(),
  status: z.string(),
  mode: z.string().nullable().optional(),
  winning_exog: z.string().nullable().optional(),
  winning_y_variant: z.string().nullable().optional(),
  winning_phase: z.string().nullable().optional(),
  winning_mae: z.number().nullable().optional(),
  completed_at: z.string().nullable().optional(),
  starting_stock: z.number().nullable().optional(),
  cum_demand_q: z.number().nullable().optional(),
  order_qty_rounded: z.number().nullable().optional(),
});
export type SkuHistoryEntry = z.infer<typeof SkuHistoryEntrySchema>;

export const SkuHistorySchema = z.object({
  sku: z.string(),
  history: z.array(SkuHistoryEntrySchema),
});
export type SkuHistory = z.infer<typeof SkuHistorySchema>;

export const SkuTimeseriesPointSchema = z.object({
  ds: z.string(),
  y: z.number().nullable(),
  orders: z.number().nullable(),
  stock: z.number().nullable(),
});
export type SkuTimeseriesPoint = z.infer<typeof SkuTimeseriesPointSchema>;

export const SkuTimeseriesSchema = z.object({
  sku: z.string(),
  points: z.array(SkuTimeseriesPointSchema),
});
export type SkuTimeseries = z.infer<typeof SkuTimeseriesSchema>;

export const SkuPredictionPointSchema = z.object({
  ds: z.string(),
  y: z.number().nullable(),
  yhat: z.number(),
  pi80_lo: z.number().nullable(),
  pi80_hi: z.number().nullable(),
  pi95_lo: z.number().nullable(),
  pi95_hi: z.number().nullable(),
});
export type SkuPredictionPoint = z.infer<typeof SkuPredictionPointSchema>;

export const SkuPredictionsSchema = z.object({
  sku: z.string(),
  run_id: z.number().nullable(),
  points: z.array(SkuPredictionPointSchema),
});
export type SkuPredictions = z.infer<typeof SkuPredictionsSchema>;
