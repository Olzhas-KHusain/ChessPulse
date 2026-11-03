import { test, expect } from '@playwright/test';

/** Cross-game form report (GitHub issue #5: e2e-test). */
const username = process.env.E2E_USERNAME ?? 'hikaru';

test('form report aggregates the period and queues remaining analyses', async ({ page }) => {
  test.setTimeout(300_000);

  await page.goto('/');
  const input = page.getByPlaceholder('e.g. hikaru');
  await input.fill(username);
  await page.getByRole('button', { name: /Analyze/ }).click();
  await expect(page.getByRole('tab', { name: 'Overview', selected: true })).toHaveCount(1, {
    timeout: 60_000,
  });

  await page.getByRole('tab', { name: 'Form report' }).click();

  // Header: N of M eligible games analysed.
  await expect(page.getByText(/\d+ of \d+ eligible games analysed/)).toBeVisible({
    timeout: 60_000,
  });

  // Queue analyses for the remaining games (worker drains asynchronously).
  const queueAll = page.getByRole('button', { name: /Analyze \d+ remaining/ });
  if (await queueAll.isVisible()) {
    await queueAll.click();
    await expect(page.getByText(/in the queue/)).toBeVisible({ timeout: 30_000 });
  }

  // Either the leak card, or the explicit still-empty notice, is rendered.
  await expect(page.getByText(/Main leak|No game has been analysed yet/).first()).toBeVisible({
    timeout: 240_000,
  });
});
