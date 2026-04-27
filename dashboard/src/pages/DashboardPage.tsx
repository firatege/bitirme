import { SkuTable } from '@/features/sku-list/SkuTable';
import { PortfolioSummary } from '@/features/sku-list/PortfolioSummary';
import { AbcMatrix } from '@/features/sku-list/AbcMatrix';
import { UrgencyLegend } from '@/features/sku-list/UrgencyLegend';
import { RunTrigger } from '@/features/run-control/RunTrigger';

export function DashboardPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Ana Ekran</h1>
          <p className="text-sm text-slate-500">
            Tüm SKU'lar aciliyet sırasına göre listelenir. Kırmızı satırlar
            öncelikli siparişler.
          </p>
        </div>
        <RunTrigger />
      </div>
      <PortfolioSummary />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <AbcMatrix />
        </div>
        <UrgencyLegend />
      </div>
      <SkuTable />
    </div>
  );
}
