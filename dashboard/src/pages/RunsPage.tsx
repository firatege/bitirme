import { RunHistoryTable } from '@/features/run-history/RunHistoryTable';

export function RunsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Çalışmalar</h1>
        <p className="text-sm text-slate-500">
          Tetiklediğiniz tüm forecast run'larının canlı durumu.
        </p>
      </div>
      <RunHistoryTable />
    </div>
  );
}
