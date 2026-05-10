import { useState } from 'react';
import { Button } from '@/shared/ui/Button';
import { ConfirmModal } from '@/shared/ui/ConfirmModal';
import { useCreateRun, useRunStatus, useSkuList } from '@/shared/api/hooks';
import { useRunHistoryStore } from '@/features/run-history/runHistoryStore';
import { toast } from '@/shared/ui/Toast';

const CONCURRENCY = 4;

export function RunTrigger() {
  const [runId, setRunId] = useState<number | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const create = useCreateRun();
  const status = useRunStatus(runId);
  const recordRun = useRunHistoryStore((s) => s.record);
  const skuList = useSkuList();

  const skuCount = skuList.data?.length ?? null;
  const estimatedMin = skuCount ? Math.ceil(skuCount / CONCURRENCY) * 2 : null;

  const handleConfirm = async () => {
    setShowConfirm(false);
    try {
      const res = await create.mutateAsync({
        concurrency: CONCURRENCY,
        check_drift: true,
      });
      setRunId(res.run_id);
      recordRun({ run_id: res.run_id, trigger: 'all' });
      toast(`Run #${res.run_id} kuyruğa eklendi (${res.jobs} job)`, 'success');
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Run tetiklenemedi', 'error');
    }
  };

  return (
    <div className="flex items-center gap-3">
      <ConfirmModal
        open={showConfirm}
        title="Tüm SKU'ları Çalıştır"
        confirmLabel="Çalıştır"
        onConfirm={handleConfirm}
        onCancel={() => setShowConfirm(false)}
      >
        <p>
          Portföydeki{' '}
          <span className="font-semibold text-slate-900 dark:text-stone-100">
            {skuCount !== null ? `${skuCount} SKU` : "tüm SKU'lar"}
          </span>{' '}
          için tahmin pipeline'ı başlatılacak.
        </p>
        <ul className="mt-2 space-y-1 text-xs text-slate-500 dark:text-stone-400">
          <li>
            <span className="font-medium">Eşzamanlılık:</span> {CONCURRENCY} iş paralel
          </li>
          {estimatedMin && (
            <li>
              <span className="font-medium">Tahmini süre:</span> ~{estimatedMin} dk
            </li>
          )}
          <li>
            <span className="font-medium">Drift kontrolü:</span> aktif
          </li>
          <li className="pt-1 text-amber-600 dark:text-amber-400">
            Mevcut tahminlerin üzerine yazılacak.
          </li>
        </ul>
      </ConfirmModal>

      <Button
        onClick={() => setShowConfirm(true)}
        disabled={create.isPending}
        variant="primary"
      >
        {create.isPending ? 'Tetikleniyor…' : 'Tümünü Çalıştır'}
      </Button>
      {runId && status.data && (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-slate-500">Run #{runId}</span>
          <StatusBadge status={status.data.status} />
          <span className="text-slate-500">
            {status.data.jobs.completed}/
            {status.data.jobs.completed +
              status.data.jobs.running +
              status.data.jobs.queued +
              status.data.jobs.failed}
          </span>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    queued:
      'bg-slate-100 text-slate-700 ring-slate-200 dark:bg-surface-2 dark:text-stone-300 dark:ring-surface-line',
    running:
      'bg-sky-100 text-sky-700 ring-sky-200 dark:bg-sky-500/15 dark:text-sky-300 dark:ring-sky-500/30',
    completed:
      'bg-brand-100 text-brand-800 ring-brand-200 dark:bg-brand-500/15 dark:text-brand-300 dark:ring-brand-500/30',
    failed:
      'bg-rose-100 text-rose-700 ring-rose-200 dark:bg-rose-500/15 dark:text-rose-300 dark:ring-rose-500/30',
  };
  return (
    <span
      className={`rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${
        map[status] ?? map['queued']
      }`}
    >
      {status}
    </span>
  );
}
