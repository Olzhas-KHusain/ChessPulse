import { useId, useState, type FormEvent } from 'react';

import { validateUsername } from '../../utils/format';

export function SearchForm({
  initialValue = '',
  compact = false,
  onSearch,
}: {
  initialValue?: string;
  compact?: boolean;
  onSearch: (username: string) => void;
}) {
  const [value, setValue] = useState(initialValue);
  const [error, setError] = useState<string | null>(null);
  const inputId = useId();
  const errorId = useId();

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = validateUsername(value);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setError(null);
    onSearch(result.value);
  }

  return (
    <form onSubmit={submit} noValidate className="w-full">
      <label
        htmlFor={inputId}
        className={
          compact
            ? 'sr-only'
            : 'block text-[11px] font-medium uppercase tracking-[0.16em] text-chalk-400'
        }
      >
        Chess.com username
      </label>
      <div
        className={`flex items-stretch gap-2 rounded-2xl border bg-board-900/80 p-1.5 shadow-lift backdrop-blur-sm transition focus-within:ring-4 focus-within:ring-mint-400/10 ${
          error
            ? 'border-coral-400/60 focus-within:border-coral-400/80'
            : 'border-white/10 focus-within:border-mint-400/60'
        } ${compact ? '' : 'mt-2'}`}
      >
        <span
          aria-hidden="true"
          className="grid w-10 shrink-0 place-items-center font-display text-xl text-chalk-500"
        >
          ♟
        </span>
        <input
          id={inputId}
          name="username"
          type="text"
          autoComplete="off"
          spellCheck={false}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          aria-invalid={error !== null}
          aria-describedby={error ? errorId : undefined}
          placeholder="e.g. hikaru"
          className="min-w-0 flex-1 bg-transparent py-2.5 text-base text-chalk-50 placeholder:text-chalk-500 focus-visible:outline-none"
        />
        <button
          type="submit"
          className="shrink-0 rounded-xl bg-mint-400 px-4 py-2 text-sm font-semibold text-board-950 transition hover:bg-mint-300 sm:px-5"
        >
          Analyze
          <span aria-hidden="true" className="ml-1.5">
            →
          </span>
        </button>
      </div>
      {error && (
        <p id={errorId} role="alert" className="mt-2 text-sm text-coral-300">
          {error}
        </p>
      )}
    </form>
  );
}
