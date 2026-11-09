import { expect, test } from '@playwright/test';

test.beforeEach(async ({ request }) => {
  const response = await request.post('/api/demo/reset', { data: {} });
  expect(response.ok()).toBeTruthy();
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
  // Hold the initial agenda poll (fetched before the save) so it is still in flight when the user saves.
  let release: () => void = () => {};
  const gate = new Promise<void>(resolve => { release = resolve; });
  let held = false;
  await page.route('**/api/agenda', async route => {
    if (route.request().method() === 'GET' && !held) {
      held = true;
      const response = await route.fetch(); // snapshot taken before the mutation
      await gate;
      await route.fulfill({ response });
    } else {
      await route.continue();
    }
  });
  await page.goto('/');
  await expect.poll(() => held).toBeTruthy();
  // Meta/sessions are loaded by the later refresh; the save button needs the session list.
  const save = page.getByRole('button', { name: "Save Inside Cilium's Datapath", exact: true });
  const saveResponse = page.waitForResponse(r => r.url().endsWith('/api/agenda') && r.request().method() === 'POST');
  // Search results come from /api/search, which is independent of the held poll once meta is ready.
  await expect(save).toBeVisible({ timeout: 30000 }).catch(() => undefined);
  if (!(await save.isVisible())) {
    release();
    await expect(save).toBeVisible();
  }
  await save.click();
  await saveResponse;
  release(); // the stale pre-mutation poll completes after the mutation succeeded
  await expect(page.getByRole('button', { name: "Remove Inside Cilium's Datapath", exact: true })).toBeVisible();
  await expect(page.getByText('Saving your change…', { exact: true })).toHaveCount(0);
});
