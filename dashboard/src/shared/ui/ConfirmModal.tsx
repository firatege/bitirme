import { type ReactNode, useEffect, useRef } from 'react';
import { Button } from './Button';

export function ConfirmModal({
  open,
  title,
  confirmLabel = 'Onayla',
  onConfirm,
  onCancel,
  children,
}: {
  open: boolean;
  title: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  children?: ReactNode;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      onCancel={onCancel}
      className="w-full max-w-md overflow-hidden rounded-xl border border-slate-200 bg-white p-0 shadow-xl backdrop:bg-black/60 backdrop:backdrop-blur-sm dark:border-surface-line dark:bg-surface-1"
    >
      <div className="space-y-4 p-6">
        <h2 className="text-base font-medium text-slate-900 dark:text-stone-50">
          {title}
        </h2>
        <div className="text-sm text-slate-600 dark:text-stone-300">
          {children}
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" onClick={onCancel}>
            İptal
          </Button>
          <Button variant="primary" onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </dialog>
  );
}
