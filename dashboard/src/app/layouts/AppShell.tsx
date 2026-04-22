import { NavLink, Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { cn } from '@/shared/lib/cn';
import { useCartStore, cartCount } from '@/features/order-cart/cartStore';

const navItemClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
    isActive
      ? 'bg-slate-900 text-white'
      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
  );

export function AppShell() {
  const { t } = useTranslation();
  const items = useCartStore((s) => s.items);
  const cartN = cartCount(items);

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 flex-col border-r border-slate-200 bg-white px-4 py-5">
        <div className="mb-6 px-3">
          <div className="text-sm font-semibold text-slate-900">
            {t('app_title')}
          </div>
          <div className="text-xs text-slate-500">Bitirme · Dashboard</div>
        </div>
        <nav className="flex flex-col gap-1">
          <NavLink to="/" end className={navItemClass}>
            {t('nav.dashboard')}
          </NavLink>
          <NavLink to="/cart" className={navItemClass}>
            {t('nav.cart')}
            {cartN > 0 && (
              <span className="ml-auto rounded-full bg-slate-900 px-2 py-0.5 text-xs font-semibold text-white">
                {cartN}
              </span>
            )}
          </NavLink>
          <NavLink to="/analytics" className={navItemClass}>
            {t('nav.analytics')}
          </NavLink>
          <NavLink to="/settings" className={navItemClass}>
            {t('nav.settings')}
          </NavLink>
        </nav>
        <div className="mt-auto px-3 text-xs text-slate-400">
          v0.1 · depo yönetimi
        </div>
      </aside>
      <main className="flex-1 bg-slate-50 p-8">
        <div className="mx-auto max-w-7xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
