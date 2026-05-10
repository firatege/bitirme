import { SkuTable } from '@/features/sku-list/SkuTable';
import { PortfolioSummary } from '@/features/sku-list/PortfolioSummary';
import { AbcMatrix } from '@/features/sku-list/AbcMatrix';
import { UrgencyLegend } from '@/features/sku-list/UrgencyLegend';
import { RunTrigger } from '@/features/run-control/RunTrigger';

export function DashboardPage() {
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-medium text-slate-900 dark:text-stone-50">
            Ana Ekran
          </h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-stone-400">
            Tüm SKU&apos;lar aciliyet sırasına göre listelenir. Kırmızı satırlar
            öncelikli sipariş gerektirir.
          </p>
        </div>
        <RunTrigger />
      </header>

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
