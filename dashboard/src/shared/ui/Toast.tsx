import { create } from 'zustand';
import { useEffect } from 'react';
import { cn } from '@/shared/lib/cn';

type ToastTone = 'info' | 'success' | 'error';

interface ToastItem {
  id: number;
  message: string;
  tone: ToastTone;
  duration: number;
}

interface ToastStore {
  items: ToastItem[];
  push: (msg: string, tone?: ToastTone, duration?: number) => void;
  dismiss: (id: number) => void;
}

let nextId = 1;

const useToastStore = create<ToastStore>((set) => ({
  items: [],
  push: (msg, tone = 'info', duration = 4000) =>
    set((state) => ({
      items: [...state.items, { id: nextId++, message: msg, tone, duration }],
    })),
  dismiss: (id) =>
    set((state) => ({ items: state.items.filter((i) => i.id !== id) })),
}));

export function toast(msg: string, tone: ToastTone = 'info', duration = 4000) {
  useToastStore.getState().push(msg, tone, duration);
}

const toneClass: Record<ToastTone, string> = {
  info: 'bg-slate-900 text-white',
  success: 'bg-emerald-600 text-white',
  error: 'bg-red-600 text-white',
};

export function ToastViewport() {
  const items = useToastStore((s) => s.items);
  const dismiss = useToastStore((s) => s.dismiss);

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {items.map((t) => (
        <ToastBubble
          key={t.id}
          item={t}
          onDismiss={() => dismiss(t.id)}
        />
      ))}
    </div>
  );
}

function ToastBubble({
  item,
  onDismiss,
}: {
  item: ToastItem;
  onDismiss: () => void;
}) {
  useEffect(() => {
    const t = setTimeout(onDismiss, item.duration);
    return () => clearTimeout(t);
  }, [item.duration, onDismiss]);

  return (
    <button
      onClick={onDismiss}
      className={cn(
        'pointer-events-auto rounded-lg px-4 py-2 text-sm shadow-lg transition-all',
        toneClass[item.tone],
      )}
    >
      {item.message}
    </button>
  );
}
