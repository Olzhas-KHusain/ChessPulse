import { useState } from 'react';

import { Dashboard } from './features/player/Dashboard';
import { SearchForm } from './features/player/SearchForm';
import { chesspulseApi, type ChesspulseApi } from './services/chesspulseApi';

export function App({ api = chesspulseApi }: { api?: ChesspulseApi }) {
  const [username, setUsername] = useState<string | null>(null);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto max-w-5xl space-y-6 px-4 py-6">
        <header className="space-y-1">
          <p className="text-xl font-bold">ChessPulse</p>
          <p className="text-sm text-slate-600">
            Rapid performance of a Chess.com player over the last 30 days. No account needed.
          </p>
        </header>
        <main className="space-y-6">
          <SearchForm onSearch={setUsername} />
          {/* key: a new search resets every section and cancels pending requests */}
          {username && <Dashboard key={username} api={api} username={username} />}
        </main>
        <footer className="text-xs text-slate-500">
          Data from the public Chess.com API. ChessPulse is not affiliated with Chess.com.
        </footer>
      </div>
    </div>
  );
}

export default App;
