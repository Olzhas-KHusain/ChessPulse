import { test, expect } from '@playwright/test';

/**
 * Engine analysis per game (GitHub issue #4: e2e-test).
 *
 * Uses the API-backed UI: request Stockfish once, then confirm the cached
 * result renders without a new job. Requires the compose `worker` service.
 */
const username = process.env.E2E_USERNAME ?? 'olzhaswlk';

test('request, complete and cache an engine analysis', async ({ page }) => {
  test.setTimeout(300_000); // Stockfish depth-12 over a full game takes a while.

  await page.goto('/');
  const input = page.getByPlaceholder('e.g. hikaru');
  await input.fill(username);
  await page.getByRole('button', { name: /Analyze/ }).click();
  await expect(page.getByRole('tab', { name: 'Overview', selected: true })).toHaveCount(1, {
    timeout: 60_000,
  });

  await page.getByRole('tab', { name: 'Games' }).click();
  await page
    .getByRole('button', { name: /^Details of the game against / })
    .first()
    .click();

  // First request: enqueue and wait until the worker finishes the job.
  const analyze = page.getByRole('button', { name: 'Analyze with Stockfish' });
  await analyze.click({ timeout: 30_000 }).catch(() => {
    /* already analyzed in a previous run — fine, cached path tested below */
  });

  const ready = page.getByText(/Your accuracy|Opponent accuracy/).first();
  await expect(ready).toBeVisible({ timeout: 240_000 });
  await expect(page.getByText(/centipawn loss|ACPL/i).first()).toBeVisible({ timeout: 30_000 });

  // The viewport app keeps no route persistently (no client router): after a
  // reload it returns to the search landing. The cached-analysis path is
  // verified by navigating back to the list and reopening the same game.
  await page.getByRole('button', { name: /Back to games/ }).click();
  await expect(
    page.getByRole('button', { name: /^Details of the game against / }).first(),
  ).toBeVisible({ timeout: 30_000 });
  await page
    .getByRole('button', { name: /^Details of the game against / })
    .first()
    .click();

  // Comes back from the cache: result without a new job request.
  // The "Analyze with Stockfish" button must be gone: a cached completed
  // analysis hides the request button.
  await expect(page.getByRole('button', { name: 'Analyze with Stockfish' })).toHaveCount(0);
});
