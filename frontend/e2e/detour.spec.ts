import { expect, test } from '@playwright/test';
import { resetDemo } from './reset-demo';

test.beforeEach(async ({ request }) => {
  await resetDemo(request);
});

test('attendee recovers from a room filling up and accepts a replacement', async ({ page, context }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /A change of plans/ })).toBeVisible();
  await page.getByRole('searchbox', { name: 'Search sessions' }).fill('Kubernetes networking');
  await page.getByRole('button', { name: 'Find my sessions' }).click();
  await expect(page.getByRole('button', { name: "Save Inside Cilium's Datapath", exact: true })).toBeVisible();
  await page.getByRole('button', { name: "Save Inside Cilium's Datapath", exact: true }).click();
  await expect(page.getByRole('button', { name: "Remove Inside Cilium's Datapath", exact: true })).toBeVisible();
  // Independent organizer page shares persisted program state; attendee gets the update by polling.
  const organizer = await context.newPage();
  await organizer.goto('/');
  await organizer.getByRole('button', { name: 'Organizer', exact: true }).click();
  await organizer.getByRole('button', { name: "Mark Inside Cilium's Datapath full", exact: true }).click();
  await expect(organizer.getByText('Room marked full for this session.', { exact: true })).toBeVisible();
  await page.bringToFront();
  await expect(page.getByRole('button', { name: 'Find my detour', exact: true })).toBeVisible({ timeout: 20000 });
  await page.getByRole('button', { name: 'Find my detour', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Replacement recommendations' }).getByText('PLAN CHANGED')).toBeVisible();
  await page.getByRole('button', { name: 'Take this detour' }).first().click();
  await expect(page.getByText('Detour accepted. Your agenda is up to date.', { exact: true })).toBeVisible();
  await expect(page.getByText('You’re on a good path.', { exact: true })).toBeVisible();
  const agenda = await context.request.get('/api/agenda');
  const data = await agenda.json();
  expect(data.agenda.session_ids).toHaveLength(1);
  expect(data.agenda.session_ids).not.toContain('session-01');
  expect(data.agenda.accepted_alternatives).toHaveLength(1);
});

test('responsive layout, time-zone control and keyboard search work', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('button', { name: "Save Inside Cilium's Datapath", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.getByRole('combobox', { name: 'Display time zone' }).selectOption('UTC');
  await expect(page.getByTestId('session-session-01')).toContainText('4:00 PM');
  await page.getByRole('combobox', { name: 'Search method' }).selectOption('keyword');
  await page.getByRole('searchbox').fill('zxqvnonexistent');
  await page.getByRole('searchbox').press('Enter');
  await expect(page.getByText('A different path awaits.', { exact: true })).toBeVisible();
});

test('mutation during an in-flight poll still refreshes with the saved state', async ({ page }) => {
  await page.goto('/');
  const save = page.getByRole('button', { name: "Save Inside Cilium's Datapath", exact: true });
  await expect(save).toBeVisible();
  // Hold the next agenda poll so it is still in flight when the user saves.
  let release: () => void = () => {};
  const gate = new Promise<void>(resolve => { release = resolve; });
  let held = false;
  await page.route('**/api/agenda', async route => {
    if (route.request().method() === 'GET' && !held) {
      held = true;
      const response = await route.fetch(); // pre-mutation snapshot
      await gate;
      await route.fulfill({ response });
    } else {
      await route.continue();
    }
  });
  await expect.poll(() => held, { timeout: 15000 }).toBeTruthy();
  await save.click();
  release(); // stale poll completes after the mutation; a forced refresh must still follow
  await expect(page.getByRole('button', { name: "Remove Inside Cilium's Datapath", exact: true })).toBeVisible();
  await expect(page.getByText('Saving your change…', { exact: true })).toHaveCount(0);
});
