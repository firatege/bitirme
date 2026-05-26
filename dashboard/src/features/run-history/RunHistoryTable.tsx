import { useNavigate } from 'react-router-dom';
import { useRunsList } from '@/shared/api/hooks';
import { Card } from '@/shared/ui/Card';
import { EmptyState } from '@/shared/ui/EmptyState';
import { Skeleton } from '@/shared/ui/Skeleton';

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
  const navigate = useNavigate();
  const { data: runs, isLoading, isError } = useRunsList();

  if (isLoading) {
    return <Skeleton className="h-64" />;
  }

  if (isError) {
    return (
      <EmptyState
        title="Çalışmalar yüklenemedi"
        description="Controller'a ulaşılamadı. Servis ayakta mı kontrol edin; sayfa otomatik yeniden denenecek."
      />
    );
  }

  if (!runs || runs.length === 0) {
    return (
      <EmptyState
        title="Henüz çalışma yok"
        description="Ana ekrandan 'Tümünü Çalıştır' veya bir SKU detayından yeniden çalıştır butonuna tıklayın. Tüm runlar burada listelenir."
      />
    );
  }

  return (
    <div className="space-y-3">
      <span className="text-xs text-slate-500 dark:text-stone-400">
        {runs.length} çalışma · sunucudan canlı
      </span>
      <Card>
        <table className="w-full text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500 dark:border-surface-line dark:bg-surface-2/30 dark:text-stone-400">
            <tr>
              <th className="px-4 py-3 text-left font-medium">Run #</th>
              <th className="px-4 py-3 text-left font-medium">Durum</th>
              <th className="px-4 py-3 text-right font-medium">Job (tamam/toplam)</th>
              <th className="px-4 py-3 text-left font-medium">Bitiş</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => {
              const total =
                (r.jobs?.queued ?? 0) +
                (r.jobs?.running ?? 0) +
                (r.jobs?.completed ?? 0) +
                (r.jobs?.failed ?? 0);
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
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${
                        STATUS_TONE[r.status] ?? STATUS_TONE['queued']
                      }`}
                    >
                      {r.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-700 dark:text-stone-200">
                    {`${r.jobs.completed}/${total}${
                      r.jobs.failed ? ` (${r.jobs.failed} hata)` : ''
                    }`}
                  </td>
                  <td className="px-4 py-3 font-mono text-[11px] text-slate-500 dark:text-stone-400">
                    {r.completed_at ? r.completed_at.slice(0, 19) : '—'}
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
