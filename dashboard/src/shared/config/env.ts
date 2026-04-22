import { z } from 'zod';

const EnvSchema = z.object({
  VITE_API_BASE_URL: z.string().url().default('http://localhost:9000'),
  VITE_GRAFANA_URL: z.string().url().default('http://localhost:3000'),
  VITE_USE_STATIC_SOURCE: z
    .enum(['true', 'false'])
    .default('false')
    .transform((v) => v === 'true'),
  VITE_USE_MSW: z
    .enum(['true', 'false'])
    .default('false')
    .transform((v) => v === 'true'),
});

const parsed = EnvSchema.safeParse({
  VITE_API_BASE_URL: import.meta.env.VITE_API_BASE_URL,
  VITE_GRAFANA_URL: import.meta.env.VITE_GRAFANA_URL,
  VITE_USE_STATIC_SOURCE: import.meta.env.VITE_USE_STATIC_SOURCE ?? 'false',
  VITE_USE_MSW: import.meta.env.VITE_USE_MSW ?? 'false',
});

if (!parsed.success) {
  console.error('[env] Invalid environment variables', parsed.error.format());
  throw new Error('Invalid environment variables');
}

export const env = {
  apiBaseUrl: parsed.data.VITE_API_BASE_URL,
  grafanaUrl: parsed.data.VITE_GRAFANA_URL,
  useStaticSource: parsed.data.VITE_USE_STATIC_SOURCE,
  useMsw: parsed.data.VITE_USE_MSW,
} as const;
