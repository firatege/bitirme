import { create } from 'zustand';
import { persist } from 'zustand/middleware';

type Theme = 'light' | 'dark' | 'system';

interface ThemeState {
  theme: Theme;
  setTheme: (t: Theme) => void;
}

/**
 * Apply the resolved theme (light | dark) to the <html> element.
 * Both `.dark` and `.light` classes are toggled so CSS can target either.
 */
function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  let isDark: boolean;
  if (theme === 'system') {
    isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  } else {
    isDark = theme === 'dark';
  }
  root.classList.toggle('dark', isDark);
  root.classList.toggle('light', !isDark);
}

/**
 * Zustand store persisted to localStorage under the key `theme`.
 * Varsayılan: dark — operasyonel kontrol paneli için.
 */
export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      theme: 'dark',
      setTheme: (t: Theme) => {
        applyTheme(t);
        set({ theme: t });
      },
    }),
    { name: 'theme' },
  ),
);

/**
 * Call once at application startup (before React renders) to apply the
 * persisted theme immediately and listen for OS-level preference changes.
 */
export function initTheme(): void {
  const { theme } = useThemeStore.getState();
  applyTheme(theme);

  // Re-apply when the user changes their OS colour-scheme preference.
  window
    .matchMedia('(prefers-color-scheme: dark)')
    .addEventListener('change', () => {
      const current = useThemeStore.getState().theme;
      if (current === 'system') {
        applyTheme('system');
      }
    });
}
