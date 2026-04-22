import { SkuTable } from '@/features/sku-list/SkuTable';
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
      <SkuTable />
    </div>
  );
}
