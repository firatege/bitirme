import { apiClient } from './client';
import { endpoints } from './endpoints';
import { readSeenSkus } from '@/shared/lib/seenSkus';
import { env } from '@/shared/config/env';
import {
  SkuDetailSchema,
  SkuHistorySchema,
  type SkuDetail,
  type SkuHistory,
} from '@/entities/sku/schema';
import {
  CreateRunResponseSchema,
  RunStatusSchema,
  type CreateRunResponse,
  type RunStatus,
} from '@/entities/run/schema';

export interface ForecastDataSource {
  getSkuLatest(sku: string): Promise<SkuDetail>;
  getSkuHistory(sku: string, limit?: number): Promise<SkuHistory>;
  getRunStatus(runId: number): Promise<RunStatus>;
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

  async getRunStatus(runId: number): Promise<RunStatus> {
    const { data } = await apiClient.get(endpoints.run(runId));
    return RunStatusSchema.parse(data);
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
    const fromStatic = await this.fetchStaticSkus();
    const fromLocal = readSeenSkus();
    const merged = new Set<string>([...fromStatic, ...fromLocal]);
    return [...merged].sort();
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
