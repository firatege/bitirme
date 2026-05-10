import { type ReactNode } from 'react';
import { cn } from '@/shared/lib/cn';

type Tone = 'default' | 'success' | 'warning' | 'critical' | 'brand';

const valueToneClasses: Record<Tone, string> = {
  default: 'text-slate-900 dark:text-stone-50',
  brand: 'text-brand-700 dark:text-brand-300',
  success: 'text-emerald-700 dark:text-emerald-400',
  warning: 'text-amber-700 dark:text-amber-400',
  critical: 'text-rose-700 dark:text-rose-400',
};

export function Stat({
  label,
  value,
  tone = 'default',
  hint,
  // ikon ve trend artık varsayılan olarak kullanılmıyor — sade görünüm.
}: {
  label: string;
  value: string;
  tone?: Tone;
  hint?: string;
  icon?: ReactNode;
  trend?: { dir: 'up' | 'down' | 'flat'; label: string };
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 dark:border-surface-line dark:bg-surface-1">
      <p className="text-xs text-slate-500 dark:text-stone-400">{label}</p>
      <p
        className={cn(
          'mt-1 text-2xl font-medium tabular-nums',
          valueToneClasses[tone],
        )}
      >
        {value}
      </p>
      {hint && (
        <p className="mt-0.5 text-xs text-slate-400 dark:text-stone-200/40">
          {hint}
        </p>
      )}
    </div>
  );
}
