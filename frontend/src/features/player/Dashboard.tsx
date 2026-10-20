import { useRef, useState, type KeyboardEvent, type ReactNode } from 'react';

import { DataStatusBanner, Section } from '../../components/StateViews';
import { useApi } from '../../hooks/useApi';
import type { ChesspulseApi } from '../../services/chesspulseApi';
import type { GroupSort } from '../../types/api';
import { GameDetailPanel } from '../games/GameDetailPanel';
import { GamesPanel } from '../games/GamesPanel';
import { OpeningsTable, OpponentsTable, SortSelect } from '../openings/GroupTables';
import { OverviewPanel } from '../overview/OverviewPanel';
import { RatingHistoryPanel } from '../rating-history/RatingHistoryPanel';

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'rating', label: 'Rating history' },
  { id: 'openings', label: 'Openings' },
  { id: 'opponents', label: 'Opponents' },
  { id: 'games', label: 'Games' },
] as const;
type TabId = (typeof TABS)[number]['id'];

export function Dashboard({ api, username }: { api: ChesspulseApi; username: string }) {
  // The overview loads (and refreshes the cache) first; the other sections are
  // requested only after it succeeds, so they reuse the same refreshed dataset.
  const overview = useApi(username, (signal) => api.overview(username, signal));

  return (
    <Section state={overview} loadingLabel={`Loading ${username}’s recent Rapid games…`}>
      {(data) => (
        <div className="space-y-4">
          <header>
            <h1 className="text-2xl font-bold">
              <a
                href={`https://www.chess.com/member/${data.username}`}
                target="_blank"
                rel="noreferrer"
                className="underline decoration-dotted"
              >
                {data.username}
              </a>
            </h1>
            <DataStatusBanner meta={data} />
          </header>
          <Tabs api={api} username={data.username} overview={<OverviewPanel overview={data} />} />
        </div>
      )}
    </Section>
  );
}

function Tabs({
  api,
  username,
  overview,
}: {
  api: ChesspulseApi;
  username: string;
  overview: ReactNode;
}) {
  const [active, setActive] = useState<TabId>('overview');
  const [openGame, setOpenGame] = useState<string | null>(null);
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const index = TABS.findIndex((t) => t.id === active);
    let next = index;
    if (event.key === 'ArrowRight') next = (index + 1) % TABS.length;
    else if (event.key === 'ArrowLeft') next = (index - 1 + TABS.length) % TABS.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = TABS.length - 1;
    else return;
    event.preventDefault();
    const tab = TABS[next];
    if (tab) {
      setActive(tab.id);
      tabRefs.current[tab.id]?.focus();
    }
  }

  return (
    <div>
      <div
        role="tablist"
        aria-label="Player statistics"
        onKeyDown={onKeyDown}
        className="flex gap-1 overflow-x-auto border-b border-slate-200"
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            ref={(el) => {
              tabRefs.current[tab.id] = el;
            }}
            type="button"
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={active === tab.id}
            aria-controls={`panel-${tab.id}`}
            tabIndex={active === tab.id ? 0 : -1}
            onClick={() => setActive(tab.id)}
            className={`whitespace-nowrap px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-indigo-600 ${
              active === tab.id ? 'border-b-2 border-indigo-700 font-semibold' : 'text-slate-600'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id={`panel-${active}`}
        aria-labelledby={`tab-${active}`}
        className="pt-4"
      >
        {active === 'overview' && overview}
        {active === 'rating' && <RatingTab api={api} username={username} />}
        {active === 'openings' && <OpeningsTab api={api} username={username} />}
        {active === 'opponents' && <OpponentsTab api={api} username={username} />}
        {active === 'games' &&
          (openGame ? (
            <GameDetailPanel
              api={api}
              username={username}
              gameId={openGame}
              onBack={() => setOpenGame(null)}
            />
          ) : (
            <GamesPanel api={api} username={username} onOpenGame={setOpenGame} />
          ))}
      </div>
    </div>
  );
}

function RatingTab({ api, username }: { api: ChesspulseApi; username: string }) {
  const state = useApi(`${username}`, (signal) => api.ratingHistory(username, signal));
  return (
    <Section state={state} loadingLabel="Loading rating history…">
      {(data) => (
        <div className="space-y-2">
          <DataStatusBanner meta={data} />
          <RatingHistoryPanel history={data} />
        </div>
      )}
    </Section>
  );
}

function OpeningsTab({ api, username }: { api: ChesspulseApi; username: string }) {
  const [sort, setSort] = useState<GroupSort>('games');
  const state = useApi(`${username}|${sort}`, (signal) => api.openings(username, sort, signal));
  return (
    <section aria-labelledby="openings-heading" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="openings-heading" className="text-lg font-semibold">
          Openings
        </h2>
        <SortSelect value={sort} onChange={setSort} />
      </div>
      <Section state={state} loadingLabel="Loading openings…">
        {(data) => (
          <>
            <DataStatusBanner meta={data} />
            <OpeningsTable data={data} />
          </>
        )}
      </Section>
    </section>
  );
}

function OpponentsTab({ api, username }: { api: ChesspulseApi; username: string }) {
  const [sort, setSort] = useState<GroupSort>('games');
  const state = useApi(`${username}|${sort}`, (signal) => api.opponents(username, sort, signal));
  return (
    <section aria-labelledby="opponents-heading" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="opponents-heading" className="text-lg font-semibold">
          Opponents
        </h2>
        <SortSelect value={sort} onChange={setSort} />
      </div>
      <Section state={state} loadingLabel="Loading opponents…">
        {(data) => (
          <>
            <DataStatusBanner meta={data} />
            <OpponentsTable data={data} />
          </>
        )}
      </Section>
    </section>
  );
}
