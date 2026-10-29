import type { ReactNode } from 'react';

/** Shared surface used by every panel so borders, blur and radius stay consistent. */
export function Panel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-2xl border border-white/[0.07] bg-board-900/60 shadow-lift backdrop-blur-sm ${className}`}
    >
      {children}
    </div>
  );
}

export function Eyebrow({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <p
      className={`text-[10px] font-medium uppercase tracking-[0.18em] text-chalk-500 ${className}`}
    >
      {children}
    </p>
  );
}

export type BadgeTone = 'win' | 'loss' | 'draw' | 'unknown' | 'mint' | 'neutral';

const BADGE_TONES: Record<BadgeTone, string> = {
  win: 'bg-mint-400/15 text-mint-300 ring-mint-400/25',
  loss: 'bg-coral-400/15 text-coral-300 ring-coral-400/25',
  draw: 'bg-chalk-400/15 text-chalk-200 ring-chalk-400/25',
  unknown: 'bg-gold-400/15 text-gold-300 ring-gold-400/25',
  mint: 'bg-mint-400/15 text-mint-300 ring-mint-400/25',
  neutral: 'bg-white/5 text-chalk-300 ring-white/10',
};

export function Badge({ tone = 'neutral', children }: { tone?: BadgeTone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ring-1 ring-inset ${BADGE_TONES[tone]}`}
    >
      {children}
    </span>
  );
}
