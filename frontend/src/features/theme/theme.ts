/**
 * Theme persistence and application.
 *
 * The inline boot script in `index.html` sets `data-theme` before first paint;
 * this module is the single place that changes it afterwards.
 */

export type Theme = 'dark' | 'light';

export const THEME_STORAGE_KEY = 'chesspulse-theme';

const THEME_COLORS: Record<Theme, string> = {
  dark: '#05080c',
  light: '#f7f4ec',
};

export function readTheme(): Theme {
  if (typeof document === 'undefined') return 'dark';
  return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta !== null) meta.setAttribute('content', THEME_COLORS[theme]);
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Private mode or blocked storage: the theme still applies for this visit.
  }
}
