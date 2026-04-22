export const queryKeys = {
  all: ['dashboard'] as const,
  health: () => [...queryKeys.all, 'health'] as const,
  skus: () => [...queryKeys.all, 'skus'] as const,
  skuLatest: (sku: string) => [...queryKeys.skus(), sku, 'latest'] as const,
  skuHistory: (sku: string, limit: number) =>
    [...queryKeys.skus(), sku, 'history', limit] as const,
  runs: () => [...queryKeys.all, 'runs'] as const,
  run: (runId: number) => [...queryKeys.runs(), runId] as const,
  runSkuDetail: (runId: number, sku: string) =>
    [...queryKeys.run(runId), 'sku', sku] as const,
  skuList: () => [...queryKeys.skus(), 'list'] as const,
} as const;
