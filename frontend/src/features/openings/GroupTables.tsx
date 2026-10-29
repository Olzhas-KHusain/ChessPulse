import { useId } from 'react';

import { EmptyNotice } from '../../components/StateViews';
import { Panel } from '../../components/ui';
import type { GroupSort, Openings, Opponents } from '../../types/api';
import { formatDate, formatNumber, formatPercent } from '../../utils/format';

export function SortSelect({
  value,
  onChange,
}: {
  value: GroupSort;
  onChange: (sort: GroupSort) => void;
}) {
  const id = useId();
  return (
    <div className="flex items-center gap-2 text-xs text-chalk-400">
      <label htmlFor={id}>Sort by</label>
      <div className="relative">
        <select
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value as GroupSort)}
          className="appearance-none rounded-lg border border-white/10 bg-board-850 py-1.5 pl-3 pr-8 text-xs text-chalk-100"
        >
          <option value="games">Most games</option>
          <option value="win_rate">Win rate</option>
          <option value="name">Name</option>
        </select>
        <span
          aria-hidden="true"
          className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[10px] text-chalk-500"
        >
          ▾
        </span>
      </div>
    </div>
  );
}

const TH =
  'whitespace-nowrap px-4 py-3 text-[10px] font-medium uppercase tracking-[0.14em] text-chalk-500';
const TD = 'px-4 py-3 align-middle';

function WinRate({ value }: { value: number | null }) {
  const width = value === null ? 0 : Math.max(0, Math.min(100, value));
  return (
    <div className="flex items-center gap-2.5">
      <span className="tabular-nums text-chalk-100">{formatPercent(value)}</span>
      {value !== null && (
        <span
          aria-hidden="true"
          className="hidden h-1 w-16 overflow-hidden rounded-full bg-board-700 sm:block"
        >
          <span
            className={`block h-full rounded-full ${width >= 50 ? 'bg-mint-400' : 'bg-coral-400'}`}
            style={{ width: `${width}%` }}
          />
        </span>
      )}
    </div>
  );
}

export function OpeningsTable({ data }: { data: Openings }) {
  if (data.items.length === 0)
    return <EmptyNotice>No openings to show for this period.</EmptyNotice>;
  return (
    <Panel className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[32rem] text-left text-sm">
          <caption className="sr-only">
            Opening statistics from the searched player's perspective
          </caption>
          <thead className="border-b border-white/[0.07] bg-white/[0.025]">
            <tr>
              <th scope="col" className={TH}>
                Opening
              </th>
              <th scope="col" className={TH}>
                Games
              </th>
              <th scope="col" className={TH}>
                W / L / D
              </th>
              <th scope="col" className={TH}>
                Win rate
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {data.items.map((item) => (
              <tr
                key={item.opening_key ?? '__unknown__'}
                className="transition-colors hover:bg-white/[0.03]"
              >
                <td className={`${TD} text-chalk-100`}>
                  {item.is_unknown ? (
                    <em className="text-chalk-400">Unknown opening</em>
                  ) : (
                    item.name
                  )}
                  {item.eco_code && (
                    <span className="ml-1.5 text-xs text-chalk-500">({item.eco_code})</span>
                  )}
                </td>
                <td className={`${TD} tabular-nums text-chalk-200`}>{item.games_count}</td>
                <td className={`${TD} tabular-nums text-chalk-300`}>
                  <span className="text-mint-300">{item.wins}</span>
                  {' / '}
                  <span className="text-coral-300">{item.losses}</span>
                  {' / '}
                  {item.draws}
                  {item.unknown_results > 0 && (
                    <span className="text-chalk-500"> (+{item.unknown_results} unknown)</span>
                  )}
                </td>
                <td className={TD}>
                  <WinRate value={item.win_rate} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="border-t border-white/[0.06] px-4 py-2.5 text-xs text-chalk-500">
        Showing {data.items.length} of {data.total_groups}. Small samples are not conclusive.
      </p>
    </Panel>
  );
}

export function OpponentsTable({ data }: { data: Opponents }) {
  if (data.items.length === 0)
    return <EmptyNotice>No opponents to show for this period.</EmptyNotice>;
  return (
    <Panel className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[36rem] text-left text-sm">
          <caption className="sr-only">
            Results against each opponent, from the searched player's side
          </caption>
          <thead className="border-b border-white/[0.07] bg-white/[0.025]">
            <tr>
              <th scope="col" className={TH}>
                Opponent
              </th>
              <th scope="col" className={TH}>
                Games
              </th>
              <th scope="col" className={TH}>
                Your W / L / D
              </th>
              <th scope="col" className={TH}>
                Win rate
              </th>
              <th scope="col" className={TH}>
                Last game
              </th>
              <th scope="col" className={TH}>
                Their rating
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {data.items.map((item) => (
              <tr key={item.opponent_username} className="transition-colors hover:bg-white/[0.03]">
                <td className={`${TD} font-medium`}>
                  <a
                    href={item.profile_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-chalk-100 underline decoration-white/20 underline-offset-4 transition hover:text-mint-300 hover:decoration-mint-400/60"
                  >
                    {item.opponent_username}
                  </a>
                </td>
                <td className={`${TD} tabular-nums text-chalk-200`}>{item.games_count}</td>
                <td className={`${TD} tabular-nums text-chalk-300`}>
                  <span className="text-mint-300">{item.wins}</span>
                  {' / '}
                  <span className="text-coral-300">{item.losses}</span>
                  {' / '}
                  {item.draws}
                </td>
                <td className={TD}>
                  <WinRate value={item.win_rate} />
                </td>
                <td className={`${TD} text-chalk-400`}>{formatDate(item.last_played_at)}</td>
                <td className={`${TD} tabular-nums text-chalk-300`}>
                  {formatNumber(item.last_rating)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="border-t border-white/[0.06] px-4 py-2.5 text-xs text-chalk-500">
        Showing {data.items.length} of {data.total_groups}.
      </p>
    </Panel>
  );
}
