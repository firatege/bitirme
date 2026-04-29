import { useEffect, useState, type ReactNode } from 'react';
import { cn } from '@/shared/lib/cn';

/* ─── store (module-level, framework-agnostic) ─── */

type ToastType = 'success' | 'error' | 'info';

interface ToastItem {
  id: number;
  message: string;
  type: ToastType;
}

let nextId = 0;
let listeners: Array<() => void> = [];
let items: ToastItem[] = [];

function emit() {
  listeners.forEach((l) => l());
}

/** Show a toast notification. Call from anywhere (not just inside React). */
export function toast(message: string, type: ToastType = 'info'): void {
  const id = nextId++;
  items = [...items, { id, message, type }];
  emit();
  setTimeout(() => {
    items = items.filter((t) => t.id !== id);
    emit();
  }, 4_000);
}

function useToasts(): ToastItem[] {
  const [, rerender] = useState(0);
  useEffect(() => {
    const fn = () => rerender((n) => n + 1);
    listeners.push(fn);
    return () => {
      listeners = listeners.filter((l) => l !== fn);
    };
  }, []);
  return items;
}

/* ─── React component ─── */

const typeClasses: Record<ToastType, string> = {
  success:
    'border-green-200 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-900/30 dark:text-green-300',
  error:
    'border-red-200 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300',
  info: 'border-slate-200 bg-white text-slate-800 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200',
};

export function ToastViewport(): ReactNode {
  const toasts = useToasts();
  if (toasts.length === 0) return null;
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={cn(
            'pointer-events-auto animate-slide-in rounded-lg border px-4 py-2.5 text-sm shadow-lg',
            typeClasses[t.type],
          )}
        >
          {t.message}
        </div>
      ))}
    </div>
  );
}
