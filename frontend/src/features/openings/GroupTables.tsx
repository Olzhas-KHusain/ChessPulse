import { useId } from 'react';

import { EmptyNotice } from '../../components/StateViews';
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
    <div className="flex items-center gap-2 text-sm">
      <label htmlFor={id}>Sort by</label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value as GroupSort)}
        className="rounded border border-slate-300 px-2 py-1 focus-visible:ring-2 focus-visible:ring-indigo-600"
      >
        <option value="games">Most games</option>
        <option value="win_rate">Win rate</option>
        <option value="name">Name</option>
      </select>
    </div>
  );
}

const th = 'px-2 py-1 font-medium';
const td = 'px-2 py-1';

export function OpeningsTable({ data }: { data: Openings }) {
  if (data.items.length === 0)
    return <EmptyNotice>No openings to show for this period.</EmptyNotice>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[32rem] text-left text-sm">
        <caption className="sr-only">
          Opening statistics from the searched player's perspective
        </caption>
        <thead className="bg-slate-100">
          <tr>
            <th scope="col" className={th}>
              Opening
            </th>
            <th scope="col" className={th}>
              Games
            </th>
            <th scope="col" className={th}>
              W / L / D
            </th>
            <th scope="col" className={th}>
              Win rate
            </th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((item) => (
            <tr key={item.opening_key ?? '__unknown__'} className="border-b border-slate-100">
              <td className={td}>
                {item.is_unknown ? <em>Unknown opening</em> : item.name}
                {item.eco_code && (
                  <span className="ml-1 text-xs text-slate-500">({item.eco_code})</span>
                )}
              </td>
              <td className={td}>{item.games_count}</td>
              <td className={td}>
                {item.wins} / {item.losses} / {item.draws}
                {item.unknown_results > 0 && ` (+${item.unknown_results} unknown)`}
              </td>
              <td className={td}>{formatPercent(item.win_rate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-slate-500">
        Showing {data.items.length} of {data.total_groups}. Small samples are not conclusive.
      </p>
    </div>
  );
}

export function OpponentsTable({ data }: { data: Opponents }) {
  if (data.items.length === 0)
    return <EmptyNotice>No opponents to show for this period.</EmptyNotice>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[36rem] text-left text-sm">
        <caption className="sr-only">
          Results against each opponent, from the searched player's side
        </caption>
        <thead className="bg-slate-100">
          <tr>
            <th scope="col" className={th}>
              Opponent
            </th>
            <th scope="col" className={th}>
              Games
            </th>
            <th scope="col" className={th}>
              Your W / L / D
            </th>
            <th scope="col" className={th}>
              Win rate
            </th>
            <th scope="col" className={th}>
              Last game
            </th>
            <th scope="col" className={th}>
              Their rating
            </th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((item) => (
            <tr key={item.opponent_username} className="border-b border-slate-100">
              <td className={td}>
                <a
                  href={item.profile_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-indigo-700 underline"
                >
                  {item.opponent_username}
                </a>
              </td>
              <td className={td}>{item.games_count}</td>
              <td className={td}>
                {item.wins} / {item.losses} / {item.draws}
              </td>
              <td className={td}>{formatPercent(item.win_rate)}</td>
              <td className={td}>{formatDate(item.last_played_at)}</td>
              <td className={td}>{formatNumber(item.last_rating)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-slate-500">
        Showing {data.items.length} of {data.total_groups}.
      </p>
    </div>
  );
}
