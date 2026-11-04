# Frontend dashboard

Status: implemented (Issue 9). Code: `frontend/src/`.

## Structure

| Path | Role |
| ---- | ---- |
| `types/api.ts` | Types mirroring the backend schemas (`docs/specs/api-*.md`) |
| `services/chesspulseApi.ts` | The only module calling `fetch`; maps the error envelope to `ApiError` (`status`, `code`, `retryAfterSeconds`); network failure → `NETWORK_ERROR` |
| `hooks/useApi.ts` | Loading / success / error state with request cancellation (`AbortController`) |
| `components/StateViews.tsx` | Loading, error, empty views; `DataStatusBanner` for stale/partial data |
| `features/player` | Search form (validation mirrors the backend rule), scope selector (`time_class` + `days`) and dashboard with tabs |
| `features/overview`, `rating-history`, `openings`, `games` | Section views; every request carries the selected scope |
| `features/analysis` | Opt-in Stockfish review of one game: request, poll, accuracy cards, key moments |
| `features/board` | Free board: piece editor, legal-move play, engine evaluation and move classification |
| `features/theme` | Dark/light toggle persisted in `localStorage` (`chesspulse-theme`) |
| `utils/format.ts` | Formatting; `null` → `—` with screen-reader text "not available" |

No router library: the header switches between `Analytics` and `Free board`, and the
dashboard uses an accessible tab list (arrow keys, Home/End). The overview is requested
first (it refreshes the server cache); other tabs load only when opened, so they reuse
the refreshed dataset instead of racing it. The selected player and scope are preserved
when switching views.

## Scope

`ScopeSelect` exposes `time_class` (`rapid`, `blitz`, `bullet`, `daily`, `all`) and
`days` (7/30/90/180/365). `DEFAULT_SCOPE` is Rapid/30 days, matching the pre-scaling
API. Changing either value resets every panel to its loading state and reissues the
requests; no panel recomputes metrics client-side.

## Free board

The editor stores an 8×8 piece grid, so intermediate setups (for example one king) are
allowed; the FEN and castling rights are derived from the placement, and en passant is
preserved from a server position. Legal moves and check detection come from `chess.js`
in the browser; the backend remains authoritative for evaluation, centipawn loss and
classification. Every request goes to `/api/v1/board/evaluate` or `/api/v1/board/move`.

## Theme

The default is dark. `html[data-theme='light']` overrides the CSS tokens, so every
component follows without per-component light variants. An inline script in
`index.html` applies the saved theme before first paint to avoid a flash; the toggle in
the header updates `data-theme`, the `theme-color` meta tag and `localStorage`.

## Data honesty rules

- `null` values render as `—` (+ "not available" for screen readers), never `0`.
- Win rate is displayed as returned by the API (2 decimals); the UI never recomputes it.
- Stale data: amber banner with the last successful update and the reason code.
  Partial data: banner "results may be incomplete"; streak caveat shown when the API
  sets `streak_may_be_incomplete`.
- Rating chart is rendered only with at least one observation; otherwise an empty
  state. One point per game, no interpolation; a table alternative is provided.
- Unknown openings are labelled "Unknown opening"; sample sizes are always visible.
- Outcomes are shown as text, not by colour alone.
- Engine numbers are labelled "mean move accuracy" and come only from the stored analysis
  payload; the panel names the engine, version and depth, and states that labels use fixed
  centipawn-loss thresholds and that accuracy is not a rating estimate.
- Each tab handles its own errors, so one failing section does not hide the others.

## Dependency

`recharts` must be added to `frontend/package.json` (Issue 1 deliberately did not add
it). Tests use Vitest + React Testing Library with the `jsdom` environment from Issue 1.
