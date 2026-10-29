import { useState } from 'react';

import { BoardMotif } from './components/BoardMotif';
import { Eyebrow } from './components/ui';
import { Dashboard } from './features/player/Dashboard';
import { SearchForm } from './features/player/SearchForm';
import { chesspulseApi, type ChesspulseApi } from './services/chesspulseApi';

const FEATURES = ['Rolling 30 days', 'Rapid only', 'No account needed'];

export function App({ api = chesspulseApi }: { api?: ChesspulseApi }) {
  const [username, setUsername] = useState<string | null>(null);

  return (
    <div className="flex min-h-screen flex-col">
      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-4 sm:px-6 lg:px-8">
        <header className="flex items-center justify-between gap-4 py-5">
          <button
            type="button"
            onClick={() => setUsername(null)}
            className="group flex items-center gap-3 rounded-xl text-left"
          >
            <span
              aria-hidden="true"
              className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-mint-300 to-mint-500 font-display text-2xl leading-none text-board-950 shadow-[0_10px_30px_-8px] shadow-mint-400/70 transition group-hover:brightness-110"
            >
              ♞
            </span>
            <span className="flex flex-col">
              <span className="font-display text-lg leading-none tracking-tight text-chalk-50">
                ChessPulse
              </span>
              <span className="mt-1.5 text-[10px] uppercase leading-none tracking-[0.22em] text-chalk-500">
                Rapid analytics
              </span>
            </span>
          </button>
          <span className="hidden items-center gap-2 rounded-full border border-white/10 bg-board-900/60 px-3.5 py-1.5 text-[10px] uppercase tracking-[0.18em] text-chalk-400 sm:inline-flex">
            <span
              aria-hidden="true"
              className="h-1.5 w-1.5 rounded-full bg-mint-400 shadow-[0_0_10px] shadow-mint-400"
            />
            Rolling 30 days
          </span>
        </header>

        <main className="flex-1 pb-14">
          {username === null ? (
            <Landing onSearch={setUsername} />
          ) : (
            <div className="space-y-5">
              <div className="mx-auto max-w-2xl animate-fade sm:mx-0">
                <SearchForm initialValue={username} compact onSearch={setUsername} />
              </div>
              {/* key: a new search resets every section and cancels pending requests */}
              <Dashboard key={username} api={api} username={username} />
            </div>
          )}
        </main>

        <footer className="border-t border-white/[0.07] py-5 text-xs text-chalk-500">
          Data from the public Chess.com API. ChessPulse is not affiliated with Chess.com.
        </footer>
      </div>
    </div>
  );
}

function Landing({ onSearch }: { onSearch: (username: string) => void }) {
  return (
    <section className="grid animate-rise items-center gap-14 py-10 lg:grid-cols-[1.1fr_0.9fr] lg:gap-16 lg:py-20">
      <div>
        <Eyebrow>Chess.com · Rapid</Eyebrow>
        <h1 className="mt-4 font-display text-[2.6rem] leading-[1.03] tracking-tight text-chalk-50 sm:text-6xl">
          See the shape of your last 30 days.
        </h1>
        <p className="mt-5 max-w-xl text-base leading-relaxed text-chalk-300 sm:text-lg">
          ChessPulse turns your recent Rapid games into one clear picture: results, rating trend,
          openings and opponents. No account, no setup.
        </p>
        <div className="mt-8 max-w-xl">
          <SearchForm onSearch={onSearch} />
        </div>
        <ul className="mt-6 flex flex-wrap gap-2">
          {FEATURES.map((feature) => (
            <li
              key={feature}
              className="rounded-full border border-white/10 bg-board-900/50 px-3 py-1 text-xs text-chalk-400"
            >
              {feature}
            </li>
          ))}
        </ul>
      </div>
      <BoardMotif />
    </section>
  );
}

export default App;
