import { lazy, Suspense, type ReactNode } from 'react';
import { createBrowserRouter } from 'react-router-dom';
import { AppShell } from './layouts/AppShell';
import { Skeleton } from '@/shared/ui/Skeleton';

const DashboardPage = lazy(() =>
  import('@/pages/DashboardPage').then((m) => ({ default: m.DashboardPage })),
);
const SkuDetailPage = lazy(() =>
  import('@/pages/SkuDetailPage').then((m) => ({ default: m.SkuDetailPage })),
);
const CartPage = lazy(() =>
  import('@/pages/CartPage').then((m) => ({ default: m.CartPage })),
);
const AnalyticsPage = lazy(() =>
  import('@/pages/AnalyticsPage').then((m) => ({ default: m.AnalyticsPage })),
);
const SettingsPage = lazy(() =>
  import('@/pages/SettingsPage').then((m) => ({ default: m.SettingsPage })),
);
const RunsPage = lazy(() =>
  import('@/pages/RunsPage').then((m) => ({ default: m.RunsPage })),
);
const RunDetailPage = lazy(() =>
  import('@/pages/RunDetailPage').then((m) => ({ default: m.RunDetailPage })),
);

function withSuspense(node: ReactNode): ReactNode {
  return (
    <Suspense
      fallback={
        <div className="space-y-3">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-32 w-full" />
        </div>
      }
    >
      {node}
    </Suspense>
  );
}

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { path: '/', element: withSuspense(<DashboardPage />) },
      { path: '/skus/:sku', element: withSuspense(<SkuDetailPage />) },
      { path: '/runs', element: withSuspense(<RunsPage />) },
      { path: '/runs/:runId', element: withSuspense(<RunDetailPage />) },
      { path: '/cart', element: withSuspense(<CartPage />) },
      { path: '/analytics', element: withSuspense(<AnalyticsPage />) },
      { path: '/settings', element: withSuspense(<SettingsPage />) },
    ],
  },
]);
