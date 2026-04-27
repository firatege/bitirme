import React from 'react';
import ReactDOM from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import { AppProviders } from './providers';
import { router } from './router';
import { env } from '@/shared/config/env';
import { initTheme } from '@/shared/lib/theme';
import '@/styles/globals.css';

initTheme();

async function bootstrapMocks(): Promise<void> {
  if (!env.useMsw) return;
  const { worker } = await import('@/test/msw/browser');
  await worker.start({ onUnhandledRequest: 'bypass' });
  console.info('[msw] mock service worker started');
}

void bootstrapMocks().then(() => {
  const root = document.getElementById('root');
  if (!root) throw new Error('Root element #root not found');
  ReactDOM.createRoot(root).render(
    <React.StrictMode>
      <AppProviders>
        <RouterProvider router={router} />
      </AppProviders>
    </React.StrictMode>,
  );
});
