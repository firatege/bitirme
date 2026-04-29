import { create } from 'zustand';
import { persist } from 'zustand/middleware';

type Theme = 'light' | 'dark' | 'system';

interface ThemeState {
  theme: Theme;
  setTheme: (t: Theme) => void;
}

/**
 * Apply the resolved theme (light | dark) to the <html> element so that
 * Tailwind's `dark:` variant and the CSS `.dark` selectors work correctly.
 */
function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === 'system') {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    root.classList.toggle('dark', prefersDark);
  } else {
    root.classList.toggle('dark', theme === 'dark');
  }
}

/**
 * Zustand store persisted to localStorage under the key `theme`.
 */
export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      theme: 'system',
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
