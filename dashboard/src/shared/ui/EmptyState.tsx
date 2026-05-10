export function EmptyState({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-slate-300 bg-white py-16 text-center dark:border-surface-line dark:bg-surface-1/40">
      <div className="rounded-full bg-brand-50 p-3 ring-1 ring-inset ring-brand-200 dark:bg-brand-500/10 dark:ring-brand-500/30">
        <svg
          className="h-6 w-6 text-brand-600 dark:text-brand-400"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5m8.25 3v6.75m0 0l-3-3m3 3l3-3M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z"
          />
        </svg>
      </div>
      <h2 className="text-lg font-semibold text-slate-900 dark:text-stone-50">
        {title}
      </h2>
      {description && (
        <p className="max-w-md text-sm text-slate-500 dark:text-stone-400">
          {description}
        </p>
      )}
    </div>
  );
}
