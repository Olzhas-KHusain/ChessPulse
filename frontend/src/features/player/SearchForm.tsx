import { useId, useState, type FormEvent } from 'react';

import { validateUsername } from '../../utils/format';

export function SearchForm({
  initialValue = '',
  onSearch,
}: {
  initialValue?: string;
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
    <form
      onSubmit={submit}
      noValidate
      className="flex w-full flex-col gap-2 sm:flex-row sm:items-start"
    >
      <div className="flex-1">
        <label htmlFor={inputId} className="block text-sm font-medium text-slate-700">
          Chess.com username
        </label>
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
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-600"
          placeholder="e.g. hikaru"
        />
        {error && (
          <p id={errorId} role="alert" className="mt-1 text-sm text-red-700">
            {error}
          </p>
        )}
      </div>
      <button
        type="submit"
        className="rounded-md bg-indigo-700 px-4 py-2 font-medium text-white hover:bg-indigo-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-600 focus-visible:ring-offset-2 sm:mt-6"
      >
        Analyze
      </button>
    </form>
  );
}
