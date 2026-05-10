import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { cn } from '@/shared/lib/cn';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const variantClasses: Record<Variant, string> = {
  primary:
    'bg-brand-500 text-surface-0 hover:bg-brand-400 active:bg-brand-600 dark:bg-brand-400 dark:text-surface-0 dark:hover:bg-brand-300',
  secondary:
    'bg-white text-slate-800 ring-1 ring-inset ring-slate-200 hover:bg-slate-50 dark:bg-surface-1 dark:text-stone-100 dark:ring-surface-line dark:hover:bg-surface-2',
  ghost:
    'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-stone-400 dark:hover:bg-surface-2 dark:hover:text-stone-100',
  danger:
    'bg-rose-700 text-white hover:bg-rose-600 dark:bg-rose-600 dark:hover:bg-rose-500',
};

const sizeClasses: Record<Size, string> = {
  sm: 'px-2.5 py-1 text-xs',
  md: 'px-3.5 py-1.5 text-sm',
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', size = 'md', className, disabled, type = 'button', ...rest }, ref) => (
    <button
      ref={ref}
      disabled={disabled}
      type={type}
      className={cn(
        'inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors',
        'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-400',
        'disabled:pointer-events-none disabled:opacity-50',
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      {...rest}
    />
  ),
);

Button.displayName = 'Button';
