import { test, expect } from '@playwright/test';

/** Games list, pagination and details (GitHub issue #3: e2e-test). */
const username = process.env.E2E_USERNAME ?? 'hikaru';

test('games list, pagination and details', async ({ page }) => {
  await page.goto('/');
  const input = page.getByPlaceholder('e.g. hikaru');
  await input.fill(username);
  await page.getByRole('button', { name: /Analyze/ }).click();
  await expect(page.getByRole('tab', { name: 'Overview', selected: true })).toHaveCount(1, {
    timeout: 60_000,
  });

  await page.getByRole('tab', { name: 'Games' }).click();
  const detailsButtons = page.getByRole('button', { name: /^Details of the game against / });
  await expect(detailsButtons.first()).toBeVisible({ timeout: 30_000 });
  const firstOpponent = (await detailsButtons.first().getAttribute('aria-label')) ?? '';

  // Pagination: the next page shows different games (keyset cursor).
  await page.getByRole('navigation', { name: 'Game list pages' }).getByRole('button').nth(1).click();
  await expect(detailsButtons.first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/Page \d+/)).toBeVisible();

  // Back to page 1 and open the details of the first game.
  await page.getByRole('navigation', { name: 'Game list pages' }).getByRole('button').nth(0).click();
  await expect(detailsButtons.first()).toBeVisible({ timeout: 30_000 });
  await detailsButtons.first().click();

  // Details view: back navigation and the game header render.
  await expect(page.getByRole('heading', { name: /vs|against|Game i/i })).toBeVisible({
    timeout: 30_000,
  });
  await page.getByRole('button', { name: /Back/i }).click();
  await expect(page.getByRole('button', { name: firstOpponent })).toBeVisible({ timeout: 30_000 });
});
