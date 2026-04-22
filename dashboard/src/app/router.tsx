import { createBrowserRouter } from 'react-router-dom';
import { AppShell } from './layouts/AppShell';
import { DashboardPage } from '@/pages/DashboardPage';
import { SkuDetailPage } from '@/pages/SkuDetailPage';
import { CartPage } from '@/pages/CartPage';
import { AnalyticsPage } from '@/pages/AnalyticsPage';
import { SettingsPage } from '@/pages/SettingsPage';

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { path: '/', element: <DashboardPage /> },
      { path: '/skus/:sku', element: <SkuDetailPage /> },
      { path: '/cart', element: <CartPage /> },
      { path: '/analytics', element: <AnalyticsPage /> },
      { path: '/settings', element: <SettingsPage /> },
    ],
  },
]);
