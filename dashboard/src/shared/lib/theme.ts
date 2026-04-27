import { create } from 'zustand';
import { persist } from 'zustand/middleware';

type Theme = 'light' | 'dark' | 'system';

interface ThemeStore {
  theme: Theme;
  setTheme: (t: Theme) => void;
}

function applyTheme(t: Theme): void {
  const root = document.documentElement;
  const isDark =
    t === 'dark' ||
    (t === 'system' &&
      window.matchMedia('(prefers-color-scheme: dark)').matches);
  root.classList.toggle('dark', isDark);
}

export const useThemeStore = create<ThemeStore>()(
  persist(
    (set) => ({
      theme: 'system',
      setTheme: (theme) => {
        applyTheme(theme);
        set({ theme });
      },
    }),
    {
      name: 'bitirme-theme-v1',
      onRehydrateStorage: () => (state) => {
        if (state) applyTheme(state.theme);
      },
    },
  ),
);

export function initTheme(): void {
  const stored = useThemeStore.getState().theme;
  applyTheme(stored);
  if (stored === 'system') {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    media.addEventListener('change', () => {
      if (useThemeStore.getState().theme === 'system') {
        applyTheme('system');
      }
    });
  }
}
