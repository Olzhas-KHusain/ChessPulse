import { useState } from 'react';

import { applyTheme, readTheme, type Theme } from './theme';

/**
 * One-button theme switch. The icon shows the theme you will get, not the one
 * you are in, which keeps the label and action aligned.
 */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(readTheme);
  const next: Theme = theme === 'dark' ? 'light' : 'dark';

  function toggle() {
    applyTheme(next);
    setTheme(next);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`Switch to ${next} theme`}
      aria-pressed={theme === 'light'}
      title={`Switch to ${next} theme`}
      className="inline-flex h-9 items-center gap-2 rounded-full border border-white/10 bg-board-900/60 px-3 text-xs font-medium text-chalk-300 transition hover:border-mint-400/40 hover:text-chalk-50"
    >
      <span aria-hidden="true" className="text-sm leading-none">
        {next === 'light' ? '☀' : '☾'}
      </span>
      <span className="hidden sm:inline">{next === 'light' ? 'Light' : 'Dark'}</span>
    </button>
  );
}
