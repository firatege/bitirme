import { useTranslation } from 'react-i18next';
import {
  useClearSkuPin,
  useSetSkuPin,
  useSkuPin,
} from '@/shared/api/hooks';
import { Card, CardBody, CardHeader } from '@/shared/ui/Card';
import { Button } from '@/shared/ui/Button';
import { toast } from '@/shared/ui/Toast';
import type { SkuHistoryEntry } from '@/entities/sku/schema';

interface Props {
  sku: string;
  history: SkuHistoryEntry[];
}

// Soft-rollback control: lets the operator pin this SKU to a specific past run.
// While pinned, every read (latest detail, predictions) AND the warm-path
// cached spec uses that run instead of "most recently completed".
export function RunPinControl({ sku, history }: Props) {
  const { t } = useTranslation();
  const pin = useSkuPin(sku);
  const setPin = useSetSkuPin(sku);
  const clearPin = useClearSkuPin(sku);

  const completed = history.filter((h) => h.status === 'completed');
  if (completed.length === 0) return null;

  const pinnedRunId = pin.data?.pinned_run_id ?? null;
  const latestId = completed[0]?.run_id ?? null;

  const handlePin = async (runId: number) => {
    try {
      await setPin.mutateAsync(runId);
      toast(t('sku_detail.pin.pinned_toast', { runId }), 'success');
    } catch (e) {
      toast(e instanceof Error ? e.message : 'pin failed', 'error');
    }
  };

  const handleClear = async () => {
    try {
      await clearPin.mutateAsync();
      toast(t('sku_detail.pin.cleared_toast'), 'success');
    } catch (e) {
      toast(e instanceof Error ? e.message : 'clear failed', 'error');
    }
  };

  return (
    <Card>
      <CardHeader
        title={t('sku_detail.pin.title')}
        subtitle={
          pinnedRunId
            ? t('sku_detail.pin.subtitle_pinned', { runId: pinnedRunId })
            : t('sku_detail.pin.subtitle_unpinned')
        }
        action={
          pinnedRunId != null ? (
            <Button
              size="sm"
              variant="secondary"
              onClick={handleClear}
              disabled={clearPin.isPending}
            >
              {t('sku_detail.pin.clear')}
            </Button>
          ) : null
        }
      />
      <CardBody className="p-0">
        <table className="w-full text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500 dark:border-surface-line dark:bg-surface-2/30 dark:text-stone-400">
            <tr>
              <th className="px-4 py-2 text-left font-medium">Run</th>
              <th className="px-4 py-2 text-left font-medium">
                {t('sku_detail.pin.completed_at')}
              </th>
              <th className="px-4 py-2 text-left font-medium">
                {t('sku_detail.pin.model')}
              </th>
              <th className="px-4 py-2 text-right font-medium">MAE</th>
              <th className="px-4 py-2 print:hidden"></th>
            </tr>
          </thead>
          <tbody>
            {completed.slice(0, 8).map((h) => {
              const isPinned = pinnedRunId === h.run_id;
              const isLatest = latestId === h.run_id;
              return (
                <tr
                  key={h.run_id}
                  className="border-b border-slate-100 last:border-0 dark:border-surface-line/50"
                >
                  <td className="px-4 py-2 font-mono text-xs text-slate-800 dark:text-stone-100">
                    #{h.run_id}
                    {isPinned && (
                      <span className="ml-2 rounded bg-brand-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-brand-800 ring-1 ring-brand-200 dark:bg-brand-500/15 dark:text-brand-300 dark:ring-brand-500/30">
                        {t('sku_detail.pin.pinned_badge')}
                      </span>
                    )}
                    {!isPinned && isLatest && (
                      <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-600 ring-1 ring-slate-200 dark:bg-surface-2 dark:text-stone-400 dark:ring-surface-line">
                        {t('sku_detail.pin.latest_badge')}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-xs text-slate-600 dark:text-stone-300">
                    {h.completed_at ? h.completed_at.slice(0, 19) : '—'}
                  </td>
                  <td className="px-4 py-2 text-xs text-slate-600 dark:text-stone-300">
                    {h.winning_exog} · {h.winning_y_variant}
                  </td>
                  <td className="px-4 py-2 text-right text-xs tabular-nums">
                    {h.winning_mae != null ? h.winning_mae.toFixed(2) : '—'}
                  </td>
                  <td className="px-4 py-2 text-right print:hidden">
                    {!isPinned && (
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => handlePin(h.run_id)}
                        disabled={setPin.isPending}
                      >
                        {t('sku_detail.pin.pin_button')}
                      </Button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardBody>
    </Card>
  );
}
