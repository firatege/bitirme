import { RunHistoryTable } from '@/features/run-history/RunHistoryTable';

export function RunsPage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-medium text-slate-900 dark:text-stone-50">
          Çalışmalar
        </h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-stone-400">
          Tetiklediğiniz tüm forecast run&apos;larının canlı durumu.
        </p>
      </header>
      <RunHistoryTable />
    </div>
  );
}
