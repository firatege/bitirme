import { Button } from './Button';

export function ErrorState({
  title,
  message,
  onRetry,
}: {
  title: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-rose-300/70 bg-white py-16 text-center dark:border-rose-500/30 dark:bg-surface-1/40">
      <div className="rounded-full bg-rose-100 p-3 ring-1 ring-inset ring-rose-200 dark:bg-rose-500/15 dark:ring-rose-500/30">
        <svg
          className="h-6 w-6 text-rose-600 dark:text-rose-400"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
          />
        </svg>
      </div>
      <h2 className="text-lg font-semibold text-slate-900 dark:text-stone-50">
        {title}
      </h2>
      {message && (
        <p className="max-w-md text-sm text-slate-500 dark:text-stone-400">
          {message}
        </p>
      )}
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          Tekrar Dene
        </Button>
      )}
    </div>
  );
}
