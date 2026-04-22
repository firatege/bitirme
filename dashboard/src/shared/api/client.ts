import axios, { AxiosError } from 'axios';
import { env } from '@/shared/config/env';

export const apiClient = axios.create({
  baseURL: env.apiBaseUrl,
  timeout: 60_000,
  headers: { 'Content-Type': 'application/json' },
});

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly url: string,
    message: string,
    public readonly data?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

apiClient.interceptors.response.use(
  (res) => res,
  (error: AxiosError) => {
    const status = error.response?.status ?? 0;
    const url = `${error.config?.baseURL ?? ''}${error.config?.url ?? ''}`;
    const msg = error.message || 'Network error';
    return Promise.reject(new ApiError(status, url, msg, error.response?.data));
  },
);
