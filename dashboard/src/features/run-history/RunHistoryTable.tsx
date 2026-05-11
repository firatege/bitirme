import { useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQueries } from '@tanstack/react-query';
import { dataSource } from '@/shared/api/source';
import { queryKeys } from '@/shared/api/queryKeys';
import { useRunHistoryStore } from './runHistoryStore';
import { Card } from '@/shared/ui/Card';
import { EmptyState } from '@/shared/ui/EmptyState';
import { Button } from '@/shared/ui/Button';

const STATUS_TONE: Record<string, string> = {
  queued:
    'bg-slate-100 text-slate-700 ring-slate-200 dark:bg-surface-2 dark:text-stone-300 dark:ring-surface-line',
  running:
    'bg-sky-100 text-sky-700 ring-sky-200 dark:bg-sky-500/15 dark:text-sky-300 dark:ring-sky-500/30',
  completed:
    'bg-brand-100 text-brand-800 ring-brand-200 dark:bg-brand-500/15 dark:text-brand-300 dark:ring-brand-500/30',
  failed:
    'bg-rose-100 text-rose-700 ring-rose-200 dark:bg-rose-500/15 dark:text-rose-300 dark:ring-rose-500/30',
};

export function RunHistoryTable() {
  const entries = useRunHistoryStore((s) => s.entries);
  const clear = useRunHistoryStore((s) => s.clear);
  const navigate = useNavigate();

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
        <span className="text-xs text-slate-500 dark:text-stone-400">
          {entries.length} kayıtlı çalışma · son 50 saklanır
        </span>
        <Button size="sm" variant="secondary" onClick={clear}>
          Geçmişi Temizle
        </Button>
      </div>
      <Card>
        <table className="w-full text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500 dark:border-surface-line dark:bg-surface-2/30 dark:text-stone-400">
            <tr>
              <th className="px-4 py-3 text-left font-medium">Run #</th>
              <th className="px-4 py-3 text-left font-medium">Tetikleyen</th>
              <th className="px-4 py-3 text-left font-medium">Durum</th>
              <th className="px-4 py-3 text-right font-medium">Job (tamam/toplam)</th>
              <th className="px-4 py-3 text-left font-medium">Bitiş</th>
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
                  onClick={() => navigate(`/runs/${r.run_id}`)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      navigate(`/runs/${r.run_id}`);
                    }
                  }}
                  role="link"
                  tabIndex={0}
                  className="cursor-pointer border-b border-slate-100 transition-colors last:border-0 hover:bg-brand-50/40 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-brand-400 dark:border-surface-line/50 dark:hover:bg-surface-2/40"
                >
                  <td className="px-4 py-3 font-mono text-xs">
                    <span className="text-slate-900 dark:text-stone-200">
                      #{r.run_id}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-700 dark:text-stone-300">
                    {r.trigger === 'sku' ? (
                      <span>
                        SKU:{' '}
                        <Link
                          to={`/skus/${encodeURIComponent(r.sku ?? '')}`}
                          onClick={(e) => e.stopPropagation()}
                          className="font-mono text-brand-700 hover:underline dark:text-brand-300"
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
                      <span className="text-xs text-rose-600 dark:text-rose-400">
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
                      <span className="text-xs text-slate-400 dark:text-stone-200/30">…</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-700 dark:text-stone-200">
                    {s
                      ? `${s.jobs.completed}/${total}${
                          s.jobs.failed ? ` (${s.jobs.failed} hata)` : ''
                        }`
                      : '—'}
                  </td>
                  <td className="px-4 py-3 font-mono text-[11px] text-slate-500 dark:text-stone-400">
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
