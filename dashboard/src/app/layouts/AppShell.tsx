import { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { cn } from '@/shared/lib/cn';
import { useCartStore, cartCount } from '@/features/order-cart/cartStore';
import { ToastViewport } from '@/shared/ui/Toast';
import { useGlobalShortcuts } from '@/features/keyboard/useGlobalShortcuts';

const navItemClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
    isActive
      ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100',
  );

export function AppShell() {
  const { t } = useTranslation();
  const items = useCartStore((s) => s.items);
  const cartN = cartCount(items);
  const [mobileOpen, setMobileOpen] = useState(false);

  useGlobalShortcuts();

  const close = () => setMobileOpen(false);

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 md:hidden dark:border-slate-800 dark:bg-slate-900">
        <button
          aria-label="Menüyü aç"
          onClick={() => setMobileOpen((v) => !v)}
          className="rounded-md p-2 hover:bg-slate-100 dark:hover:bg-slate-800"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-5 w-5"
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path
              fillRule="evenodd"
              d="M3 5h14a1 1 0 010 2H3a1 1 0 010-2zm0 4h14a1 1 0 010 2H3a1 1 0 010-2zm0 4h14a1 1 0 010 2H3a1 1 0 010-2z"
              clipRule="evenodd"
            />
          </svg>
        </button>
        <span className="text-sm font-semibold">{t('app_title')}</span>
        <span className="w-8" />
      </header>

      <aside
        className={cn(
          'flex w-full flex-col border-r border-slate-200 bg-white px-4 py-5 transition-all md:w-60 dark:border-slate-800 dark:bg-slate-900',
          mobileOpen ? 'block' : 'hidden md:flex',
        )}
      >
        <div className="mb-6 hidden px-3 md:block">
          <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            {t('app_title')}
          </div>
          <div className="text-xs text-slate-500 dark:text-slate-400">
            Bitirme · Dashboard
          </div>
        </div>
        <nav className="flex flex-col gap-1">
          <NavLink to="/" end className={navItemClass} onClick={close}>
            {t('nav.dashboard')}
          </NavLink>
          <NavLink to="/runs" className={navItemClass} onClick={close}>
            {t('nav.runs')}
          </NavLink>
          <NavLink to="/cart" className={navItemClass} onClick={close}>
            {t('nav.cart')}
            {cartN > 0 && (
              <span className="ml-auto rounded-full bg-slate-900 px-2 py-0.5 text-xs font-semibold text-white dark:bg-slate-100 dark:text-slate-900">
                {cartN}
              </span>
            )}
          </NavLink>
          <NavLink to="/analytics" className={navItemClass} onClick={close}>
            {t('nav.analytics')}
          </NavLink>
          <NavLink to="/settings" className={navItemClass} onClick={close}>
            {t('nav.settings')}
          </NavLink>
        </nav>
        <div className="mt-auto hidden px-3 text-xs text-slate-400 md:block dark:text-slate-600">
          v0.1 · depo yönetimi
        </div>
      </aside>

      <main className="flex-1 bg-slate-50 p-4 sm:p-6 lg:p-8 dark:bg-slate-950">
        <div className="mx-auto max-w-7xl">
          <Outlet />
        </div>
      </main>
      <ToastViewport />
    </div>
  );
}
