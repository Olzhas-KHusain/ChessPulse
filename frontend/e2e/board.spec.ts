import { test, expect } from '@playwright/test';

/**
 * Free analysis board (GitHub issue: e2e-test).
 *
 * Runs against the real Stockfish service: evaluate the start position, play a
 * legal move and check the classification, then build an arbitrary position.
 */
test('evaluate a position, play a move and edit the board', async ({ page }) => {
  test.setTimeout(180_000);

  await page.goto('/');
  await page.getByRole('button', { name: 'Free board' }).click();
  await expect(
    page.getByRole('heading', { name: 'Set up any position. Analyse every move.' }),
  ).toBeVisible();

  // Evaluate the standard start position.
  await page.getByRole('button', { name: 'Evaluate position' }).click();
  await expect(page.getByRole('img', { name: /Evaluation bar/ })).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByText('Engine suggestion')).toBeVisible();
  await expect(page.getByText(/depth \d+/)).toBeVisible();

  // Play 1.e4 on the board; the engine classifies it and updates the FEN.
  await page.getByRole('button', { name: 'e2 white pawn' }).click();
  await page.getByRole('button', { name: 'e4' }).click();
  await expect(page.getByText('Best', { exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByLabel('Position FEN')).toHaveValue(/4P3/);
  await expect(page.getByRole('button', { name: 'e4 white pawn' })).toBeVisible();

  // Undo returns to the previous position.
  await page.getByRole('button', { name: 'Undo' }).click();
  await expect(page.getByLabel('Position FEN')).toHaveValue(/8\/8\/8\/8\/PPPPPPPP/);

  // Redo brings the move back.
  await page.getByRole('button', { name: 'Redo' }).click();
  await expect(page.getByLabel('Position FEN')).toHaveValue(/4P3/);
  await expect(page.getByText('Best', { exact: true })).toBeVisible();

  // Build a position from scratch: only a white king is invalid, both kings are fine.
  await page.getByRole('button', { name: 'Clear board' }).click();
  await expect(page.getByText('Editing', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'White king' }).click();
  await page.getByRole('button', { name: 'e1' }).click();
  await page.getByRole('button', { name: 'Play this position' }).click();
  await expect(page.getByRole('alert')).toContainText(/king/i);

  await page.getByRole('button', { name: 'Black king' }).click();
  await page.getByRole('button', { name: 'e8' }).click();
  await page.getByRole('button', { name: 'Play this position' }).click();
  await expect(page.getByText('Playing', { exact: true })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('turns engine analysis off and plays a move locally', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Free board' }).click();

  const toggle = page.getByRole('switch', { name: 'Engine analysis' });
  await expect(toggle).toHaveAttribute('aria-checked', 'true');
  await toggle.click();

  await expect(toggle).toHaveAttribute('aria-checked', 'false');
  await expect(page.getByRole('heading', { name: 'Analysis is off' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Evaluate position' })).toHaveCount(0);

  await page.getByRole('button', { name: 'd2 white pawn' }).click();
  await page.getByRole('button', { name: 'd4' }).click();

  await expect(page.getByLabel('Position FEN')).toHaveValue(/3P4/);
  await expect(page.getByText('Best', { exact: true })).toHaveCount(0);

  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-checked', 'true');
  await expect(page.getByRole('button', { name: 'Evaluate position' })).toBeVisible();
});
