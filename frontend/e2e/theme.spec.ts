import { test, expect } from '@playwright/test';

/** Dark/light theme toggle with persistence (GitHub issue: e2e-test). */
test('switches theme, applies it to the page and remembers the choice', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Switch to light theme' })).toBeVisible();

  const html = page.locator('html');
  await expect(html).toHaveAttribute('data-theme', 'dark');

  await page.getByRole('button', { name: 'Switch to light theme' }).click();
  await expect(html).toHaveAttribute('data-theme', 'light');
  await expect(page.getByRole('button', { name: 'Switch to dark theme' })).toBeVisible();

  // The boot script must apply the saved theme before the app renders.
  await page.reload();
  await expect(html).toHaveAttribute('data-theme', 'light');
  await expect(page.getByRole('button', { name: 'Switch to dark theme' })).toBeVisible();

  await page.getByRole('button', { name: 'Switch to dark theme' }).click();
  await expect(html).toHaveAttribute('data-theme', 'dark');
});
