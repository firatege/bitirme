import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  useSkuHistory,
  useSkuLatest,
  useTriggerSkuForecast,
} from '@/shared/api/hooks';
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
import { useRunHistoryStore } from '@/features/run-history/runHistoryStore';

export function SkuDetailPage() {
  const { sku = '' } = useParams<{ sku: string }>();
  const latest = useSkuLatest(sku);
  const history = useSkuHistory(sku);
  const trigger = useTriggerSkuForecast();
  const recordRun = useRunHistoryStore((s) => s.record);
  const [showConfirm, setShowConfirm] = useState(false);

  const handleConfirm = async () => {
    setShowConfirm(false);
    try {
      const res = await trigger.mutateAsync(sku);
      recordRun({ run_id: res.run_id, trigger: 'sku', sku });
      toast(
        `Run #${res.run_id} kuyruğa eklendi (${res.jobs} job)`,
        'success',
      );
    } catch (e) {
      toast(
        e instanceof Error ? e.message : 'Run tetiklenemedi',
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
        <Button
          variant="secondary"
          size="sm"
          className="ml-auto"
          onClick={() => setShowConfirm(true)}
          disabled={trigger.isPending}
        >
          {trigger.isPending ? 'Tetikleniyor…' : 'Bu SKU için yeniden çalıştır'}
        </Button>
      </div>

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

      {history.data && history.data.history.length > 0 && (
        <HistoryChart entries={history.data.history} />
      )}
    </div>
  );
}
