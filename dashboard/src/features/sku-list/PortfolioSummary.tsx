import { useMemo } from 'react';
import { useQueries } from '@tanstack/react-query';
import { dataSource } from '@/shared/api/source';
import { queryKeys } from '@/shared/api/queryKeys';
import { useSkuList } from '@/shared/api/hooks';
import { Stat } from '@/shared/ui/Stat';
import { fmtDec, fmtInt } from '@/shared/lib/format';
import { urgencyOf } from '@/entities/sku/selectors';

export function PortfolioSummary() {
  const { data: skus = [] } = useSkuList();
  const queries = useQueries({
    queries: skus.map((sku) => ({
      queryKey: queryKeys.skuLatest(sku),
      queryFn: () => dataSource.getSkuLatest(sku),
      staleTime: 30_000,
      retry: 0,
    })),
  });

  const stats = useMemo(() => {
    let critical = 0;
    let needsReorder = 0;
    let totalOrderQty = 0;
    let maeSum = 0;
    let maeCount = 0;
    for (const q of queries) {
      const d = q.data;
      if (!d) continue;
      if (urgencyOf(d.winning) === 'CRITICAL') critical++;
      const rec = d.recommendation;
      if (rec && rec.order_qty_rounded > 0) {
        needsReorder++;
        totalOrderQty += rec.order_qty_rounded;
      }
      const mae = d.winning?.mae;
      if (typeof mae === 'number') {
        maeSum += mae;
        maeCount++;
      }
    }
    return {
      critical,
      needsReorder,
      totalOrderQty,
      avgMae: maeCount > 0 ? maeSum / maeCount : null,
    };
  }, [queries]);

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Stat
        label="Kritik SKU"
        value={fmtInt(stats.critical)}
        tone={stats.critical > 0 ? 'critical' : 'success'}
      />
      <Stat
        label="Sipariş Bekleyen"
        value={fmtInt(stats.needsReorder)}
        tone={stats.needsReorder > 0 ? 'warning' : 'default'}
      />
      <Stat
        label="Toplam Sipariş"
        value={fmtInt(stats.totalOrderQty)}
        hint="adet · MOQ yuvarlanmış"
      />
      <Stat
        label="Ortalama MAE"
        value={stats.avgMae !== null ? fmtDec(stats.avgMae) : '—'}
        hint="model doğruluğu"
      />
    </div>
  );
}
