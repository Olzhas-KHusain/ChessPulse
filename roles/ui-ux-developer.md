# Role: UI/UX Developer

*Owns the browser-facing surface of ChessPulse — dashboard, game details, free board and theme — so it is honest about data, usable with a keyboard, readable in both themes and on a phone, and never turns "unknown" into a zero.*

You implement the React/TypeScript/Tailwind layer. The numbers come from the API and `docs/specs/`; you do not invent metrics in the UI. Product scope belongs to [`pm.md`](pm.md); deployment belongs to [`devops-engineer.md`](devops-engineer.md); shared engineering rules are in `AGENT.md`.

---

## The product in one paragraph

ChessPulse shows a Chess.com player's results across Rapid, Blitz, Bullet and Daily over a selectable 7–365 day window, plus a free Stockfish board that needs no account. The UI's job is to make the data legible and to say clearly when it is stale, missing, partial or cached. Honesty about data is the feature, not a disclaimer.

---

## Stack and layout

- React 19, TypeScript strict, Vite, Tailwind CSS 4 (`@theme` tokens in `src/index.css`), Recharts, `chess.js`.
- No client router: `App.tsx` switches between `analytics` and `board` with state. Do not add a router for a two-view app.
- Feature folders: `src/features/<area>/`; shared primitives in `src/components/ui.tsx`; API in `src/services/chesspulseApi.ts`; response types in `src/types/api.ts`.
- Data sections go through `useApi` and handle loading, empty, stale, partial and error states explicitly via `StateViews`.

---

## Design language

- Dark is the default. The palette is an editorial "analysis board": near-black surfaces, ivory text, mint as the single accent, gold/coral reserved for data states.
- Display headings use the serif face (`font-display`); body text uses sans; moves and numbers use mono.
- Motion is restrained (`animate-rise`, `animate-fade`) and respects `prefers-reduced-motion`.
- Use tokens from `index.css`, not literals. Text on a mint accent uses `text-on-accent`; do not assume white or black.

## Themes

- Two themes. Light is a **token override** under `html[data-theme='light']`, not per-component variants.
- The toggle persists in `localStorage` under `chesspulse-theme`; the inline boot script in `index.html` sets `data-theme` before first paint so there is no flash.
- `--color-white` is remapped in light because the layout uses white for hairlines and overlays.
- The board and evaluation bar have their own tokens (`--color-square-*`, `--color-eval-*`). Check both themes: a hard-coded hex that looks fine on dark can vanish on paper.

---

## Honesty rules (the product's core)

- **Unknown is not zero.** Use `MISSING` and null states; never render an absent value as `0`.
- **Stale data must look stale.** Show the last successful refresh and the rolling UTC window end (`OverviewPanel`); do not imply live data.
- **Opening names are provider-verbatim.** Chess.com's `eco` URL names a game by the resulting position, so a transposition can carry another opening's name. `Dashboard` explains this. Do not "fix" a name by guessing.
- **Engine numbers name their source.** Say "mean move accuracy" and show the engine and depth; never present accuracy as an Elo estimate.
- **Sample size matters.** Do not call an opening a "primary leak" from two games; the form report already encodes this rule.
- **Empty states are designed screens**, not blank areas.

---

## The free board

- `BoardPanel` stores an 8×8 grid (`position.ts`), not a `Chess` instance, because a position may be illegal while the user is still placing pieces.
- **Analysis is a toggle, default on.** When it is off, moves are played locally with `chess.js`, engine endpoints are not called, the evaluation card says "Analysis is off", and the move list hides classification and cp-loss.
- Undo/redo stores snapshots of `{fen, moves, evaluation}`; a new move clears the redo stack.
- Every square is a real `<button>` with an `aria-label` such as `e2 white pawn`. Keyboard and screen-reader users must be able to play. Do not replace squares with `div`s.
- White and black pieces use different rendering (stroke + shadow); verify contrast on both square colours in both themes.

## Game details

- `GameBoard` replays the PGN main line and allows trial branches from any position. "Main line" discards the branch.
- Analysis starts **only** when the user clicks "Analyze with Stockfish". The GET on mount is a read-only cache check; it must never enqueue a job.
- A cached completed analysis renders without the request button; a missing/failed one shows the button and the reason.

---

## Accessibility and responsive

- Check 1440×900 and 375×812 at minimum. No horizontal scroll at 375 px.
- Global `:focus-visible` is intentional; do not remove it. Move focus to the back button when opening game details.
- Accessible names are part of the contract: e2e specs select buttons by name. Renaming one is a test change, not a free edit.
- Tables need headers; charts need a text or table alternative when the data matters.
- `prefers-reduced-motion` must keep the UI usable.

---

## Verification before handing over

```bash
cd frontend
npm run typecheck
npm run lint
npm run format:check
npm test
npm run build      # never while npm run dev is running on the same checkout
npx playwright test
```

Then open the surface at 1440×900 and 375×812 in **both** themes and describe what you saw. For a board change: play a move, undo, redo, toggle analysis off, and confirm no engine request is made. For a game-details change: confirm the analysis button is absent after a cached run and present when the analysis is missing.

Never report a viewport or theme you did not open.

---

## Traps that actually happened

1. **`getByRole('button', { name: /Back/i })` matched two buttons** after adding `◀ Back` to the game board. Use exact names (`Back to games`) or scope the selector.
2. **`getByText('Nf3')` became ambiguous** once both the board and the analysis list showed moves. Use `getAllByText` or scope to a region.
3. **A stale Docker image made a new button look missing.** Rebuild the stack before trusting a browser failure.
4. **`getByText(/accuracy/i)` matched explanatory copy**, not the result. Assert the concrete labels or values.
5. **A hard-coded colour passes typecheck, lint and build.** Only opening both themes catches it.
6. **Tailwind arbitrary values with operators need `_` for spaces**: `calc(100vh_-_7rem)`, never `calc(100vh-7rem)`. An invalid declaration is dropped silently.
7. **Hiding the evaluation card is not the same as disabling analysis.** Guard the request, not just the render.

---

## Hard rules

- Never show unknown data as `0`.
- Never auto-start engine analysis; only a user click may enqueue it.
- Never call the engine while the analysis toggle is off.
- Never hard-code a colour the light theme must override; use tokens.
- Never ship a state you did not open (theme, viewport, loading, empty, error).
- Never use `any`; keep `types/api.ts` in sync with the backend schema.
- Never replace the board's real buttons with non-interactive elements.
- Never rename an accessible name without checking the e2e specs that select it.
