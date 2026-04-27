import { http, HttpResponse } from 'msw';
import {
  fixtureRunStatus,
  fixtureSkuDetail,
  fixtureSkuHistory,
  FIXTURE_SKUS,
} from '../fixtures/forecastResult.fixture';
import { env } from '@/shared/config/env';

const API = env.apiBaseUrl;

let nextRunId = 1001;

export const handlers = [
  http.get(`${API}/healthz`, () => HttpResponse.json({ ok: true })),

  http.get(`${API}/readyz`, () =>
    HttpResponse.json({ db_ok: true, worker_ok: true }),
  ),

  http.get(`${API}/skus/:sku/latest`, ({ params }) => {
    const sku = decodeURIComponent(String(params.sku));
    if (!FIXTURE_SKUS.includes(sku as (typeof FIXTURE_SKUS)[number])) {
      return HttpResponse.json({ error: 'sku not found' }, { status: 404 });
    }
    return HttpResponse.json(fixtureSkuDetail(sku));
  }),

  http.get(`${API}/skus/:sku/history`, ({ params }) => {
    const sku = decodeURIComponent(String(params.sku));
    return HttpResponse.json(fixtureSkuHistory(sku));
  }),

  http.post(`${API}/runs`, () => {
    const runId = nextRunId++;
    return HttpResponse.json(
      { run_id: runId, jobs: FIXTURE_SKUS.length, status: 'queued' },
      { status: 202 },
    );
  }),

  http.post(`${API}/skus/:sku/forecast`, () => {
    const runId = nextRunId++;
    return HttpResponse.json(
      { run_id: runId, jobs: 1, status: 'queued' },
      { status: 202 },
    );
  }),

  http.get(`${API}/runs/:runId`, ({ params }) => {
    const runId = Number(params.runId);
    return HttpResponse.json(fixtureRunStatus(runId));
  }),

  http.get(`${API}/runs/:runId/skus/:sku`, ({ params }) => {
    const sku = decodeURIComponent(String(params.sku));
    const detail = fixtureSkuDetail(sku);
    detail.run_id = Number(params.runId);
    return HttpResponse.json(detail);
  }),
];
