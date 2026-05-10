import { type ReactNode } from 'react';
import { cn } from '@/shared/lib/cn';

export function Card({
  children,
  className,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  accent: _accent = false,
}: {
  children: ReactNode;
  className?: string;
  accent?: boolean;
}) {
  return (
    <div
      className={cn(
        'rounded-lg border bg-white dark:bg-surface-1',
        'border-slate-200 dark:border-surface-line',
        className,
      )}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  /** legacy — eyebrow artık kullanılmıyor, geriye dönük kabul edilir. */
  eyebrow?: string;
}) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-3 dark:border-surface-line">
      <div className="min-w-0">
        <h3 className="truncate text-sm font-medium text-slate-900 dark:text-stone-50">
          {title}
        </h3>
        {subtitle && (
          <p className="mt-0.5 line-clamp-2 text-xs text-slate-500 dark:text-stone-200/50">
            {subtitle}
          </p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export function CardBody({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn('px-5 py-4', className)}>{children}</div>;
}
