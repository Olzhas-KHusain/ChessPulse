/**
 * Decorative chessboard for the landing page. It is pure presentation: the
 * highlighted squares are arbitrary and carry no data.
 */

const HIGHLIGHTED = new Set([
  '0-1',
  '1-3',
  '2-0',
  '2-4',
  '3-2',
  '3-6',
  '4-1',
  '4-5',
  '5-3',
  '5-7',
  '6-2',
  '6-6',
  '7-4',
]);

export function BoardMotif() {
  return (
    <div aria-hidden="true" className="relative mx-auto w-full max-w-sm select-none">
      <div className="absolute -inset-8 rounded-[3rem] bg-mint-400/10 blur-3xl" />
      <div className="relative rotate-3 rounded-3xl border border-white/10 bg-board-900/70 p-3 shadow-lift backdrop-blur">
        <div className="grid grid-cols-8 overflow-hidden rounded-xl">
          {Array.from({ length: 64 }, (_, index) => {
            const row = Math.floor(index / 8);
            const column = index % 8;
            const light = (row + column) % 2 === 0;
            const highlighted = HIGHLIGHTED.has(`${row}-${column}`);
            return (
              <div
                key={index}
                className={`aspect-square ${
                  highlighted ? 'bg-mint-400/70' : light ? 'bg-chalk-100/10' : 'bg-board-800'
                }`}
              />
            );
          })}
        </div>
        <div className="pointer-events-none absolute inset-0 grid place-items-center">
          <span className="font-display text-7xl text-chalk-50 drop-shadow-[0_12px_30px_rgba(0,0,0,0.85)]">
            ♞
          </span>
        </div>
      </div>
      <div className="absolute -bottom-5 -left-3 rounded-2xl border border-white/10 bg-board-850/90 px-4 py-3 shadow-lift backdrop-blur sm:-left-6">
        <p className="text-[10px] uppercase tracking-[0.18em] text-chalk-500">Built for</p>
        <p className="mt-1 font-display text-lg leading-none text-chalk-50">Rapid · 30 days</p>
      </div>
    </div>
  );
}
