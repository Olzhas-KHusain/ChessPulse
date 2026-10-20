# AGENT.md — ChessPulse Engineering Rules

## 1. Project Overview

ChessPulse is a web application for analyzing a Chess.com player's Rapid games from the most recent rolling 30-day period.

The application provides statistical insights into game outcomes, rating observations, openings, opponents, winning streaks, and individual games.

The MVP must work without user registration or authentication.

### Product principles

- Correctness over quantity of metrics.
- Transparent data limitations.
- Partial results are better than total failure when safe.
- Unknown data must never be represented as zero.
- Cached data must be identified as cached or stale when appropriate.
- Never fabricate chess statistics, ratings, game records, or provider responses.
- Keep the MVP small enough to implement and test incrementally.

## 2. Technology Stack

### Frontend
- React
- TypeScript with strict mode
- Vite
- React Router, if multiple routes are needed
- Tailwind CSS
- Recharts for charts
- Vitest
- React Testing Library

### Backend
- Python 3.12+; use the version pinned in the project configuration
- FastAPI
- Pydantic v2
- HTTPX for outbound HTTP requests
- SQLAlchemy 2.x
- Alembic
- PostgreSQL
- python-chess for PGN parsing and chess-specific utilities
- pytest and pytest-asyncio where appropriate

### Development and deployment
- Git
- Docker and Docker Compose for local services
- Environment variables for configuration
- Ruff for Python linting and formatting
- mypy or an equivalent type-checking tool where practical
- ESLint and Prettier for frontend consistency

Do not introduce a new framework, database, queue, cache server, or dependency without a concrete requirement and documented justification.

## 3. Architecture

Use a modular monolith. Do not create microservices for the MVP.

Backend responsibilities should be separated into:
- API routers: HTTP routing and request/response handling
- Schemas: request and response validation
- Services: business rules and analytics
- Providers: Chess.com API integration
- Repositories: database access
- Models: SQLAlchemy entities
- Cache: freshness, expiration, and refresh coordination
- Configuration: environment-based settings

Suggested structure:

    backend/
      app/
        main.py
        api/
          v1/
            routers/
        core/
          config.py
          errors.py
        models/
        schemas/
        repositories/
        services/
        providers/
          chess_com.py
        analytics/
        cache/
        db/
      migrations/
      tests/
      pyproject.toml

    frontend/
      src/
        app/
        components/
        features/
          player/
          overview/
          rating-history/
          openings/
          opponents/
          games/
        services/
        hooks/
        types/
        utils/
      package.json

    docs/
      specs/
    docker-compose.yml
    .env.example
    README.md

Adapt this layout to existing repository conventions instead of duplicating an established structure.

## 4. Mandatory Engineering Rules

1. Read the relevant specification, existing code, and tests before implementing a feature.
2. Implement the smallest coherent change that satisfies the issue.
3. Do not rewrite unrelated modules or change public API contracts without justification.
4. Use type hints for Python functions and explicit types for TypeScript data structures.
5. Validate external data at system boundaries.
6. Never expose stack traces, SQL, secrets, or internal exception messages to clients.
7. Keep business logic out of API routers and React presentation components.
8. Use dependency injection for database sessions and external providers where appropriate.
9. Use parameterized database queries through SQLAlchemy.
10. Avoid N+1 database queries and unbounded database or HTTP requests.
11. Do not add dependencies solely for convenience when the standard library or current stack is sufficient.
12. Do not commit secrets, local database files, virtual environments, build output, or personal data.
13. Never use real provider availability as the only basis for automated tests.
14. Add or update tests for every meaningful behavior change.
15. Update API schemas and documentation whenever the API contract changes.

## 5. Data and Analytics Rules

### Analysis window
- Use a rolling window of the most recent 30 days.
- Use UTC for internal timestamps and comparisons.
- Document whether the lower and upper time boundaries are inclusive.
- Include only completed Rapid games within the selected period.
- Do not silently substitute Blitz, Bullet, Daily, or other time controls.

### Results
- Classify each player's result as win, loss, or draw using verified game data.
- Calculate win rate as:

      wins / (wins + losses + draws) * 100

- If there are no eligible completed games, return a null win rate and zero eligible games. Do not divide by zero.
- A streak must be calculated in chronological order using an explicitly documented convention. A draw or loss breaks a winning streak.
- Do not confuse the player's current Chess.com rating with a rating reconstructed from game records.

### Missing or unreliable data
- Distinguish missing data from a measured zero.
- Do not fabricate opening names, opponent identifiers, ratings, timestamps, or results.
- Mark unavailable or incomplete sections explicitly.
- Malformed individual games must not invalidate unrelated valid games.
- Exclude records only with a documented reason; report partial-data status where it materially affects results.

### Chess.com integration
- Use official, publicly documented interfaces where available.
- Verify the current API contract before relying on particular fields or endpoint behavior.
- Respect upstream rate limits, cache instructions, attribution requirements, and applicable terms.
- Set a descriptive User-Agent if required by provider documentation.
- Treat all upstream data as untrusted input.
- Do not scrape private data, bypass access controls, or invent undocumented API endpoints.
- Keep provider-specific parsing inside the provider integration layer.

### Engine-dependent metrics
The MVP does not calculate engine-based accuracy, Brilliant moves, blunders, centipawn loss, or engine-estimated Elo.

These features require a separately scoped engine-analysis stage, likely involving Stockfish and additional computational controls.

Do not display placeholders that look like real calculated values.

## 6. Caching and Failure Handling

- Cache validated provider data and reusable analytics.
- Make cache lifetime configurable; 12 hours is an initial default proposal, not a provider guarantee.
- Follow upstream cache directives and rate-limit guidance when applicable.
- Store fetch time, source, freshness, and refresh outcome.
- Never replace the last known good cache with an empty result caused by a timeout, rate limit, or provider outage.
- Use bounded timeouts and bounded retries with backoff.
- Respect Retry-After when provided.
- Avoid duplicate concurrent refreshes for the same player and resource where practical.
- If stale data is served, mark it as stale and expose its last successful update time.
- Do not claim data is fresh merely because the API request succeeded.

## 7. API Rules

- Prefix versioned endpoints with `/api/v1`.
- Use consistent JSON response schemas.
- Validate path parameters, query parameters, and external data.
- Use appropriate HTTP status codes.
- Return safe, actionable error messages.
- Include machine-readable error codes.
- Keep HTTP concerns separate from analytics logic.
- Avoid breaking changes without an explicit specification update.

Planned endpoints:

- `GET /api/v1/players/{username}`
- `GET /api/v1/players/{username}/overview`
- `GET /api/v1/players/{username}/rating-history`
- `GET /api/v1/players/{username}/openings`
- `GET /api/v1/players/{username}/opponents`
- `GET /api/v1/players/{username}/games`
- `GET /api/v1/players/{username}/games/{game_id}`

The detailed contract is defined in `spec.md`.

## 8. Frontend Rules

- Use strict TypeScript; avoid `any`.
- Keep API calls in a dedicated service layer.
- Define frontend types that match documented backend response schemas.
- Represent loading, empty, partial, stale, error, and success states explicitly.
- Do not turn missing values into zero or display them as real data.
- Do not render a chart when its data is invalid or absent.
- Ensure forms and controls are keyboard-accessible.
- Provide clear validation for usernames.
- Avoid redundant requests and handle request cancellation where appropriate.
- Make the layout usable on mobile and desktop.
- Keep charts understandable with labels, units, tooltips, and empty states.

## 9. Testing Requirements

Backend:
- Unit-test analytics formulas and edge cases.
- Test provider parsing with recorded fixtures or mocked responses.
- Test cache expiration, stale fallback, and provider failures.
- Test API response schemas and status codes.
- Test database constraints and repository behavior.

Frontend:
- Test API service behavior.
- Test loading, empty, stale, partial, and error states.
- Test important metric rendering and formatting.
- Test username validation and game-list interactions.

Integration:
- Test critical API-to-database flows using a test database.
- Use mocks or fixtures for Chess.com responses.
- Never require a live Chess.com account or live provider uptime for the standard test suite.

## 10. Definition of Done

An issue is complete only when:
- Its acceptance criteria are met.
- Relevant tests pass.
- New behavior is covered by tests.
- Error and empty states are handled.
- Types and API contracts are consistent.
- Documentation is updated where necessary.
- No secrets or unrelated generated files are committed.
- The implementation does not contradict `spec.md`.

## 11. AI Agent Workflow

For each issue:

1. Read `AGENT.md`, `process.md`, `spec.md`, and the issue.
2. Inspect the repository and identify affected modules.
3. State the intended approach and assumptions.
4. Implement one vertical slice at a time.
5. Run focused tests, then relevant full checks.
6. Review the diff for unintended changes.
7. Update documentation and report:
   - What changed
   - Files changed
   - Tests executed and their results
   - Known limitations
   - Any specification decisions requiring human approval

If requirements conflict or the provider's actual behavior differs from the specification, stop at the affected boundary, explain the conflict, and request a decision instead of silently inventing a rule.
