import { CartView } from '@/features/order-cart/CartView';

export function CartPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Sipariş Sepeti</h1>
        <p className="text-sm text-slate-500">
          Onay bekleyen sipariş önerileri. Miktarları düzenleyin, not ekleyin,
          tedarikçiye CSV olarak aktarın.
        </p>
      </div>
      <CartView />
    </div>
  );
}
