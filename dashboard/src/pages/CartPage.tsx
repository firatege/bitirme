import { CartView } from '@/features/order-cart/CartView';

export function CartPage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-medium text-slate-900 dark:text-stone-50">
          Sipariş Sepeti
        </h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-stone-400">
          Onay bekleyen sipariş önerileri. Miktarları düzenleyin, not ekleyin,
          tedarikçiye CSV olarak aktarın.
        </p>
      </header>
      <CartView />
    </div>
  );
}
