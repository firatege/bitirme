import { cn } from '@/shared/lib/cn';
import type { ReactNode } from 'react';

export function Stat({
  label,
  value,
  hint,
  tone = 'default',
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: 'default' | 'critical' | 'warning' | 'success';
}) {
  const toneClass =
    tone === 'critical'
      ? 'text-red-700 dark:text-red-400'
      : tone === 'warning'
        ? 'text-orange-700 dark:text-orange-400'
        : tone === 'success'
          ? 'text-green-700 dark:text-green-400'
          : 'text-slate-900 dark:text-slate-100';
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {label}
      </div>
      <div className={cn('mt-1 text-2xl font-semibold', toneClass)}>
        {value}
      </div>
      {hint && (
        <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          {hint}
        </div>
      )}
    </div>
  );
}
