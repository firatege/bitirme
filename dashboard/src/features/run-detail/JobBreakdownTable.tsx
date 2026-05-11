import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { fmtDec } from '@/shared/lib/format';
import { cn } from '@/shared/lib/cn';
import type { RunJob } from '@/entities/run/schema';

interface Props {
  jobs: RunJob[];
}

const STATUS_ORDER = ['failed', 'running', 'claimed', 'queued', 'completed'] as const;

const STATUS_TONES: Record<string, string> = {
  queued:
    'bg-slate-100 text-slate-700 ring-slate-200 dark:bg-surface-2 dark:text-stone-300 dark:ring-surface-line',
  claimed:
    'bg-slate-100 text-slate-700 ring-slate-200 dark:bg-surface-2 dark:text-stone-300 dark:ring-surface-line',
  running:
    'bg-sky-100 text-sky-700 ring-sky-200 dark:bg-sky-500/15 dark:text-sky-300 dark:ring-sky-500/30',
  completed:
    'bg-brand-100 text-brand-800 ring-brand-200 dark:bg-brand-500/15 dark:text-brand-300 dark:ring-brand-500/30',
  failed:
    'bg-rose-100 text-rose-700 ring-rose-200 dark:bg-rose-500/15 dark:text-rose-300 dark:ring-rose-500/30',
};

export function JobBreakdownTable({ jobs }: Props) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState<string | 'all'>('all');
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const grouped = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const j of jobs) {
      counts[j.status] = (counts[j.status] ?? 0) + 1;
    }
    return counts;
  }, [jobs]);

  const filtered = useMemo(
    () => (filter === 'all' ? jobs : jobs.filter((j) => j.status === filter)),
    [jobs, filter],
  );

  const toggle = (jobId: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(jobId)) next.delete(jobId);
      else next.add(jobId);
      return next;
    });
  };

  return (
    <Card>
      <CardHeader
        title={t('run_detail.jobs.title')}
        subtitle={t('run_detail.jobs.subtitle', { total: jobs.length })}
      />
      <CardBody className="space-y-3">
        <div className="flex flex-wrap gap-2">
          <FilterChip
            active={filter === 'all'}
            onClick={() => setFilter('all')}
            label={`${t('run_detail.jobs.filter_all')} (${jobs.length})`}
          />
          {STATUS_ORDER.map((s) => {
            const count = grouped[s] ?? 0;
            if (count === 0) return null;
            return (
              <FilterChip
                key={s}
                active={filter === s}
                onClick={() => setFilter(s)}
                label={`${t(`status.${s}`, { defaultValue: s })} (${count})`}
                tone={STATUS_TONES[s]}
              />
            );
          })}
        </div>

        <div className="overflow-hidden rounded-lg border border-slate-200 dark:border-surface-line">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500 dark:border-surface-line dark:bg-surface-2/30 dark:text-stone-400">
              <tr>
                <th className="px-3 py-2 text-left font-medium">SKU</th>
                <th className="px-3 py-2 text-left font-medium">
                  {t('run_detail.jobs.status')}
                </th>
                <th className="px-3 py-2 text-left font-medium">
                  {t('run_detail.jobs.mode')}
                </th>
                <th className="px-3 py-2 text-right font-medium">
                  {t('run_detail.jobs.attempts')}
                </th>
                <th className="px-3 py-2 text-right font-medium">MAE</th>
                <th className="px-3 py-2 text-left font-medium">
                  {t('run_detail.jobs.error')}
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-3 py-6 text-center text-sm text-slate-500 dark:text-stone-400"
                  >
                    {t('run_detail.jobs.empty')}
                  </td>
                </tr>
              ) : (
                filtered.map((j) => {
                  const isOpen = expanded.has(j.job_id);
                  const errTone = STATUS_TONES[j.status] ?? STATUS_TONES.queued;
                  return (
                    <tr
                      key={j.job_id}
                      className={cn(
                        'border-b border-slate-100 transition-colors last:border-0 hover:bg-brand-50/40 dark:border-surface-line/50 dark:hover:bg-surface-2/40',
                      )}
                    >
                      <td className="px-3 py-2 font-mono text-xs">
                        <Link
                          to={`/skus/${encodeURIComponent(j.sku)}`}
                          className="text-slate-800 hover:underline dark:text-stone-100"
                        >
                          {j.sku}
                        </Link>
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={cn(
                            'rounded-md px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset',
                            errTone,
                          )}
                        >
                          {j.status}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-xs text-slate-600 dark:text-stone-300">
                        {j.sku_mode ?? '—'}
                      </td>
                      <td className="px-3 py-2 text-right text-xs tabular-nums">
                        {j.attempts}
                      </td>
                      <td className="px-3 py-2 text-right text-xs tabular-nums">
                        {j.winning_mae != null ? fmtDec(j.winning_mae) : '—'}
                      </td>
                      <td className="px-3 py-2 text-xs">
                        {j.last_error ? (
                          <button
                            type="button"
                            onClick={() => toggle(j.job_id)}
                            className="max-w-md truncate text-left text-rose-700 hover:underline dark:text-rose-300"
                            title={t('run_detail.jobs.expand_error')}
                          >
                            {isOpen ? '▼ ' : '▶ '}
                            {j.last_error.split('\n')[0]?.slice(0, 80) ?? ''}
                          </button>
                        ) : (
                          <span className="text-slate-400 dark:text-stone-500">
                            —
                          </span>
                        )}
                        {isOpen && j.last_error && (
                          <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-slate-900/95 p-2 text-[11px] leading-snug text-stone-100">
                            {j.last_error}
                          </pre>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </CardBody>
    </Card>
  );
}

function FilterChip({
  active,
  onClick,
  label,
  tone,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  tone?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-md px-2.5 py-1 text-xs font-medium ring-1 ring-inset transition-colors',
        active
          ? 'bg-slate-900 text-white ring-slate-900 dark:bg-stone-100 dark:text-slate-900 dark:ring-stone-100'
          : tone ??
              'bg-slate-100 text-slate-700 ring-slate-200 hover:bg-slate-200 dark:bg-surface-2 dark:text-stone-300 dark:ring-surface-line dark:hover:bg-surface-2/60',
      )}
    >
      {label}
    </button>
  );
}
