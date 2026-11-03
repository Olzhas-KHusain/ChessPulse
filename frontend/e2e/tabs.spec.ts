import { test, expect } from '@playwright/test';

/** Tabs: rating history, openings, opponents (GitHub issue #2: e2e-test). */
const username = process.env.E2E_USERNAME ?? 'hikaru';

test('tabs load independently with their data', async ({ page }) => {
  await page.goto('/');
  const input = page.getByPlaceholder('e.g. hikaru');
  await input.fill(username);
  await page.getByRole('button', { name: /Analyze/ }).click();
  await expect(page.getByRole('tab', { name: 'Overview', selected: true })).toHaveCount(1, {
    timeout: 60_000,
  });

  // Rating history: chart or at least the latest-rating headline renders.
  await page.getByRole('tab', { name: 'Rating history' }).click();
  await expect(page.getByText(/Latest/)).toBeVisible({ timeout: 30_000 });

  // Openings: a table with game counts renders.
  await page.getByRole('tab', { name: 'Openings' }).click();
  await expect(page.getByRole('table').first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/games/i).first()).toBeVisible();

  // Opponents: a table of opponents renders.
  await page.getByRole('tab', { name: 'Opponents' }).click();
  await expect(page.getByRole('table').first()).toBeVisible({ timeout: 30_000 });

  // Each tab keeps its own state after switching.
  await page.getByRole('tab', { name: 'Rating history' }).click();
  await expect(page.getByText(/Latest/)).toBeVisible();
});
