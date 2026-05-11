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

export function useSkuTimeseries(sku: string, months = 24) {
  return useQuery({
    queryKey: queryKeys.skuTimeseries(sku, months),
    queryFn: () => dataSource.getSkuTimeseries(sku, months),
    enabled: !!sku,
    staleTime: 5 * 60_000,
  });
}

export function useSkuPredictions(sku: string, runId?: number) {
  return useQuery({
    queryKey: queryKeys.skuPredictions(sku, runId),
    queryFn: () => dataSource.getSkuPredictions(sku, runId),
    enabled: !!sku,
    staleTime: 5 * 60_000,
  });
}

export function useSkuList() {
  return useQuery({
    queryKey: queryKeys.skuList(),
    queryFn: () => dataSource.listSkus(),
    staleTime: 5 * 60_000,
  });
}

export function useSkuPin(sku: string) {
  return useQuery({
    queryKey: queryKeys.skuPin(sku),
    queryFn: () => dataSource.getSkuPin(sku),
    enabled: !!sku,
    staleTime: 60_000,
  });
}

export function useSetSkuPin(sku: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (runId: number) => dataSource.setSkuPin(sku, runId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.skuPin(sku) });
      qc.invalidateQueries({ queryKey: queryKeys.skuLatest(sku) });
      qc.invalidateQueries({ queryKey: queryKeys.skuPredictions(sku, undefined) });
    },
  });
}

export function useClearSkuPin(sku: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => dataSource.clearSkuPin(sku),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.skuPin(sku) });
      qc.invalidateQueries({ queryKey: queryKeys.skuLatest(sku) });
      qc.invalidateQueries({ queryKey: queryKeys.skuPredictions(sku, undefined) });
    },
  });
}

export function useRunJobs(runId: number | null) {
  return useQuery({
    queryKey: runId ? queryKeys.runJobs(runId) : ['run-jobs', 'none'],
    queryFn: () => dataSource.getRunJobs(runId as number),
    enabled: runId !== null,
    refetchInterval: (query) => {
      const jobs = query.state.data?.jobs ?? [];
      const inFlight = jobs.some(
        (j) => j.status === 'queued' || j.status === 'claimed' || j.status === 'running',
      );
      return inFlight ? 3_000 : false;
    },
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
