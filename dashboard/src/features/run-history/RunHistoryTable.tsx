import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useQueries } from '@tanstack/react-query';
import { dataSource } from '@/shared/api/source';
import { queryKeys } from '@/shared/api/queryKeys';
import { useRunHistoryStore } from './runHistoryStore';
import { Card } from '@/shared/ui/Card';
import { EmptyState } from '@/shared/ui/EmptyState';
import { Button } from '@/shared/ui/Button';

const STATUS_TONE: Record<string, string> = {
  queued: 'bg-slate-100 text-slate-700 ring-slate-200',
  running: 'bg-blue-100 text-blue-700 ring-blue-200',
  completed: 'bg-emerald-100 text-emerald-700 ring-emerald-200',
  failed: 'bg-red-100 text-red-700 ring-red-200',
};

export function RunHistoryTable() {
  const entries = useRunHistoryStore((s) => s.entries);
  const clear = useRunHistoryStore((s) => s.clear);

  const queries = useQueries({
    queries: entries.map((e) => ({
      queryKey: queryKeys.run(e.run_id),
      queryFn: () => dataSource.getRunStatus(e.run_id),
      refetchInterval: (query: { state: { data?: { status?: string } } }) => {
        const s = query.state.data?.status;
        return s === 'completed' || s === 'failed' ? false : 5_000;
      },
      retry: 0,
    })),
  });

  const rows = useMemo(
    () =>
      entries.map((e, i) => ({
        ...e,
        status: queries[i]?.data,
        isLoading: queries[i]?.isLoading ?? false,
        isError: queries[i]?.isError ?? false,
      })),
    [entries, queries],
  );

  if (entries.length === 0) {
    return (
      <EmptyState
        title="Henüz çalışma yok"
        description="Ana ekrandan 'Tümünü Çalıştır' veya bir SKU detayından yeniden çalıştır butonuna tıklayın. Tetiklediğiniz tüm runlar burada listelenir."
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-500">
          Toplam {entries.length} kayıtlı çalışma · son 50 saklanır
        </span>
        <Button size="sm" variant="secondary" onClick={clear}>
          Geçmişi Temizle
        </Button>
      </div>
      <Card>
        <table className="w-full text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3 text-left">Run #</th>
              <th className="px-4 py-3 text-left">Tetikleyen</th>
              <th className="px-4 py-3 text-left">Durum</th>
              <th className="px-4 py-3 text-right">Job (tamam/toplam)</th>
              <th className="px-4 py-3 text-left">Bitiş</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const s = r.status;
              const total =
                (s?.jobs?.queued ?? 0) +
                (s?.jobs?.running ?? 0) +
                (s?.jobs?.completed ?? 0) +
                (s?.jobs?.failed ?? 0);
              return (
                <tr
                  key={r.run_id}
                  className="border-b border-slate-100 last:border-0 hover:bg-slate-50"
                >
                  <td className="px-4 py-3 font-mono text-xs">
                    <Link
                      to={`/runs/${r.run_id}`}
                      className="text-slate-900 hover:underline"
                    >
                      #{r.run_id}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {r.trigger === 'sku' ? (
                      <span>
                        SKU:{' '}
                        <Link
                          to={`/skus/${encodeURIComponent(r.sku ?? '')}`}
                          className="font-mono hover:underline"
                        >
                          {r.sku}
                        </Link>
                      </span>
                    ) : (
                      'Toplu'
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {r.isError ? (
                      <span className="text-xs text-red-600">
                        ulaşılamadı
                      </span>
                    ) : s ? (
                      <span
                        className={`rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${
                          STATUS_TONE[s.status] ?? STATUS_TONE['queued']
                        }`}
                      >
                        {s.status}
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">…</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {s
                      ? `${s.jobs.completed}/${total}${
                          s.jobs.failed ? ` (${s.jobs.failed} ✗)` : ''
                        }`
                      : '—'}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500">
                    {s?.completed_at ? s.completed_at.slice(0, 19) : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
