import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { EmptyNotice } from '../../components/StateViews';
import { Eyebrow, Panel } from '../../components/ui';
import type { RatingHistory } from '../../types/api';
import { formatDate, formatDateTime, formatNumber } from '../../utils/format';

const AXIS_TICK = { fill: '#8d887d', fontSize: 11 };
const AXIS_LABEL = { fill: '#6d6a63', fontSize: 11 };

export function RatingHistoryPanel({ history }: { history: RatingHistory }) {
  const points = history.points.map((p) => ({ ...p, time: new Date(p.timestamp).getTime() }));
  const first = points.at(0);
  const last = points.at(-1);
  const change = first && last ? last.rating - first.rating : null;

  return (
    <section aria-labelledby="rating-heading" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Eyebrow>Trend</Eyebrow>
          <h2
            id="rating-heading"
            className="mt-1 font-display text-2xl tracking-tight text-chalk-50"
          >
            Rating history (Rapid)
          </h2>
        </div>
        {last && (
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="rounded-full border border-white/10 bg-board-900/60 px-3 py-1 text-chalk-300">
              Latest <span className="font-semibold tabular-nums text-chalk-50">{last.rating}</span>
            </span>
            {change !== null && (
              <span
                className={`rounded-full border px-3 py-1 tabular-nums ${
                  change >= 0
                    ? 'border-mint-400/25 bg-mint-400/10 text-mint-300'
                    : 'border-coral-400/25 bg-coral-400/10 text-coral-300'
                }`}
              >
                {change >= 0 ? '+' : ''}
                {change} over period
              </span>
            )}
            <span className="rounded-full border border-white/10 bg-board-900/60 px-3 py-1 tabular-nums text-chalk-400">
              {formatNumber(points.length)} observations
            </span>
          </div>
        )}
      </div>

      {points.length === 0 ? (
        <EmptyNotice>No rating observations are available for this period.</EmptyNotice>
      ) : (
        <>
          <Panel className="p-3 sm:p-5">
            <div className="h-72 w-full" aria-hidden="true">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={points} margin={{ top: 8, right: 12, bottom: 28, left: 0 }}>
                  <defs>
                    <linearGradient id="rating-fill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#4fd6a4" stopOpacity={0.32} />
                      <stop offset="100%" stopColor="#4fd6a4" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#16202b" strokeDasharray="3 6" vertical={false} />
                  <XAxis
                    dataKey="time"
                    type="number"
                    scale="time"
                    domain={['dataMin', 'dataMax']}
                    tickFormatter={(t: number) => formatDate(new Date(t).toISOString())}
                    tick={AXIS_TICK}
                    axisLine={{ stroke: '#16202b' }}
                    tickLine={false}
                    label={{
                      value: 'Game end time (local)',
                      position: 'insideBottom',
                      offset: -18,
                      ...AXIS_LABEL,
                    }}
                  />
                  <YAxis
                    domain={['auto', 'auto']}
                    width={44}
                    tick={AXIS_TICK}
                    axisLine={false}
                    tickLine={false}
                    label={{
                      value: 'Rating',
                      angle: -90,
                      position: 'insideLeft',
                      ...AXIS_LABEL,
                    }}
                  />
                  <Tooltip
                    cursor={{ stroke: '#2b3d4e', strokeDasharray: '3 3' }}
                    contentStyle={{
                      backgroundColor: '#0e151e',
                      border: '1px solid #1f2d3b',
                      borderRadius: 12,
                      boxShadow: '0 20px 50px -20px rgb(0 0 0 / 0.9)',
                    }}
                    labelStyle={{ color: '#b6b0a3', fontSize: 12 }}
                    itemStyle={{ color: '#86e6c0', fontSize: 12 }}
                    labelFormatter={(t) => formatDateTime(new Date(Number(t)).toISOString())}
                    formatter={(v) => [String(v), 'Rating reported with the game']}
                  />
                  <Area
                    type="linear"
                    dataKey="rating"
                    stroke="#4fd6a4"
                    strokeWidth={2.5}
                    fill="url(#rating-fill)"
                    dot={{ r: 2.5, fill: '#4fd6a4', strokeWidth: 0 }}
                    activeDot={{ r: 5, fill: '#b9f2db', stroke: '#05080c', strokeWidth: 2 }}
                    connectNulls={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Panel>

          <details className="group rounded-2xl border border-white/[0.07] bg-board-900/40 px-4 py-3 text-sm">
            <summary className="cursor-pointer list-none text-chalk-300 transition hover:text-chalk-50">
              <span
                aria-hidden="true"
                className="mr-2 inline-block text-[10px] text-chalk-500 transition group-open:rotate-90"
              >
                ▶
              </span>
              Rating observations as a table
            </summary>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Rating observations</caption>
                <thead>
                  <tr className="border-b border-white/[0.07] text-[10px] uppercase tracking-[0.14em] text-chalk-500">
                    <th scope="col" className="px-2 py-2 font-medium">
                      Time
                    </th>
                    <th scope="col" className="px-2 py-2 font-medium">
                      Rating
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {history.points.map((p) => (
                    <tr key={`${p.game_id}`}>
                      <td className="px-2 py-2 text-chalk-300">{formatDateTime(p.timestamp)}</td>
                      <td className="px-2 py-2 tabular-nums text-chalk-100">{p.rating}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}

      <p className="border-l-2 border-white/10 pl-3 text-xs leading-relaxed text-chalk-500">
        One point per game that reported a rating; days without games have no point. Chess.com does
        not state whether a game rating is before or after the game.
        {history.coverage === 'partial' &&
          ` Coverage is partial: ${history.games_without_rating} game(s) had no rating or some games are missing.`}
      </p>
    </section>
  );
}
