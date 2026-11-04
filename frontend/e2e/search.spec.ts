import { test, expect } from '@playwright/test';

/**
 * Search & overview flow (GitHub issue #1: e2e-test).
 *
 * E2E_USERNAME selects the Chess.com player used for the happy path; any real
 * Rapid player works (defaults to hikaru).
 */
const username = process.env.E2E_USERNAME ?? 'olzhaswlk';

test('search, validation and overview metrics', async ({ page }) => {
  await page.goto('/');

  // Empty input is rejected client-side without any request.
  const input = page.getByPlaceholder('e.g. hikaru');
  await input.fill('');
  await page.getByRole('button', { name: /Analyze/ }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page).toHaveURL(/\/$/);

  // Too-long input is rejected by validation too.
  await input.fill('x'.repeat(65));
  await page.getByRole('button', { name: /Analyze/ }).click();
  await expect(page.getByRole('alert')).toBeVisible();

  // A nonexistent player gets an explanatory message.
  await input.fill(`no-such-player-${Date.now()}`);
  await page.getByRole('button', { name: /Analyze/ }).click();
  if (page.url().split('#')[0].includes('no-such-player')) {
    await expect(page.getByText('No Chess.com player with this username was found.')).toBeVisible({
      timeout: 30_000,
    });
  }

  // Real player: overview metrics render.
  await input.fill(username);
  await page.getByRole('button', { name: /Analyze/ }).click();
  await expect(page.getByRole('tab', { name: 'Overview' })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole('tab', { name: 'Overview', selected: true })).toHaveCount(1);
  await expect(page.getByText(/Current Rapid rating/)).toBeVisible();
  await expect(page.getByText(/games in the window|Win rate|Streak/i).first()).toBeVisible();
});
