import { cn } from '@/shared/lib/cn';
import type { HTMLAttributes } from 'react';

export function Badge({
  className,
  ...props
}: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset',
        className,
      )}
      {...props}
    />
  );
}
