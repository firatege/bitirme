import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQueries } from '@tanstack/react-query';
import { dataSource } from '@/shared/api/source';
import { queryKeys } from '@/shared/api/queryKeys';
import { useSkuList } from '@/shared/api/hooks';
import {
  urgencyOf,
  urgencyRank,
  type UrgencyLevel,
} from '@/entities/sku/selectors';
import { fmtDec, fmtInt, fmtPct } from '@/shared/lib/format';
import { UrgencyBadge } from './UrgencyBadge';
import { Card } from '@/shared/ui/Card';
import { Skeleton } from '@/shared/ui/Skeleton';
import { EmptyState } from '@/shared/ui/EmptyState';

const LEVELS: UrgencyLevel[] = [
  'CRITICAL',
  'HIGH',
  'MEDIUM',
  'LOW',
  'UNKNOWN',
];

export function SkuTable() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [filter, setFilter] = useState<UrgencyLevel | 'ALL'>('ALL');
  const [search, setSearch] = useState('');

  const { data: skus = [], isLoading: skusLoading } = useSkuList();

  const queries = useQueries({
    queries: skus.map((sku) => ({
      queryKey: queryKeys.skuLatest(sku),
      queryFn: () => dataSource.getSkuLatest(sku),
      staleTime: 30_000,
      retry: 0,
    })),
  });

  const rows = useMemo(() => {
    return skus
      .map((sku, idx) => {
        const q = queries[idx];
        const detail = q?.data;
        const level = urgencyOf(detail?.winning);
        return {
          sku,
          detail,
          level,
          isLoading: q?.isLoading ?? false,
          isError: q?.isError ?? false,
        };
      })
      .filter((r) => filter === 'ALL' || r.level === filter)
      .filter((r) =>
        search ? r.sku.toLowerCase().includes(search.toLowerCase()) : true,
      )
      .sort((a, b) => urgencyRank[a.level] - urgencyRank[b.level]);
  }, [skus, queries, filter, search]);

  if (skusLoading) {
    return (
      <div className="space-y-2">
        {[...Array(4)].map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (skus.length === 0) {
    return (
      <EmptyState
        title={t('empty.no_skus')}
        description="public/sku_list.json dosyasını oluşturun veya bir run tetikleyin."
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="SKU ara…"
          className="h-9 w-64 rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-slate-400"
        />
        <div className="flex gap-1">
          {(['ALL', ...LEVELS] as const).map((lvl) => (
            <button
              key={lvl}
              onClick={() => setFilter(lvl)}
              className={`h-9 rounded-lg px-3 text-xs font-medium transition-colors ${
                filter === lvl
                  ? 'bg-slate-900 text-white'
                  : 'bg-white text-slate-700 ring-1 ring-inset ring-slate-200 hover:bg-slate-50'
              }`}
            >
              {lvl === 'ALL' ? 'Tümü' : t(`urgency.${lvl}` as const)}
            </button>
          ))}
        </div>
        <span className="ml-auto text-xs text-slate-500">
          {rows.length} / {skus.length} SKU
        </span>
      </div>

      <Card>
        <table className="w-full text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Aciliyet</th>
              <th className="px-4 py-3">{t('labels.sku')}</th>
              <th className="px-4 py-3 text-right">Stok</th>
              <th className="px-4 py-3 text-right">Önerilen Sipariş</th>
              <th className="px-4 py-3 text-right">{t('labels.stockout_p3m')}</th>
              <th className="px-4 py-3 text-right">{t('labels.stockout_p6m')}</th>
              <th className="px-4 py-3 text-right">{t('labels.mae')}</th>
              <th className="px-4 py-3">{t('labels.model')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.sku}
                className="cursor-pointer border-b border-slate-100 transition-colors last:border-0 hover:bg-slate-50"
                onClick={() => navigate(`/skus/${encodeURIComponent(r.sku)}`)}
              >
                <td className="px-4 py-3">
                  <UrgencyBadge level={r.level} />
                </td>
                <td className="px-4 py-3 font-mono text-xs">{r.sku}</td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {fmtInt(r.detail?.recommendation?.starting_stock)}
                </td>
                <td className="px-4 py-3 text-right font-semibold tabular-nums">
                  {fmtInt(r.detail?.recommendation?.order_qty_rounded)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {fmtPct(r.detail?.winning?.p_stockout_3m)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {fmtPct(r.detail?.winning?.p_stockout_6m)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {fmtDec(r.detail?.winning?.mae)}
                </td>
                <td className="px-4 py-3 text-xs text-slate-600">
                  {r.detail?.winning
                    ? `${r.detail.winning.exog} · ${r.detail.winning.y_variant}`
                    : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
