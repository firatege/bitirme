import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import {
  useSkuHistory,
  useSkuLatest,
  useSkuPredictions,
  useSkuTimeseries,
  useTriggerSkuForecast,
  useRunStatus,
} from '@/shared/api/hooks';
import { queryKeys } from '@/shared/api/queryKeys';
import { Skeleton } from '@/shared/ui/Skeleton';
import { ErrorState } from '@/shared/ui/ErrorState';
import { EmptyState } from '@/shared/ui/EmptyState';
import { Button } from '@/shared/ui/Button';
import { ConfirmModal } from '@/shared/ui/ConfirmModal';
import { toast } from '@/shared/ui/Toast';
import { UrgencyBadge } from '@/features/sku-list/UrgencyBadge';
import { urgencyOf } from '@/entities/sku/selectors';
import { OrderBreakdownCard } from '@/features/sku-detail/OrderBreakdownCard';
import { ModelProvenancePanel } from '@/features/sku-detail/ModelProvenancePanel';
import { StockoutGauge } from '@/features/sku-detail/StockoutGauge';
import { HistoryChart } from '@/features/sku-detail/HistoryChart';
import { DemandHistoryChart } from '@/features/sku-detail/DemandHistoryChart';
import { WhyThisNumberCard } from '@/features/sku-detail/WhyThisNumberCard';
import { RunDeltaCard } from '@/features/sku-detail/RunDeltaCard';
import { AnomalyFlagCard } from '@/features/sku-detail/AnomalyFlagCard';
import { BaselineComparisonCard } from '@/features/sku-detail/BaselineComparisonCard';
import { RunPinControl } from '@/features/sku-detail/RunPinControl';
import { RunProgressBadge } from '@/features/run-control/RunProgressBadge';

const SKU_RUN_KEY = (sku: string) => `bitirme.skuRun.${sku}`;

function readPersistedRunId(sku: string): number | null {
  if (!sku || typeof localStorage === 'undefined') return null;
  const raw = localStorage.getItem(SKU_RUN_KEY(sku));
  if (!raw) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

function persistRunId(sku: string, runId: number | null): void {
  if (!sku || typeof localStorage === 'undefined') return;
  try {
    if (runId == null) {
      localStorage.removeItem(SKU_RUN_KEY(sku));
    } else {
      localStorage.setItem(SKU_RUN_KEY(sku), String(runId));
    }
  } catch {
    /* ignore quota errors */
  }
}

export function SkuDetailPage() {
  const { t } = useTranslation();
  const { sku = '' } = useParams<{ sku: string }>();
  const qc = useQueryClient();
  const latest = useSkuLatest(sku);
  const history = useSkuHistory(sku);
  const timeseries = useSkuTimeseries(sku);
  const predictions = useSkuPredictions(sku);
  const trigger = useTriggerSkuForecast();
  const [showConfirm, setShowConfirm] = useState(false);
  const [activeRunId, setActiveRunId] = useState<number | null>(() =>
    readPersistedRunId(sku),
  );
  const runStatus = useRunStatus(activeRunId);

  // Switch the persisted runId when navigating between SKUs.
  useEffect(() => {
    setActiveRunId(readPersistedRunId(sku));
  }, [sku]);

  // When the run finishes, refresh the SKU panels so the user sees the new
  // recommendation/forecast without manually reloading. Clear the badge after
  // a minute so it doesn't linger forever on a completed run.
  useEffect(() => {
    const s = runStatus.data;
    if (!s) return;
    if (s.status === 'completed' || s.status === 'failed') {
      qc.invalidateQueries({ queryKey: queryKeys.skuLatest(sku) });
      qc.invalidateQueries({ queryKey: queryKeys.skuPredictions(sku, undefined) });
      qc.invalidateQueries({ queryKey: queryKeys.skuTimeseries(sku, 24) });
      qc.invalidateQueries({ queryKey: queryKeys.skuHistory(sku, 20) });
      const timer = window.setTimeout(() => {
        persistRunId(sku, null);
        setActiveRunId(null);
      }, 60_000);
      return () => window.clearTimeout(timer);
    }
  }, [runStatus.data, sku, qc]);

  const handleConfirm = async () => {
    setShowConfirm(false);
    try {
      const res = await trigger.mutateAsync(sku);
      setActiveRunId(res.run_id);
      persistRunId(sku, res.run_id);
      toast(
        t('run_trigger.queued', { runId: res.run_id, jobs: res.jobs }),
        'success',
      );
    } catch (e) {
      toast(
        e instanceof Error ? e.message : t('run_trigger.failed'),
        'error',
      );
    }
  };

  if (latest.isLoading)
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-3 gap-4">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
      </div>
    );

  if (latest.isError)
    return (
      <ErrorState
        title="SKU yüklenemedi"
        message={latest.error instanceof Error ? latest.error.message : ''}
        onRetry={() => latest.refetch()}
      />
    );

  const detail = latest.data;
  if (!detail)
    return (
      <EmptyState
        title="Bu SKU için sonuç yok"
        description="Önce bir run tetikleyin."
      />
    );

  const level = urgencyOf(detail.winning);

  return (
    <div className="space-y-6">
      <ConfirmModal
        open={showConfirm}
        title={`${sku} — Yeniden Çalıştır`}
        confirmLabel="Çalıştır"
        onConfirm={handleConfirm}
        onCancel={() => setShowConfirm(false)}
      >
        <p>
          <span className="font-semibold text-slate-900 dark:text-stone-100">
            {sku}
          </span>{' '}
          için tahmin pipeline'ı yeniden başlatılacak.
        </p>
        <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
          Bu SKU'nun mevcut tahmininin üzerine yazılacak.
        </p>
      </ConfirmModal>

      <div className="flex flex-wrap items-center gap-3">
        <Link
          to="/"
          className="text-xs text-slate-500 hover:text-slate-800 dark:text-stone-400 dark:hover:text-stone-100"
        >
          ← Geri
        </Link>
        <h1 className="font-mono text-lg text-slate-900 dark:text-stone-50">
          {sku}
        </h1>
        <UrgencyBadge level={level} />
        <div className="ml-auto flex items-center gap-3">
          <RunProgressBadge runId={activeRunId} />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setShowConfirm(true)}
            disabled={trigger.isPending}
          >
            {trigger.isPending ? t('run_trigger.triggering') : 'Bu SKU için yeniden çalıştır'}
          </Button>
        </div>
      </div>

      {history.data && history.data.history.length >= 3 && (
        <AnomalyFlagCard history={history.data.history} />
      )}

      {detail.recommendation && (
        <WhyThisNumberCard recommendation={detail.recommendation} />
      )}

      {history.data && history.data.history.length >= 2 && (
        <RunDeltaCard history={history.data.history} />
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {detail.recommendation && (
          <OrderBreakdownCard
            sku={sku}
            recommendation={detail.recommendation}
            onRequestRerun={() => setShowConfirm(true)}
          />
        )}
        <StockoutGauge
          p3m={detail.winning?.p_stockout_3m}
          p6m={detail.winning?.p_stockout_6m}
          eT={detail.winning?.e_t_stockout_mo}
        />
        {detail.winning && <ModelProvenancePanel win={detail.winning} />}
      </div>

      <DemandHistoryChart
        points={timeseries.data?.points}
        predictions={predictions.data?.points}
        isLoading={timeseries.isLoading}
      />

      <BaselineComparisonCard
        timeseries={timeseries.data?.points}
        predictions={predictions.data?.points}
      />

      {history.data && history.data.history.length > 0 && (
        <HistoryChart entries={history.data.history} />
      )}

      {history.data && history.data.history.length > 0 && (
        <RunPinControl sku={sku} history={history.data.history} />
      )}
    </div>
  );
}
