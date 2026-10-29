import { Eyebrow, Panel } from '../../components/ui';
import type { Overview } from '../../types/api';
import {
  formatDate,
  formatDateTime,
  formatNumber,
  formatPercent,
  MISSING,
} from '../../utils/format';

function StatValue({ value }: { value: string }) {
  if (value !== MISSING) return <>{value}</>;
  return (
    <>
      <span aria-hidden="true">{MISSING}</span>
      <span className="sr-only">not available</span>
    </>
  );
}

function HeroStat({
  label,
  value,
  hint,
  accent = false,
}: {
  label: string;
  value: string;
  hint?: string;
  accent?: boolean;
}) {
  return (
    <div
      className={`relative overflow-hidden rounded-2xl border p-4 sm:p-5 ${
        accent
          ? 'border-mint-400/25 bg-gradient-to-br from-mint-400/[0.13] via-mint-400/[0.04] to-transparent'
          : 'border-white/[0.07] bg-board-900/60'
      }`}
    >
      <dt className="text-[11px] uppercase tracking-[0.14em] text-chalk-400">{label}</dt>
      <dd
        className={`mt-2 font-display text-3xl leading-none tabular-nums sm:text-4xl ${
          accent ? 'text-mint-300' : 'text-chalk-50'
        }`}
      >
        <StatValue value={value} />
      </dd>
      {hint && <p className="mt-2 text-xs leading-snug text-chalk-500">{hint}</p>}
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
  const hasGames = overview.games_count > 0;
  const share = (count: number) =>
    overview.games_count > 0 ? `${(count / overview.games_count) * 100}%` : '0%';

  return (
    <section aria-labelledby="overview-heading" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <Eyebrow>Overview</Eyebrow>
          <h2
            id="overview-heading"
            className="mt-1 font-display text-2xl tracking-tight text-chalk-50"
          >
            Rapid, {formatDate(overview.period.start)} – {formatDate(overview.period.end)}
          </h2>
        </div>
        <span className="rounded-full border border-white/10 bg-board-900/60 px-3 py-1 text-[11px] text-chalk-400">
          Last 30 days
        </span>
      </div>

      {overview.games_count === 0 && (
        <p className="rounded-2xl border border-dashed border-white/15 bg-board-900/40 p-4 text-sm text-chalk-300">
          No eligible Rapid games in the last 30 days.
        </p>
      )}

      <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <HeroStat label="Games" value={formatNumber(overview.games_count)} />
        <HeroStat
          label="Win rate"
          value={formatPercent(overview.win_rate)}
          hint="Wins ÷ (wins + losses + draws)"
          accent
        />
        <HeroStat
          label="Current Rapid rating"
          value={formatNumber(overview.current_rating)}
          hint={rating ? `From Chess.com stats, ${formatDateTime(rating.as_of)}` : 'Not available'}
        />
        <HeroStat
          label="Current streak"
          value={streakText(overview)}
          hint={overview.current_streak ? 'Most recent games first' : undefined}
        />
      </dl>

      <div className="grid gap-3 lg:grid-cols-[1.35fr_1fr]">
        <Panel className="p-4 sm:p-5">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-medium text-chalk-100">Record</h3>
            <span className="text-xs tabular-nums text-chalk-500">
              {formatNumber(overview.games_count)} games
            </span>
          </div>
          <div
            aria-hidden="true"
            className="mt-4 flex h-2.5 gap-0.5 overflow-hidden rounded-full bg-board-700"
          >
            {hasGames && (
              <>
                <span className="h-full bg-mint-400" style={{ width: share(overview.wins) }} />
                <span className="h-full bg-coral-400" style={{ width: share(overview.losses) }} />
                <span className="h-full bg-chalk-400" style={{ width: share(overview.draws) }} />
                <span
                  className="h-full bg-gold-400"
                  style={{ width: share(overview.unknown_results) }}
                />
              </>
            )}
          </div>
          <p className="sr-only">
            {overview.wins} wins, {overview.losses} losses, {overview.draws} draws.
          </p>
          <dl className="mt-4 grid grid-cols-3 gap-3">
            <div>
              <dt className="flex items-center gap-1.5 text-xs text-chalk-400">
                <span aria-hidden="true" className="h-2 w-2 rounded-full bg-mint-400" />
                Wins
              </dt>
              <dd className="mt-1 font-display text-2xl leading-none tabular-nums text-chalk-50">
                {formatNumber(overview.wins)}
              </dd>
            </div>
            <div>
              <dt className="flex items-center gap-1.5 text-xs text-chalk-400">
                <span aria-hidden="true" className="h-2 w-2 rounded-full bg-coral-400" />
                Losses
              </dt>
              <dd className="mt-1 font-display text-2xl leading-none tabular-nums text-chalk-50">
                {formatNumber(overview.losses)}
              </dd>
            </div>
            <div>
              <dt className="flex items-center gap-1.5 text-xs text-chalk-400">
                <span aria-hidden="true" className="h-2 w-2 rounded-full bg-chalk-400" />
                Draws
              </dt>
              <dd className="mt-1 font-display text-2xl leading-none tabular-nums text-chalk-50">
                {formatNumber(overview.draws)}
              </dd>
            </div>
          </dl>
        </Panel>

        <Panel className="p-4 sm:p-5">
          <h3 className="text-sm font-medium text-chalk-100">Streaks</h3>
          <dl className="mt-4 space-y-4">
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-sm text-chalk-300">Longest winning streak</dt>
              <dd className="font-display text-xl tabular-nums text-chalk-50">
                <StatValue value={formatNumber(overview.longest_winning_streak)} />
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-sm text-chalk-300">Unknown results</dt>
              <dd className="font-display text-xl tabular-nums text-chalk-50">
                {formatNumber(overview.unknown_results)}
              </dd>
            </div>
          </dl>
          {overview.unknown_results > 0 && (
            <p className="mt-4 border-t border-white/[0.06] pt-3 text-xs leading-relaxed text-chalk-500">
              {overview.unknown_results} game(s) have an unknown result and are not counted in the
              win rate.
            </p>
          )}
        </Panel>
      </div>

      {overview.streak_may_be_incomplete && (
        <p className="rounded-xl border border-gold-400/25 bg-gold-400/10 px-3 py-2 text-xs leading-relaxed text-gold-300">
          Streaks may not reflect every game: some results or games are missing.
        </p>
      )}
    </section>
  );
}
