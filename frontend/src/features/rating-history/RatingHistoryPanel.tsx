import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { EmptyNotice } from '../../components/StateViews';
import type { RatingHistory } from '../../types/api';
import { formatDate, formatDateTime } from '../../utils/format';

export function RatingHistoryPanel({ history }: { history: RatingHistory }) {
  const points = history.points.map((p) => ({ ...p, time: new Date(p.timestamp).getTime() }));
  return (
    <section aria-labelledby="rating-heading" className="space-y-3">
      <h2 id="rating-heading" className="text-lg font-semibold">
        Rating history (Rapid)
      </h2>
      {points.length === 0 ? (
        <EmptyNotice>No rating observations are available for this period.</EmptyNotice>
      ) : (
        <>
          <div className="h-64 w-full" aria-hidden="true">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={points} margin={{ top: 8, right: 16, bottom: 24, left: 8 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="time"
                  type="number"
                  scale="time"
                  domain={['dataMin', 'dataMax']}
                  tickFormatter={(t: number) => formatDate(new Date(t).toISOString())}
                  label={{ value: 'Game end time (local)', position: 'insideBottom', offset: -16 }}
                />
                <YAxis
                  domain={['auto', 'auto']}
                  label={{ value: 'Rating', angle: -90, position: 'insideLeft' }}
                />
                <Tooltip
                  labelFormatter={(t) => formatDateTime(new Date(Number(t)).toISOString())}
                  formatter={(v) => [String(v), 'Rating reported with the game']}
                />
                <Line type="linear" dataKey="rating" stroke="#4338ca" dot connectNulls={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <details className="text-sm">
            <summary className="cursor-pointer">Rating observations as a table</summary>
            <table className="mt-2 w-full text-left">
              <caption className="sr-only">Rating observations</caption>
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Rating</th>
                </tr>
              </thead>
              <tbody>
                {history.points.map((p) => (
                  <tr key={`${p.game_id}`}>
                    <td>{formatDateTime(p.timestamp)}</td>
                    <td>{p.rating}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      )}
      <p className="text-xs text-slate-500">
        One point per game that reported a rating; days without games have no point. Chess.com does
        not state whether a game rating is before or after the game.
        {history.coverage === 'partial' &&
          ` Coverage is partial: ${history.games_without_rating} game(s) had no rating or some games are missing.`}
      </p>
    </section>
  );
}
