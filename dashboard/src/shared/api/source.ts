import { apiClient } from './client';
import { endpoints } from './endpoints';
import { readSeenSkus } from '@/shared/lib/seenSkus';
import { env } from '@/shared/config/env';
import {
  SkuDetailSchema,
  SkuHistorySchema,
  SkuPredictionsSchema,
  SkuTimeseriesSchema,
  type SkuDetail,
  type SkuHistory,
  type SkuPredictions,
  type SkuTimeseries,
} from '@/entities/sku/schema';
import {
  CreateRunResponseSchema,
  RunJobsSchema,
  RunStatusSchema,
  SkuPinSchema,
  type CreateRunResponse,
  type RunJobs,
  type RunStatus,
  type SkuPin,
} from '@/entities/run/schema';

export interface ForecastDataSource {
  getSkuLatest(sku: string): Promise<SkuDetail>;
  getSkuHistory(sku: string, limit?: number): Promise<SkuHistory>;
  getSkuTimeseries(sku: string, months?: number): Promise<SkuTimeseries>;
  getSkuPredictions(sku: string, runId?: number): Promise<SkuPredictions>;
  getRunStatus(runId: number): Promise<RunStatus>;
  listRuns(limit?: number): Promise<RunStatus[]>;
  getRunJobs(runId: number): Promise<RunJobs>;
  getSkuPin(sku: string): Promise<SkuPin>;
  setSkuPin(sku: string, runId: number): Promise<SkuPin>;
  clearSkuPin(sku: string): Promise<SkuPin>;
  createRun(body: { concurrency?: number; check_drift?: boolean }): Promise<CreateRunResponse>;
  triggerSkuForecast(sku: string): Promise<CreateRunResponse>;
  listSkus(): Promise<string[]>;
}

class ControllerAdapter implements ForecastDataSource {
  async getSkuLatest(sku: string): Promise<SkuDetail> {
    const { data } = await apiClient.get(endpoints.skuLatest(sku));
    return SkuDetailSchema.parse(data);
  }

  async getSkuHistory(sku: string, limit = 20): Promise<SkuHistory> {
    const { data } = await apiClient.get(endpoints.skuHistory(sku, limit));
    return SkuHistorySchema.parse(data);
  }

  async getSkuTimeseries(sku: string, months = 24): Promise<SkuTimeseries> {
    const { data } = await apiClient.get(endpoints.skuTimeseries(sku, months));
    return SkuTimeseriesSchema.parse(data);
  }

  async getSkuPredictions(sku: string, runId?: number): Promise<SkuPredictions> {
    const { data } = await apiClient.get(endpoints.skuPredictions(sku, runId));
    return SkuPredictionsSchema.parse(data);
  }

  async getRunStatus(runId: number): Promise<RunStatus> {
    const { data } = await apiClient.get(endpoints.run(runId));
    return RunStatusSchema.parse(data);
  }

  async listRuns(limit = 100): Promise<RunStatus[]> {
    const { data } = await apiClient.get(endpoints.runs, { params: { limit } });
    return RunStatusSchema.array().parse(data);
  }

  async getRunJobs(runId: number): Promise<RunJobs> {
    const { data } = await apiClient.get(endpoints.runJobs(runId));
    return RunJobsSchema.parse(data);
  }

  async getSkuPin(sku: string): Promise<SkuPin> {
    const { data } = await apiClient.get(endpoints.skuPin(sku));
    return SkuPinSchema.parse(data);
  }

  async setSkuPin(sku: string, runId: number): Promise<SkuPin> {
    const { data } = await apiClient.post(endpoints.skuPin(sku), {
      run_id: runId,
    });
    return SkuPinSchema.parse(data);
  }

  async clearSkuPin(sku: string): Promise<SkuPin> {
    const { data } = await apiClient.delete(endpoints.skuPin(sku));
    return SkuPinSchema.parse(data);
  }

  async createRun(body: {
    concurrency?: number;
    check_drift?: boolean;
  }): Promise<CreateRunResponse> {
    const { data } = await apiClient.post(endpoints.runs, body);
    return CreateRunResponseSchema.parse(data);
  }

  async triggerSkuForecast(sku: string): Promise<CreateRunResponse> {
    const { data } = await apiClient.post(endpoints.skuForecast(sku), {});
    return CreateRunResponseSchema.parse(data);
  }

  async listSkus(): Promise<string[]> {
    if (env.useMsw) {
      const { FIXTURE_SKUS } = await import(
        '@/test/fixtures/forecastResult.fixture'
      );
      return [...FIXTURE_SKUS];
    }
    const fromApi = await this.fetchApiSkus();
    if (fromApi.length > 0) {
      // API is the source of truth — only augment with locally-seen SKUs that
      // the backend already knows about would be redundant, so we trust the API.
      return [...fromApi].sort();
    }
    // Fallback: API unreachable or empty. Merge build-time static list with
    // locally-seen SKUs so the UI still renders something.
    const fromStatic = await this.fetchStaticSkus();
    const fromLocal = readSeenSkus();
    const merged = new Set<string>([...fromStatic, ...fromLocal]);
    return [...merged].sort();
  }

  private async fetchApiSkus(): Promise<string[]> {
    try {
      const { data } = await apiClient.get(endpoints.skus);
      const payload = data as { skus?: string[] };
      return payload.skus ?? [];
    } catch {
      return [];
    }
  }

  private async fetchStaticSkus(): Promise<string[]> {
    try {
      const res = await fetch('/sku_list.json', { cache: 'no-store' });
      if (!res.ok) return [];
      const payload = (await res.json()) as { skus?: string[] };
      return payload.skus ?? [];
    } catch {
      return [];
    }
  }
}

export const dataSource: ForecastDataSource = new ControllerAdapter();
