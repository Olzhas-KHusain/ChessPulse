import { useCallback, useEffect, useState } from 'react';
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
import { Badge, Eyebrow, Panel, type BadgeTone } from '../../components/ui';
import { ApiError, type ChesspulseApi } from '../../services/chesspulseApi';
import type {
  FormGroup,
  FormLeakKind,
  FormMoment,
  FormReport,
  MoveClassification,
} from '../../types/api';
import { formatDate, formatDateTime, formatNumber, MISSING } from '../../utils/format';

const POLL_MS = 3000;

const CLASSIFICATION_TONE: Record<MoveClassification, BadgeTone> = {
  best: 'win',
  good: 'neutral',
  inaccuracy: 'unknown',
  mistake: 'draw',
  blunder: 'loss',
};

const CLASSIFICATION_LABEL: Record<MoveClassification, string> = {
  best: 'Best',
  good: 'Good',
  inaccuracy: 'Inaccuracy',
  mistake: 'Mistake',
  blunder: 'Blunder',
};

const LEAK_KIND_LABEL: Record<FormLeakKind, string> = {
  phase: 'Phase',
  color: 'Colour',
  opening: 'Opening',
};

const AXIS_TICK = { fill: '#8d887d', fontSize: 11 };
const AXIS_LABEL = { fill: '#6d6a63', fontSize: 11 };

/**
 * Cross-game form report: where the player's win probability actually leaks.
 *
 * Every number comes from stored engine analyses. The headline metric is win-probability
 * points given up per analysed game — never an Elo estimate. The report states how many
 * games are analysed and keeps polling while the worker finishes the rest.
 */
export function FormPanel({ api, username }: { api: ChesspulseApi; username: string }) {
  const [report, setReport] = useState<FormReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [queueing, setQueueing] = useState(false);

  const load = useCallback(
    (signal?: AbortSignal) =>
      api.form(username, signal).then(
        (next) => {
          if (signal?.aborted) return;
          setReport(next);
          setError(null);
        },
        (cause: unknown) => {
          if (signal?.aborted) return;
          setError(cause instanceof ApiError ? cause.message : 'Could not load the form report.');
        },
      ),
    [api, username],
  );

  useEffect(() => {
    const controller = new AbortController();
    setReport(null);
    setError(null);
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const pending = report !== null && report.games_queued + report.games_running > 0;
  useEffect(() => {
    if (!pending) return undefined;
    const timer = setInterval(() => {
      api.form(username).then(setReport, () => undefined);
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [api, username, pending]);

  async function analyzeAll() {
    setQueueing(true);
    setError(null);
    try {
      await api.analyzeForm(username);
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'The analysis could not be requested.');
    } finally {
      setQueueing(false);
    }
  }

  if (error !== null && report === null) {
    return (
      <Panel className="p-4 sm:p-5">
        <Eyebrow>Form report</Eyebrow>
        <p className="mt-2 text-sm text-coral-300">{error}</p>
        <button
          type="button"
          onClick={() => void load()}
          className="mt-3 rounded-lg border border-white/10 bg-board-900/60 px-3 py-1.5 text-xs text-chalk-200 transition hover:border-white/20 hover:text-chalk-50"
        >
          Try again
        </button>
      </Panel>
    );
  }

  if (report === null) {
    return (
      <Panel className="p-4 sm:p-5">
        <Eyebrow>Form report</Eyebrow>
        <p className="mt-2 text-sm text-chalk-400">Loading the cross-game report…</p>
      </Panel>
    );
  }

  const missing = report.games_total - report.games_analyzed;
  const trend = report.accuracy_trend.filter(
    (point): point is typeof point & { accuracy: number } => point.accuracy !== null,
  );

  return (
    <section aria-labelledby="form-heading" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Eyebrow>Why the rating is stuck</Eyebrow>
          <h2 id="form-heading" className="mt-1 font-display text-2xl tracking-tight text-chalk-50">
            Form report
          </h2>
          <p className="mt-1 text-sm text-chalk-400">
            {formatNumber(report.games_analyzed)} of {formatNumber(report.games_total)} eligible
            games analysed · {report.time_class} · rolling 30 days
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {pending && (
            <span className="flex items-center gap-2 rounded-full border border-gold-400/25 bg-gold-400/10 px-3 py-1 text-xs text-gold-300">
              <span aria-hidden="true" className="h-2 w-2 animate-pulse rounded-full bg-gold-400" />
              {formatNumber(report.games_queued + report.games_running)} in the queue
            </span>
          )}
          <button
            type="button"
            onClick={() => void analyzeAll()}
            disabled={queueing || missing <= 0}
            className="rounded-xl bg-mint-400 px-4 py-2 text-sm font-semibold text-board-950 shadow-[0_8px_24px_-10px] shadow-mint-400/80 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {queueing
              ? 'Queueing…'
              : missing <= 0
                ? 'All games analysed'
                : `Analyze ${formatNumber(missing)} remaining`}
          </button>
        </div>
      </div>

      {error !== null && (
        <p className="rounded-xl border border-coral-400/25 bg-coral-400/10 p-3 text-sm text-coral-200">
          {error}
        </p>
      )}

      {report.games_analyzed === 0 ? (
        <EmptyNotice>
          No game has been analysed yet. Run the engine over the whole period to see where the
          rating leaks: phases, colours and openings are only compared once real engine data exists.
        </EmptyNotice>
      ) : (
        <>
          <LeakHeadline report={report} />
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Mean move accuracy" value={pct(report.accuracy_mean)} />
            <Stat label="Opponent accuracy" value={pct(report.opponent_accuracy_mean)} />
            <Stat label="Average centipawn loss" value={formatNumber(report.acpl_mean)} />
            <Stat
              label="Win probability lost / game"
              value={
                report.wp_loss_per_game === null
                  ? MISSING
                  : `${report.wp_loss_per_game.toFixed(1)} pts`
              }
            />
          </div>

          {report.games_failed > 0 && (
            <p className="rounded-xl border border-gold-400/25 bg-gold-400/10 p-3 text-sm text-gold-300">
              {formatNumber(report.games_failed)} game(s) could not be analysed and are excluded
              from the aggregates.
            </p>
          )}

          <AccuracyTrend points={trend} />

          <GroupTables report={report} />

          <TopMoments moments={report.top_moments} />

          <p className="border-l-2 border-white/10 pl-3 text-xs leading-relaxed text-chalk-500">
            “Win probability lost” is the mean drop in the engine’s win probability over your own
            moves, in percentage points per analysed game. Phases are defined by move number:
            opening 1–10, middlegame 11–30, late 31+. This is not an Elo estimate, and groups with
            fewer than three analysed games never become the main leak.
          </p>
        </>
      )}
    </section>
  );
}

function LeakHeadline({ report }: { report: FormReport }) {
  const leak = report.primary_leak;
  if (leak === null) {
    return (
      <Panel className="p-4 sm:p-5">
        <Eyebrow>Main leak</Eyebrow>
        <p className="mt-2 text-sm text-chalk-300">
          No dominant leak yet. A group needs at least three analysed games before it can be named,
          and a real gap between groups before it is worth acting on.
        </p>
      </Panel>
    );
  }
  return (
    <Panel className="overflow-hidden">
      <div className="grid gap-4 p-4 sm:grid-cols-[1fr_auto] sm:items-center sm:p-5">
        <div>
          <Eyebrow>Main leak · {LEAK_KIND_LABEL[leak.kind] ?? leak.kind}</Eyebrow>
          <h3 className="mt-1 font-display text-2xl leading-tight tracking-tight text-chalk-50">
            {leak.label}
          </h3>
          <p className="mt-2 max-w-xl text-sm leading-relaxed text-chalk-400">
            Across {formatNumber(leak.games)} analysed game(s) this slice gives up the most win
            probability: {formatNumber(leak.blunders)} blunder(s) and {formatNumber(leak.mistakes)}{' '}
            mistake(s) in {formatNumber(leak.moves)} of your moves.
          </p>
        </div>
        <div className="rounded-2xl border border-coral-400/25 bg-coral-400/[0.08] px-5 py-4 text-center">
          <p className="text-[10px] uppercase tracking-[0.16em] text-coral-300/80">Lost / game</p>
          <p className="mt-1 font-display text-4xl leading-none tabular-nums text-coral-300">
            {leak.wp_loss_per_game.toFixed(1)}
          </p>
          <p className="mt-1 text-[11px] text-coral-300/70">win-probability points</p>
        </div>
      </div>
    </Panel>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.015] p-3">
      <p className="text-[10px] uppercase tracking-[0.16em] text-chalk-500">{label}</p>
      <p className="mt-1 font-display text-2xl leading-none tabular-nums text-chalk-50">{value}</p>
    </div>
  );
}

function AccuracyTrend({
  points,
}: {
  points: Array<{
    game_id: string;
    played_at: string;
    accuracy: number;
    opponent: string;
  }>;
}) {
  if (points.length === 0) {
    return <EmptyNotice>No analysed game reported an accuracy value yet.</EmptyNotice>;
  }
  const data = points.map((point) => ({ ...point, time: new Date(point.played_at).getTime() }));
  return (
    <Panel className="p-3 sm:p-5">
      <h3 className="px-1 text-sm font-medium text-chalk-100">Accuracy per analysed game</h3>
      <div className="mt-2 h-64 w-full" aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 28, left: 0 }}>
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
              domain={[0, 100]}
              width={40}
              tick={AXIS_TICK}
              axisLine={false}
              tickLine={false}
              label={{
                value: 'Accuracy (%)',
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
              formatter={(value) => [`${Number(value).toFixed(1)}%`, 'Accuracy']}
            />
            <Line
              type="monotone"
              dataKey="accuracy"
              stroke="#4fd6a4"
              strokeWidth={2.5}
              dot={{ r: 2.5, fill: '#4fd6a4', strokeWidth: 0 }}
              activeDot={{ r: 5, fill: '#b9f2db', stroke: '#05080c', strokeWidth: 2 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

function GroupTables({ report }: { report: FormReport }) {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <GroupTable title="By phase" groups={report.by_phase} />
      <GroupTable title="By colour" groups={report.by_color} />
      <GroupTable
        title="By opening"
        groups={report.by_opening}
        empty="Each opening needs at least two analysed games."
      />
    </div>
  );
}

function GroupTable({
  title,
  groups,
  empty = 'No analysed games in this slice.',
}: {
  title: string;
  groups: FormGroup[];
  empty?: string;
}) {
  return (
    <Panel className="p-4">
      <h3 className="text-sm font-medium text-chalk-100">{title}</h3>
      {groups.length === 0 ? (
        <p className="mt-2 text-sm text-chalk-400">{empty}</p>
      ) : (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">{title}</caption>
            <thead>
              <tr className="border-b border-white/[0.07] text-[10px] uppercase tracking-[0.14em] text-chalk-500">
                <th scope="col" className="py-2 pr-2 font-medium">
                  Group
                </th>
                <th scope="col" className="px-2 py-2 text-right font-medium">
                  Games
                </th>
                <th scope="col" className="px-2 py-2 text-right font-medium">
                  Lost / game
                </th>
                <th scope="col" className="px-2 py-2 text-right font-medium">
                  B · M
                </th>
                <th scope="col" className="py-2 pl-2 text-right font-medium">
                  Accuracy
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {groups.map((group) => (
                <tr key={group.key}>
                  <td className="py-2 pr-2 text-chalk-200">{group.label}</td>
                  <td className="px-2 py-2 text-right tabular-nums text-chalk-300">
                    {formatNumber(group.games)}
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums text-coral-300">
                    {group.games === 0 ? MISSING : group.wp_loss_per_game.toFixed(1)}
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums text-chalk-300">
                    {group.blunders} · {group.mistakes}
                  </td>
                  <td className="py-2 pl-2 text-right tabular-nums text-chalk-300">
                    {pct(group.accuracy)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function TopMoments({ moments }: { moments: FormMoment[] }) {
  return (
    <Panel className="p-4 sm:p-5">
      <h3 className="text-sm font-medium text-chalk-100">Most expensive moments</h3>
      {moments.length === 0 ? (
        <p className="mt-2 rounded-xl border border-dashed border-white/15 bg-board-900/40 p-3 text-sm text-chalk-400">
          No inaccuracies, mistakes or blunders were found in the analysed games.
        </p>
      ) : (
        <ol className="mt-2 divide-y divide-white/[0.05]">
          {moments.map((moment) => (
            <li
              key={`${moment.game_id}-${moment.move_number}-${moment.san}`}
              className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"
            >
              <span className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="w-10 shrink-0 tabular-nums text-chalk-500">
                  {moment.move_number}.
                </span>
                <span className="font-mono text-chalk-100">{moment.san}</span>
                <Badge tone={CLASSIFICATION_TONE[moment.classification]}>
                  {CLASSIFICATION_LABEL[moment.classification]}
                </Badge>
                <span className="text-xs text-chalk-400">
                  −{moment.wp_loss.toFixed(1)} wp · −{formatNumber(moment.cp_loss)} cp
                </span>
              </span>
              <span className="text-xs text-chalk-500">
                {moment.game_url ? (
                  <a
                    href={moment.game_url}
                    target="_blank"
                    rel="noreferrer"
                    className="transition hover:text-mint-300"
                  >
                    vs {moment.opponent} ↗
                  </a>
                ) : (
                  `vs ${moment.opponent}`
                )}
                {moment.opening_name ? ` · ${moment.opening_name}` : ''}
              </span>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}

function pct(value: number | null): string {
  return value === null ? MISSING : `${value.toFixed(1)}%`;
}
