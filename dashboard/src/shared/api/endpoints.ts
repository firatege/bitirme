export const endpoints = {
  healthz: '/healthz',
  readyz: '/readyz',
  runs: '/runs',
  run: (runId: number) => `/runs/${runId}`,
  runJobs: (runId: number) => `/runs/${runId}/jobs`,
  runSkuDetail: (runId: number, sku: string) =>
    `/runs/${runId}/skus/${encodeURIComponent(sku)}`,
  skuLatest: (sku: string) => `/skus/${encodeURIComponent(sku)}/latest`,
  skuHistory: (sku: string, limit = 20) =>
    `/skus/${encodeURIComponent(sku)}/history?limit=${limit}`,
  skuTimeseries: (sku: string, months = 24) =>
    `/skus/${encodeURIComponent(sku)}/timeseries?months=${months}`,
  skuPredictions: (sku: string, runId?: number) =>
    `/skus/${encodeURIComponent(sku)}/predictions${runId ? `?run_id=${runId}` : ''}`,
  skuForecast: (sku: string) => `/skus/${encodeURIComponent(sku)}/forecast`,
  skus: '/skus',
  skuPin: (sku: string) => `/skus/${encodeURIComponent(sku)}/pin`,
} as const;
