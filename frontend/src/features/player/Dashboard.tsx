import { useRef, useState, type KeyboardEvent, type ReactNode } from 'react';

import { DataStatusBanner, Section } from '../../components/StateViews';
import { Eyebrow, Panel } from '../../components/ui';
import { useApi } from '../../hooks/useApi';
import type { ChesspulseApi } from '../../services/chesspulseApi';
import type { GroupSort, Overview } from '../../types/api';
import { formatDate, formatNumber } from '../../utils/format';
import { GamesPanel } from '../games/GamesPanel';
import { FormPanel } from '../form/FormPanel';
import { OpeningsTable, OpponentsTable, SortSelect } from '../openings/GroupTables';
import { OverviewPanel } from '../overview/OverviewPanel';
import { RatingHistoryPanel } from '../rating-history/RatingHistoryPanel';

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'form', label: 'Form report' },
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
        <div className="animate-rise space-y-5">
          <PlayerHeader data={data} />
          <Tabs api={api} username={data.username} overview={<OverviewPanel overview={data} />} />
        </div>
      )}
    </Section>
  );
}

function PlayerHeader({ data }: { data: Overview }) {
  const initials = data.username.slice(0, 2).toUpperCase();
  return (
    <Panel className="overflow-hidden">
      <div className="flex flex-col gap-6 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div className="flex min-w-0 items-center gap-4">
          <span
            aria-hidden="true"
            className="grid h-14 w-14 shrink-0 place-items-center rounded-2xl border border-white/10 bg-gradient-to-br from-board-700 to-board-850 font-display text-xl uppercase text-mint-300"
          >
            {initials}
          </span>
          <div className="min-w-0">
            <Eyebrow>Chess.com · Rapid</Eyebrow>
            <h1 className="mt-1.5 truncate font-display text-3xl leading-none tracking-tight text-chalk-50">
              <a
                href={`https://www.chess.com/member/${data.username}`}
                target="_blank"
                rel="noreferrer"
                className="transition hover:text-mint-300"
              >
                {data.username}
              </a>
            </h1>
            <p className="mt-2 text-sm text-chalk-400">
              {formatDate(data.period.start)} – {formatDate(data.period.end)} · rolling 30 days
            </p>
          </div>
        </div>
        <div className="flex shrink-0 gap-8 border-t border-white/[0.06] pt-4 sm:gap-10 sm:border-0 sm:pt-0">
          <div>
            <p className="text-[10px] uppercase tracking-[0.18em] text-chalk-500">Rating</p>
            <p className="mt-1 font-display text-3xl leading-none tabular-nums text-chalk-50">
              {formatNumber(data.current_rating)}
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.18em] text-chalk-500">Games</p>
            <p className="mt-1 font-display text-3xl leading-none tabular-nums text-chalk-50">
              {formatNumber(data.games_count)}
            </p>
          </div>
        </div>
      </div>
      <div className="border-t border-white/[0.06] bg-white/[0.015] px-5 py-2.5 sm:px-6">
        <DataStatusBanner meta={data} />
      </div>
    </Panel>
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
        className="flex gap-1 overflow-x-auto rounded-2xl border border-white/[0.07] bg-board-900/60 p-1.5 backdrop-blur-sm"
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
            className={`whitespace-nowrap rounded-xl px-4 py-2 text-sm transition-colors ${
              active === tab.id
                ? 'bg-mint-400 font-semibold text-board-950 shadow-[0_8px_24px_-10px] shadow-mint-400/80'
                : 'font-medium text-chalk-300 hover:bg-white/5 hover:text-chalk-50'
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
        className="pt-5"
      >
        {active === 'overview' && overview}
        {active === 'form' && <FormPanel api={api} username={username} />}
        {active === 'rating' && <RatingTab api={api} username={username} />}
        {active === 'openings' && <OpeningsTab api={api} username={username} />}
        {active === 'opponents' && <OpponentsTab api={api} username={username} />}
        {active === 'games' && <GamesPanel api={api} username={username} />}
      </div>
    </div>
  );
}

function RatingTab({ api, username }: { api: ChesspulseApi; username: string }) {
  const state = useApi(`${username}`, (signal) => api.ratingHistory(username, signal));
  return (
    <Section state={state} loadingLabel="Loading rating history…">
      {(data) => (
        <div className="space-y-3">
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
    <section aria-labelledby="openings-heading" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Eyebrow>Repertoire</Eyebrow>
          <h2
            id="openings-heading"
            className="mt-1 font-display text-2xl tracking-tight text-chalk-50"
          >
            Openings
          </h2>
        </div>
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
    <section aria-labelledby="opponents-heading" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Eyebrow>Rivalries</Eyebrow>
          <h2
            id="opponents-heading"
            className="mt-1 font-display text-2xl tracking-tight text-chalk-50"
          >
            Opponents
          </h2>
        </div>
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
