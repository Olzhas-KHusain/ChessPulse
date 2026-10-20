# process.md — ChessPulse Spec-Driven Development Workflow

## 1. Purpose

This document defines how ChessPulse features move from an idea to a tested implementation.

The specification is the source of truth. Code, tests, and documentation must remain consistent with it.

## 2. Sources of Truth

Use this priority order:

1. Explicitly approved product decisions
2. `spec.md` — product and technical specification
3. The current GitHub Issue — scope and acceptance criteria
4. `AGENT.md` — engineering rules
5. `roles/pm.md` — product-management responsibilities
6. Existing implementation and tests, when consistent with the approved specification

If two sources conflict, do not silently choose one. Identify the conflict and ask for clarification or propose a documented resolution.

External provider documentation determines the actual supported API behavior. If it contradicts an assumption in `spec.md`, update the assumption before building on it.

## 3. Development Lifecycle

### Phase 1 — Discover

Before implementation:

- Read the issue and its acceptance criteria.
- Inspect relevant code, tests, and dependencies.
- Identify the affected frontend, backend, database, and provider modules.
- Check whether the issue duplicates existing functionality.
- Verify external API assumptions against current official documentation.
- Identify data integrity, security, performance, and migration risks.

Deliverable: a short implementation plan.

### Phase 2 — Specify

Every feature must define:

- Problem and user value
- In-scope behavior
- Out-of-scope behavior
- Inputs and outputs
- Business rules and edge cases
- API or database changes
- Error and partial-data behavior
- Acceptance criteria
- Test strategy
- Dependencies and risks

Acceptance criteria should be observable and testable.

Avoid vague statements such as "works correctly" or "has a good UI".

### Phase 3 — Design

Before substantial coding:

- Choose the smallest architecture change that satisfies the requirements.
- Define API request and response schemas.
- Define persistence and cache implications.
- Identify migration and backward-compatibility requirements.
- Decide where validation and error handling belong.
- Record important decisions in a short Architecture Decision Record (ADR) when the choice has lasting consequences.

Do not create unnecessary abstractions or introduce distributed architecture for an MVP requirement.

### Phase 4 — Implement

Implement in small, reviewable steps.

Preferred order for a feature that spans the stack:

1. Domain rules and data types
2. Database model and migration, if required
3. Provider or repository logic
4. Service/business logic
5. API schema and endpoint
6. Frontend API integration
7. UI states and presentation
8. Documentation and observability

This order may change when a vertical slice can be tested earlier, but business rules must remain independently testable.

### Phase 5 — Verify

Run the narrowest relevant tests first.

Then run:
- Backend linting and type checks, if configured
- Backend unit and integration tests
- Frontend linting and type checks
- Frontend unit/component tests
- Build checks
- Relevant migration checks

Do not claim a test passed unless it was actually executed and passed.

Do not make live Chess.com access a requirement for ordinary automated tests.

### Phase 6 — Review

Review the diff for:

- Scope creep
- Incorrect metric formulas
- Confusion between zero and unknown
- Incorrect handling of stale cache
- Leaked secrets or unsafe errors
- Duplicate network requests
- Missing tests
- API contract mismatches
- Accessibility and responsive-layout regressions
- Unnecessary dependencies
- Unjustified database or architectural complexity

### Phase 7 — Deliver

The implementation report must include:

- Summary
- Files and modules changed
- Acceptance criteria completed
- Tests actually run and results
- Migration or configuration instructions
- Known limitations
- Unresolved questions

A feature is not done merely because its code has been written.

## 4. GitHub Issue Lifecycle

Recommended labels:

- `type:feature`
- `type:bug`
- `type:chore`
- `type:docs`
- `area:frontend`
- `area:backend`
- `area:database`
- `area:provider`
- `priority:P0`
- `priority:P1`
- `priority:P2`
- `status:blocked`

Issue states:

1. Draft
2. Ready for refinement
3. Ready for development
4. In progress
5. In review
6. Done
7. Blocked

Only issues with sufficiently clear acceptance criteria should enter Ready for development.

## 5. Definition of Ready

An issue is ready when:

- The problem and user value are clear.
- Scope is bounded.
- Acceptance criteria are testable.
- Relevant dependencies are identified.
- External API assumptions are verified or explicitly marked as unresolved.
- Important edge cases are described.
- The issue can be implemented without guessing at a product decision.

## 6. Definition of Done

An issue is done when:

- All acceptance criteria pass.
- Tests cover the new behavior and relevant regressions.
- Required checks pass.
- Documentation and API contracts are updated.
- Error, empty, and partial-data states are handled.
- The diff has been reviewed.
- No unresolved critical issue remains.
- Any remaining limitation is documented.

## 7. Test-First Expectations

Write tests before or alongside implementation when practical.

For analytics, prefer small deterministic examples:
- No eligible games
- One win
- One loss
- One draw
- Mixed results
- Multiple games with equal timestamps
- Games outside the 30-day window
- Non-Rapid games
- Incomplete or malformed records
- Missing opponent or opening data

For caching, test:
- Cache hit
- Cache miss
- Expired cache
- Successful refresh
- Failed refresh with stale data
- Failed refresh without cached data
- Provider rate limiting
- Concurrent refresh attempts

## 8. Change Management

Changes that require explicit product approval:

- Expanding the MVP beyond Rapid games
- Changing the 30-day analysis window
- Adding user accounts or authentication
- Adding engine-based analytics
- Introducing paid services or costly infrastructure
- Changing the public API in a breaking way
- Collecting additional personal data
- Changing the meaning of an existing metric

Small implementation details can be decided by the agent if they do not alter product behavior, security, cost, or public contracts.

## 9. AI-Native Development Rules

AI agents may:
- Explore the repository
- Propose designs
- Generate code and tests
- Find inconsistencies
- Suggest issue breakdowns
- Update documentation alongside code

AI agents must not:
- Invent external API capabilities
- Mark unrun tests as passing
- silently change requirements
- fabricate analytics when data is missing
- expand scope without approval
- delete unrelated user work
- expose secrets in logs or reports
- consider a task complete merely because a code-generation step succeeded

## 10. Recommended Delivery Order

1. Repository setup and development environment
2. Database and migration baseline
3. Chess.com provider integration
4. Game normalization and filtering
5. Analytics service
6. API endpoints
7. Frontend search and overview
8. Rating history, openings, and opponents
9. Game list and game details
10. Reliability, caching, accessibility, and release checks

The GitHub Issues define the concrete scope and dependencies for each stage.
