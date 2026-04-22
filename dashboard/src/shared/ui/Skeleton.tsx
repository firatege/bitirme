import { cn } from '@/shared/lib/cn';
import type { HTMLAttributes } from 'react';

export function Skeleton({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('animate-pulse rounded-md bg-slate-200', className)}
      {...props}
    />
  );
}
