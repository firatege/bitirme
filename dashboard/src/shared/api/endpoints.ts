export const endpoints = {
  healthz: '/healthz',
  readyz: '/readyz',
  runs: '/runs',
  run: (runId: number) => `/runs/${runId}`,
  runSkuDetail: (runId: number, sku: string) =>
    `/runs/${runId}/skus/${encodeURIComponent(sku)}`,
  skuLatest: (sku: string) => `/skus/${encodeURIComponent(sku)}/latest`,
  skuHistory: (sku: string, limit = 20) =>
    `/skus/${encodeURIComponent(sku)}/history?limit=${limit}`,
  skuForecast: (sku: string) => `/skus/${encodeURIComponent(sku)}/forecast`,
} as const;
