import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { dataSource } from './source';
import { queryKeys } from './queryKeys';
import { rememberSku } from '@/shared/lib/seenSkus';

export function useSkuLatest(sku: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.skuLatest(sku),
    queryFn: async () => {
      const result = await dataSource.getSkuLatest(sku);
      rememberSku(sku);
      return result;
    },
    enabled: enabled && !!sku,
    staleTime: 30_000,
    retry: 1,
  });
}

export function useSkuHistory(sku: string, limit = 20) {
  return useQuery({
    queryKey: queryKeys.skuHistory(sku, limit),
    queryFn: () => dataSource.getSkuHistory(sku, limit),
    enabled: !!sku,
    staleTime: 60_000,
  });
}

export function useSkuList() {
  return useQuery({
    queryKey: queryKeys.skuList(),
    queryFn: () => dataSource.listSkus(),
    staleTime: 5 * 60_000,
  });
}

export function useRunStatus(runId: number | null) {
  return useQuery({
    queryKey: runId ? queryKeys.run(runId) : ['run', 'none'],
    queryFn: () => dataSource.getRunStatus(runId as number),
    enabled: runId !== null,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 3_000;
      return data.status === 'completed' || data.status === 'failed'
        ? false
        : 3_000;
    },
  });
}

export function useCreateRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { concurrency?: number; check_drift?: boolean }) =>
      dataSource.createRun(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.runs() });
    },
  });
}

export function useTriggerSkuForecast() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sku: string) => dataSource.triggerSkuForecast(sku),
    onSuccess: (_data, sku) => {
      qc.invalidateQueries({ queryKey: queryKeys.skuLatest(sku) });
    },
  });
}
