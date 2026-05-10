import { useState } from 'react';
import { NavLink, Outlet, ScrollRestoration } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { cn } from '@/shared/lib/cn';
import { useCartStore, cartCount } from '@/features/order-cart/cartStore';
import { ToastViewport } from '@/shared/ui/Toast';
import { useGlobalShortcuts } from '@/features/keyboard/useGlobalShortcuts';
import { useThemeStore } from '@/shared/lib/theme';

const navItemClass = ({ isActive }: { isActive: boolean }): string =>
  cn(
    'flex items-center gap-2.5 rounded-md px-3 py-1.5 text-sm transition-colors',
    isActive
      ? 'bg-slate-100 text-slate-900 dark:bg-surface-2 dark:text-stone-50'
      : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-stone-300 dark:hover:bg-surface-2/60 dark:hover:text-stone-50',
  );

function ThemeToggle() {
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);
  const isDark =
    theme === 'dark' ||
    (theme === 'system' &&
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-color-scheme: dark)').matches);
  return (
    <button
      type="button"
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
      title={isDark ? 'Açık tema' : 'Koyu tema'}
      className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-stone-400 dark:hover:bg-surface-2 dark:hover:text-stone-100"
    >
      {isDark ? (
        <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 3v2m0 14v2M5.6 5.6l1.4 1.4m10 10l1.4 1.4M3 12h2m14 0h2M5.6 18.4l1.4-1.4m10-10l1.4-1.4" strokeLinecap="round" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="currentColor">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      )}
    </button>
  );
}

export function AppShell() {
  const { t } = useTranslation();
  const items = useCartStore((s) => s.items);
  const cartN = cartCount(items);
  const [mobileOpen, setMobileOpen] = useState(false);

  useGlobalShortcuts();

  const close = (): void => setMobileOpen(false);

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      {/* Mobile header */}
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 md:hidden dark:border-surface-line dark:bg-surface-1">
        <button
          type="button"
          aria-label="Menüyü aç"
          onClick={() => setMobileOpen((v) => !v)}
          className="rounded-md p-2 hover:bg-slate-100 dark:hover:bg-surface-2"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M3 5h14a1 1 0 010 2H3a1 1 0 010-2zm0 4h14a1 1 0 010 2H3a1 1 0 010-2zm0 4h14a1 1 0 010 2H3a1 1 0 010-2z" clipRule="evenodd" />
          </svg>
        </button>
        <span className="text-sm font-medium">{t('app_title')}</span>
        <span className="w-8" />
      </header>

      <aside
        className={cn(
          'flex w-full flex-col border-r bg-white px-3 py-4 md:w-56',
          'border-slate-200 dark:border-surface-line dark:bg-surface-1',
          mobileOpen ? 'block' : 'hidden md:flex',
        )}
      >
        {/* Brand */}
        <div className="hidden md:block px-3 pb-4">
          <div className="text-sm font-medium text-slate-900 dark:text-stone-50">
            {t('app_title')}
          </div>
          <div className="mt-0.5 text-[11px] text-slate-500 dark:text-stone-400">
            Bitirme · Dashboard
          </div>
        </div>

        {/* Nav */}
        <nav className="flex flex-col gap-0.5">
          <NavLink to="/" end className={navItemClass} onClick={close}>
            {t('nav.dashboard')}
          </NavLink>
          <NavLink to="/runs" className={navItemClass} onClick={close}>
            {t('nav.runs')}
          </NavLink>
          <NavLink to="/cart" className={navItemClass} onClick={close}>
            <span className="flex-1">{t('nav.cart')}</span>
            {cartN > 0 && (
              <span className="rounded bg-brand-600 px-1.5 py-0.5 text-[10px] font-medium text-white dark:bg-brand-500 dark:text-surface-0">
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

        <div className="mt-auto hidden md:block">
          <div className="flex items-center justify-between border-t border-slate-200 px-3 pt-3 dark:border-surface-line">
            <span className="text-[11px] text-slate-400 dark:text-stone-200/35">
              v0.1
            </span>
            <ThemeToggle />
          </div>
        </div>
      </aside>

      <main className="flex-1 bg-slate-50 p-4 sm:p-6 lg:p-8 dark:bg-surface-0">
        <div className="mx-auto max-w-7xl">
          <Outlet />
        </div>
      </main>
      <ToastViewport />
      <ScrollRestoration />
    </div>
  );
}
