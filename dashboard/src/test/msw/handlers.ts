import { http, HttpResponse } from 'msw';
import {
  FIXTURE_SKUS,
  fixtureSkuDetail,
  fixtureSkuHistory,
  fixtureRunStatus,
} from '../fixtures/forecastResult.fixture';

let nextRunId = 2000;

export const handlers = [
  // GET /skus/:sku/latest
  http.get('*/skus/:sku/latest', ({ params }) => {
    return HttpResponse.json(fixtureSkuDetail(String(params.sku)));
  }),

  // GET /skus/:sku/history
  http.get('*/skus/:sku/history', ({ params }) => {
    return HttpResponse.json(fixtureSkuHistory(String(params.sku)));
  }),

  // GET /runs/:runId
  http.get('*/runs/:runId', ({ params }) => {
    return HttpResponse.json(fixtureRunStatus(Number(params.runId)));
  }),

  // POST /runs
  http.post('*/runs', () => {
    const runId = nextRunId++;
    return HttpResponse.json({
      run_id: runId,
      jobs: FIXTURE_SKUS.length,
      status: 'queued',
    });
  }),

  // POST /skus/:sku/forecast
  http.post('*/skus/:sku/forecast', () => {
    const runId = nextRunId++;
    return HttpResponse.json({
      run_id: runId,
      jobs: 1,
      status: 'queued',
    });
  }),
];
