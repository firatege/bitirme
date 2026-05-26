import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/shared/ui/Button';
import { ConfirmModal } from '@/shared/ui/ConfirmModal';
import { useCreateRun, useRunStatus, useSkuList } from '@/shared/api/hooks';
import { toast } from '@/shared/ui/Toast';
import { RunProgressBadge } from './RunProgressBadge';

const CONCURRENCY = 4;
const ACTIVE_RUN_KEY = 'bitirme.activeRunId';

function readPersistedRunId(): number | null {
  if (typeof localStorage === 'undefined') return null;
  const raw = localStorage.getItem(ACTIVE_RUN_KEY);
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

function persistRunId(runId: number | null): void {
  if (typeof localStorage === 'undefined') return;
  try {
    if (runId === null) {
      localStorage.removeItem(ACTIVE_RUN_KEY);
    } else {
      localStorage.setItem(ACTIVE_RUN_KEY, String(runId));
    }
  } catch {
    /* ignore quota errors */
  }
}

export function RunTrigger() {
  const { t } = useTranslation();
  const [runId, setRunId] = useState<number | null>(() => readPersistedRunId());
  const [showConfirm, setShowConfirm] = useState(false);
  const create = useCreateRun();
  const status = useRunStatus(runId);
  const skuList = useSkuList();

  const skuCount = skuList.data?.length ?? null;
  const estimatedMin = skuCount ? Math.ceil(skuCount / CONCURRENCY) * 2 : null;

  // Clear persisted runId once the run is fully done so the badge doesn't linger forever.
  useEffect(() => {
    const s = status.data;
    if (!s) return;
    if (s.status === 'completed' || s.status === 'failed') {
      const t = window.setTimeout(() => persistRunId(null), 60_000);
      return () => window.clearTimeout(t);
    }
  }, [status.data]);

  const handleConfirm = async () => {
    setShowConfirm(false);
    try {
      const res = await create.mutateAsync({
        concurrency: CONCURRENCY,
        check_drift: true,
      });
      setRunId(res.run_id);
      persistRunId(res.run_id);
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

  return (
    <div className="flex items-center gap-3">
      <ConfirmModal
        open={showConfirm}
        title={t('run_trigger.confirm.title')}
        confirmLabel={t('run_trigger.confirm.cta')}
        onConfirm={handleConfirm}
        onCancel={() => setShowConfirm(false)}
      >
        <p>
          {t('run_trigger.confirm.body_prefix')}{' '}
          <span className="font-semibold text-slate-900 dark:text-stone-100">
            {skuCount !== null
              ? t('run_trigger.confirm.body_count', { count: skuCount })
              : t('run_trigger.confirm.body_count_unknown')}
          </span>{' '}
          {t('run_trigger.confirm.body_suffix')}
        </p>
        <ul className="mt-2 space-y-1 text-xs text-slate-500 dark:text-stone-400">
          <li>
            <span className="font-medium">{t('run_trigger.confirm.concurrency')}:</span>{' '}
            {t('run_trigger.confirm.concurrency_value', { count: CONCURRENCY })}
          </li>
          {estimatedMin && (
            <li>
              <span className="font-medium">{t('run_trigger.confirm.eta')}:</span>{' '}
              ~{estimatedMin} {t('run_trigger.confirm.eta_unit')}
            </li>
          )}
          <li>
            <span className="font-medium">{t('run_trigger.confirm.drift')}:</span>{' '}
            {t('run_trigger.confirm.drift_value')}
          </li>
          <li className="pt-1 text-amber-600 dark:text-amber-400">
            {t('run_trigger.confirm.overwrite_warn')}
          </li>
        </ul>
      </ConfirmModal>

      <Button
        onClick={() => setShowConfirm(true)}
        disabled={create.isPending}
        variant="primary"
      >
        {create.isPending
          ? t('run_trigger.triggering')
          : t('actions.trigger_all')}
      </Button>
      {runId && <RunProgressBadge runId={runId} />}
    </div>
  );
}
