import { useTranslation } from 'react-i18next';
import { useRunStatus } from '@/shared/api/hooks';

interface Props {
  runId: number | null;
}

function calcEta(
  startedAt: string | null | undefined,
  completed: number,
  remaining: number,
): string | null {
  if (!startedAt || completed === 0 || remaining === 0) return null;
  const elapsedMs = Date.now() - new Date(startedAt).getTime();
  if (elapsedMs < 5_000) return null;
  const msPerSku = elapsedMs / completed;
  const etaMs = msPerSku * remaining;
  const etaMin = Math.round(etaMs / 60_000);
  if (etaMin < 1) return '< 1 dk';
  return `~${etaMin} dk`;
}

export function RunProgressBadge({ runId }: Props) {
  const { t } = useTranslation();
  const status = useRunStatus(runId);
  if (runId == null || !status.data) return null;

  const s = status.data;
  const j = s.jobs;
  const total = j.completed + j.running + j.queued + j.failed;
  const pct = total > 0 ? Math.round((j.completed / total) * 100) : 0;
  const eta = s.status === 'running'
    ? calcEta(s.started_at, j.completed, j.queued + j.running)
    : null;

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2 text-xs">
        <span className="text-slate-500 dark:text-stone-400">
          {t('run_trigger.run_label', { runId })}
        </span>
        <StatusPill status={s.status} label={t(`status.${s.status}`, { defaultValue: s.status })} />
        <span className="tabular-nums text-slate-600 dark:text-stone-300 font-medium">
          {j.completed}/{total}
        </span>
        {eta && (
          <span className="text-slate-400 dark:text-stone-500">
            {eta} kaldı
          </span>
        )}
        {s.status === 'running' && (
          <span className="text-slate-400 dark:text-stone-500">
            {pct}%
          </span>
        )}
      </div>
      {s.status === 'running' && total > 0 && (
        <div className="h-1 w-40 rounded-full bg-slate-200 dark:bg-surface-2 overflow-hidden">
          <div
            className="h-full rounded-full bg-sky-500 transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}

const PILL_STYLES: Record<string, string> = {
  queued:
    'bg-slate-100 text-slate-700 ring-slate-200 dark:bg-surface-2 dark:text-stone-300 dark:ring-surface-line',
  running:
    'bg-sky-100 text-sky-700 ring-sky-200 dark:bg-sky-500/15 dark:text-sky-300 dark:ring-sky-500/30',
  completed:
    'bg-brand-100 text-brand-800 ring-brand-200 dark:bg-brand-500/15 dark:text-brand-300 dark:ring-brand-500/30',
  failed:
    'bg-rose-100 text-rose-700 ring-rose-200 dark:bg-rose-500/15 dark:text-rose-300 dark:ring-rose-500/30',
};

function StatusPill({ status, label }: { status: string; label: string }) {
  return (
    <span
      className={`rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${
        PILL_STYLES[status] ?? PILL_STYLES.queued
      }`}
    >
      {label}
    </span>
  );
}
