import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test('attendee and organizer views have no automated WCAG AA violations', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.session-card').first()).toBeVisible();
  const attendee = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(attendee.violations).toEqual([]);
  await page.getByRole('button', { name: 'Organizer', exact: true }).click();
  await expect(page.getByRole('heading', { name: /Plans change/ })).toBeVisible();
  const organizer = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(organizer.violations).toEqual([]);
});
