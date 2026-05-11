import { useTranslation } from 'react-i18next';
import { useRunStatus } from '@/shared/api/hooks';

interface Props {
  runId: number | null;
}

// Compact running-state pill: "Run #42 ● completed 4/17" next to a trigger
// button. Shared between the global RunTrigger and per-SKU detail page so the
// running state survives a refresh in both surfaces.
export function RunProgressBadge({ runId }: Props) {
  const { t } = useTranslation();
  const status = useRunStatus(runId);
  if (runId == null || !status.data) return null;

  const j = status.data.jobs;
  const total = j.completed + j.running + j.queued + j.failed;
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-slate-500">
        {t('run_trigger.run_label', { runId })}
      </span>
      <StatusPill status={status.data.status} label={t(`status.${status.data.status}`, { defaultValue: status.data.status })} />
      <span className="text-slate-500 tabular-nums">
        {j.completed}/{total}
      </span>
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
