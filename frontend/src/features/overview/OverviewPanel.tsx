import type { Overview } from '../../types/api';
import {
  formatDate,
  formatDateTime,
  formatNumber,
  formatPercent,
  MISSING,
} from '../../utils/format';

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <dt className="text-sm text-slate-600">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold text-slate-900">
        {value === MISSING ? (
          <>
            <span aria-hidden="true">{MISSING}</span>
            <span className="sr-only">not available</span>
          </>
        ) : (
          value
        )}
      </dd>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

function streakText(overview: Overview): string {
  const streak = overview.current_streak;
  if (!streak) return MISSING;
  const noun = { win: 'win', loss: 'loss', draw: 'draw' }[streak.type];
  const plural = streak.type === 'loss' ? 'losses' : `${noun}s`;
  return `${streak.length} ${streak.length === 1 ? noun : plural}`;
}

export function OverviewPanel({ overview }: { overview: Overview }) {
  const rating = overview.current_rating_detail;
  return (
    <section aria-labelledby="overview-heading" className="space-y-3">
      <h2 id="overview-heading" className="text-lg font-semibold">
        Rapid, {formatDate(overview.period.start)} – {formatDate(overview.period.end)}
      </h2>
      {overview.games_count === 0 && (
        <p className="rounded-md border border-dashed border-slate-300 p-3 text-slate-700">
          No eligible Rapid games in the last 30 days.
        </p>
      )}
      <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Metric label="Games" value={formatNumber(overview.games_count)} />
        <Metric
          label="Win rate"
          value={formatPercent(overview.win_rate)}
          hint="Wins ÷ (wins + losses + draws)"
        />
        <Metric label="Wins" value={formatNumber(overview.wins)} />
        <Metric label="Losses" value={formatNumber(overview.losses)} />
        <Metric label="Draws" value={formatNumber(overview.draws)} />
        <Metric
          label="Current Rapid rating"
          value={formatNumber(overview.current_rating)}
          hint={rating ? `From Chess.com stats, ${formatDateTime(rating.as_of)}` : 'Not available'}
        />
        <Metric label="Current streak" value={streakText(overview)} />
        <Metric
          label="Longest winning streak"
          value={formatNumber(overview.longest_winning_streak)}
        />
      </dl>
      {overview.unknown_results > 0 && (
        <p className="text-sm text-slate-600">
          {overview.unknown_results} game(s) have an unknown result and are not counted in the win
          rate.
        </p>
      )}
      {overview.streak_may_be_incomplete && (
        <p className="text-sm text-slate-600">
          Streaks may not reflect every game: some results or games are missing.
        </p>
      )}
    </section>
  );
}
