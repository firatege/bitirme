import { cn } from '@/shared/lib/cn';

type Tone = 'default' | 'success' | 'warning' | 'critical';

const toneClasses: Record<Tone, string> = {
  default: 'text-slate-900 dark:text-slate-100',
  success: 'text-green-700 dark:text-green-400',
  warning: 'text-amber-600 dark:text-amber-400',
  critical: 'text-red-700 dark:text-red-400',
};

export function Stat({
  label,
  value,
  tone = 'default',
  hint,
}: {
  label: string;
  value: string;
  tone?: Tone;
  hint?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-5 py-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
        {label}
      </p>
      <p className={cn('mt-1 text-2xl font-semibold tabular-nums', toneClasses[tone])}>
        {value}
      </p>
      {hint && (
        <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
          {hint}
        </p>
      )}
    </div>
  );
}
