import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQueries } from '@tanstack/react-query';
import { useVirtualizer } from '@tanstack/react-virtual';
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
import { cn } from '@/shared/lib/cn';

const LEVELS: UrgencyLevel[] = [
  'CRITICAL',
  'HIGH',
  'MEDIUM',
  'LOW',
  'UNKNOWN',
];

const ROW_HEIGHT = 44;

export function SkuTable() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [filter, setFilter] = useState<UrgencyLevel | 'ALL'>('ALL');
  const [search, setSearch] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

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

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 8,
  });

  // Filtre/arama değişince tablo en üstten başlasın — kullanıcı önceki scroll
  // konumunda boş alan görmesin.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 0 });
  }, [filter, search]);

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

  const tableHeight = Math.min(rows.length * ROW_HEIGHT + 4, 560);

  return (
    <div className="space-y-3">
      {/* Filtre çubuğu */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="SKU ara…"
          className="h-9 w-64 rounded-md border border-slate-200 bg-white px-3 text-sm outline-none focus:border-brand-500 dark:border-surface-line dark:bg-surface-1"
          data-search-input
        />
        <div className="flex flex-wrap gap-1">
          {(['ALL', ...LEVELS] as const).map((lvl) => {
            const active = filter === lvl;
            return (
              <button
                key={lvl}
                type="button"
                onClick={() => setFilter(lvl)}
                className={cn(
                  'inline-flex h-9 items-center rounded-md px-3 text-xs transition-colors',
                  active
                    ? 'bg-brand-700 text-white dark:bg-brand-600'
                    : 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 dark:border-surface-line dark:bg-surface-1 dark:text-stone-300 dark:hover:bg-surface-2',
                )}
              >
                {lvl === 'ALL' ? 'Tümü' : t(`urgency.${lvl}` as const)}
              </button>
            );
          })}
        </div>
        <span className="ml-auto text-xs text-slate-500 dark:text-stone-400">
          {rows.length} / {skus.length} SKU
        </span>
      </div>

      <Card>
        {/* Header */}
        <div
          className="grid items-center gap-x-4 border-b border-slate-200 bg-slate-50 px-4 py-2 text-xs text-slate-500 dark:border-surface-line dark:bg-surface-2/30 dark:text-stone-200/50"
          style={{ gridTemplateColumns: GRID_COLS }}
        >
          <span>Aciliyet</span>
          <span>{t('labels.sku')}</span>
          <span className="text-right">Stok</span>
          <span className="text-right">Önerilen</span>
          <span className="text-right">{t('labels.stockout_p3m')}</span>
          <span className="text-right">{t('labels.stockout_p6m')}</span>
          <span className="text-right">{t('labels.mae')}</span>
          <span>{t('labels.model')}</span>
        </div>

        {/* Body */}
        <div
          ref={scrollRef}
          style={{ height: tableHeight }}
          className="overflow-auto"
        >
          <div
            style={{
              height: virtualizer.getTotalSize(),
              position: 'relative',
            }}
          >
            {virtualizer.getVirtualItems().map((vRow) => {
              const r = rows[vRow.index];
              if (!r) return null;
              return (
                <div
                  key={r.sku}
                  onClick={() =>
                    navigate(`/skus/${encodeURIComponent(r.sku)}`)
                  }
                  className="absolute inset-x-0 grid cursor-pointer items-center gap-x-4 border-b border-slate-100 px-4 text-sm transition-colors hover:bg-slate-50 dark:border-surface-line/50 dark:hover:bg-surface-2/40"
                  style={{
                    gridTemplateColumns: GRID_COLS,
                    height: ROW_HEIGHT,
                    transform: `translateY(${vRow.start}px)`,
                  }}
                >
                  <span className="min-w-0">
                    <UrgencyBadge level={r.level} />
                  </span>
                  <span className="truncate font-mono text-xs text-slate-800 dark:text-stone-100">
                    {r.sku}
                  </span>
                  <span className="text-right tabular-nums text-slate-700 dark:text-stone-200">
                    {fmtInt(r.detail?.recommendation?.starting_stock)}
                  </span>
                  <span className="text-right font-medium tabular-nums text-slate-900 dark:text-stone-50">
                    {fmtInt(r.detail?.recommendation?.order_qty_rounded)}
                  </span>
                  <span className="text-right tabular-nums text-slate-700 dark:text-stone-200">
                    {fmtPct(r.detail?.winning?.p_stockout_3m)}
                  </span>
                  <span className="text-right tabular-nums text-slate-700 dark:text-stone-200">
                    {fmtPct(r.detail?.winning?.p_stockout_6m)}
                  </span>
                  <span className="text-right tabular-nums text-slate-700 dark:text-stone-200">
                    {fmtDec(r.detail?.winning?.mae)}
                  </span>
                  <span
                    title={
                      r.detail?.winning
                        ? `${r.detail.winning.exog} · ${r.detail.winning.y_variant}`
                        : ''
                    }
                    className="min-w-0 truncate text-xs text-slate-500 dark:text-stone-400"
                  >
                    {r.detail?.winning
                      ? `${r.detail.winning.exog} · ${r.detail.winning.y_variant}`
                      : '—'}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </Card>
    </div>
  );
}

// Aciliyet · SKU · Stok · Önerilen · 3ay · 6ay · MAE · Model
// Sayısal kolonlar 4-5 haneli + binlik ayraç sığdırır (örn. 127.600, 9.496,28).
// Model kolonu uzun string'lerde minmax(180, 1fr) ile esnek genişler.
const GRID_COLS =
  '100px 140px 80px 100px 80px 80px 90px minmax(180px, 1fr)';
