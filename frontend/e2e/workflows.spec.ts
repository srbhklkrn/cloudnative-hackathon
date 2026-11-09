import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { resetDemo } from './reset-demo';

test.describe.configure({ timeout: 120000 });
let browserErrors: string[];

test.beforeEach(async ({ page, context, request }) => {
  browserErrors = [];
  page.on('pageerror', error => browserErrors.push(error.message));
  context.on('page', other => other.on('pageerror', error => browserErrors.push(error.message)));
  await resetDemo(request);
});
test.afterEach(() => expect(browserErrors, 'Uncaught browser errors').toEqual([]));

async function save(page: Page, title: string) {
  await page.getByRole('button', { name: `Save ${title}`, exact: true }).click();
  await expect(page.getByRole('button', { name: `Remove ${title}`, exact: true })).toBeEnabled();
}

async function audit(page: Page) {
  const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(result.violations.map(v => ({ id: v.id, targets: v.nodes.map(n => n.target) }))).toEqual([]);
}

test('organizer full/cancel/reopen controls and time/location editor validate changes', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Organizer', exact: true }).click();
  const title = "Inside Cilium's Datapath";
  const row = page.getByRole('row').filter({ hasText: title });
  await page.getByRole('button', { name: `Mark ${title} full`, exact: true }).click();
  await expect(row.locator('.availability')).toHaveText('Room full');
  await page.getByRole('button', { name: `Reopen ${title}`, exact: true }).click();
  await expect(row.locator('.availability')).toHaveText('Available');
  await page.getByRole('button', { name: `Cancel ${title}`, exact: true }).click();
  await expect(row.locator('.availability')).toHaveText('Canceled');
  await page.getByRole('button', { name: `Reopen ${title}`, exact: true }).click();
  await expect(row.locator('.availability')).toHaveText('Available');
  await page.getByRole('button', { name: `Edit ${title}`, exact: true }).click();
  const editor = row.locator('form');
  await editor.getByLabel('New end time').fill('08:00');
  await editor.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Invalid time interval');
  await expect(editor).toBeVisible();
  await expect(editor.getByLabel('New end time')).toHaveValue('08:00');
  await editor.getByLabel('New start time').fill('09:05');
  await editor.getByLabel('New end time').fill('09:50');
  await editor.getByLabel('Room', { exact: true }).fill('Annex');
  await editor.getByRole('combobox', { name: /^Building/ }).selectOption('Canyon');
  await audit(page);
  await editor.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(editor).toHaveCount(0);
  await expect(row).toContainText('9:05 AM');
  await expect(row).toContainText('9:50 AM');
  await expect(row).toContainText('Annex');
  await expect(row).toContainText('Canyon');
});

test('independent attendees keep separate agendas and recommendation interests', async ({ page, browser }) => {
  await page.goto('/');
  await save(page, "Inside Cilium's Datapath");
  await page.getByRole('button', { name: 'Networking', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Networking', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Networking', exact: true })).toHaveAttribute('aria-pressed', 'true');
  const otherContext = await browser.newContext();
  try {
    const other = await otherContext.newPage();
    await other.goto('/');
    await expect(other.locator('.session-card')).toHaveCount(30);
    await expect(other.locator('.timeline-item')).toHaveCount(0);
    await expect(other.getByRole('button', { name: 'Networking', exact: true })).toHaveAttribute('aria-pressed', 'false');
    await page.reload();
    await expect(page.locator('.timeline-item')).toHaveCount(1);
    await expect(page.getByRole('button', { name: 'Networking', exact: true })).toHaveAttribute('aria-pressed', 'true');
  } finally { await otherContext.close(); }
});

test('dismissed detours stay dismissed and impossible access needs explain no alternatives', async ({ page }) => {
  await page.goto('/');
  await save(page, "Inside Cilium's Datapath");
  await page.getByRole('button', { name: 'Organizer', exact: true }).click();
  await page.getByRole('button', { name: "Mark Inside Cilium's Datapath full", exact: true }).click();
  await expect(page.getByText('Room marked full for this session.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: /My agenda/ }).click();
  const region = page.getByRole('region', { name: 'Replacement recommendations' });
  const dismissed = await region.locator('.recommendation h3').first().innerText();
  await region.getByRole('button', { name: `Dismiss ${dismissed}`, exact: true }).click();
  await expect(region.getByRole('heading', { name: dismissed, exact: true })).toHaveCount(0);
  await page.reload();
  await page.getByRole('button', { name: /My agenda/ }).click();
  await expect(region.locator('.original-session')).toBeVisible();
  await expect(region.getByRole('heading', { name: dismissed, exact: true })).toHaveCount(0);
  await page.getByLabel('Quiet space', { exact: true }).click();
  await expect(page.getByLabel('Quiet space', { exact: true })).toBeEnabled();
  await page.getByLabel('Hearing loop', { exact: true }).click();
  await expect(region).toContainText('No compatible alternative is available');
  await expect(region.locator('.recommendation')).toHaveCount(0);
  await expect(page.locator('.timeline-item')).toHaveCount(1);
  await audit(page);
});

test('successive cancellations can be recovered without losing the other saved session', async ({ page }) => {
  await page.goto('/');
  await save(page, "Inside Cilium's Datapath");
  await save(page, 'Kernel Superpowers for Cluster Traffic');
  await page.getByRole('button', { name: 'Organizer', exact: true }).click();
  await page.getByRole('button', { name: "Cancel Inside Cilium's Datapath", exact: true }).click();
  await expect(page.getByText('Session canceled. Affected agendas will be checked.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: /My agenda/ }).click();
  const region = page.getByRole('region', { name: 'Replacement recommendations' });
  const replacement = await region.locator('.recommendation h3').first().innerText();
  await audit(page);
  await region.getByRole('button', { name: 'Take this detour', exact: true }).first().click();
  await expect(page.getByText('You’re on a good path.', { exact: true })).toBeVisible();
  await expect(page.locator('.timeline-item')).toHaveCount(2);
  await page.getByRole('button', { name: 'Organizer', exact: true }).click();
  await page.getByRole('button', { name: `Cancel ${replacement}`, exact: true }).click();
  await expect(page.getByRole('button', { name: `Reopen ${replacement}`, exact: true })).toBeVisible();
  await page.getByRole('button', { name: /My agenda/ }).click();
  await expect(region.locator('.original-session')).toContainText(replacement);
  await region.getByRole('button', { name: 'Take this detour', exact: true }).first().click();
  await expect(page.getByText('You’re on a good path.', { exact: true })).toBeVisible();
  await expect(page.locator('.timeline-item')).toHaveCount(2);
  await expect(page.locator('.timeline')).toContainText('Kernel Superpowers for Cluster Traffic');
  const agenda = await (await page.request.get('/api/agenda')).json();
  expect(agenda.agenda.accepted_alternatives).toHaveLength(2);
});

test('a recommendation canceled by another organizer disappears on the next poll', async ({ page, context }) => {
  await page.goto('/');
  await save(page, "Inside Cilium's Datapath");
  const organizer = await context.newPage();
  await organizer.goto('/');
  await organizer.getByRole('button', { name: 'Organizer', exact: true }).click();
  await organizer.getByRole('button', { name: "Cancel Inside Cilium's Datapath", exact: true }).click();
  await expect(organizer.getByText('Session canceled. Affected agendas will be checked.', { exact: true })).toBeVisible();
  await page.bringToFront();
  await page.getByRole('button', { name: 'Find my detour', exact: true }).click();
  const region = page.getByRole('region', { name: 'Replacement recommendations' });
  const title = await region.locator('.recommendation h3').first().innerText();
  await organizer.getByRole('button', { name: `Cancel ${title}`, exact: true }).click();
  await expect(organizer.getByRole('button', { name: `Reopen ${title}`, exact: true })).toBeVisible();
  await page.bringToFront();
  await expect(region.getByRole('heading', { name: title, exact: true })).toHaveCount(0);
  await expect(region.locator('.recommendation')).not.toHaveCount(0);
});

test('reset confirmation can be canceled and accepted, clearing demo changes and agendas', async ({ page }) => {
  await page.goto('/');
  await save(page, "Inside Cilium's Datapath");
  await page.getByRole('button', { name: 'Organizer', exact: true }).click();
  await page.getByRole('button', { name: "Mark Inside Cilium's Datapath full", exact: true }).click();
  await expect(page.getByText('Room marked full for this session.', { exact: true })).toBeVisible();
  page.once('dialog', dialog => dialog.dismiss());
  await page.getByRole('button', { name: 'Reset demo', exact: true }).click();
  await expect(page.getByRole('button', { name: "Reopen Inside Cilium's Datapath", exact: true })).toBeVisible();
  expect((await (await page.request.get('/api/agenda')).json()).agenda.session_ids).toHaveLength(1);
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Reset demo', exact: true }).click();
  await expect(page.getByText('Demo program and agendas reset.', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: "Mark Inside Cilium's Datapath full", exact: true })).toBeVisible();
  await expect(page.locator('.timeline-item')).toHaveCount(0);
  const program = await (await page.request.get('/api/sessions')).json();
  expect(program.sessions).toHaveLength(30);
  expect(program.disruptions).toEqual([]);
});

test('mobile preferences, agenda, organizer room moves and access verification work together', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.locator('.session-card')).toHaveCount(30);
  await page.getByRole('button', { name: 'Interests & accessibility', exact: true }).click();
  await page.getByLabel('Live captions', { exact: true }).click();
  await expect(page.locator('.session-card')).toHaveCount(18);
  await save(page, "Inside Cilium's Datapath");
  await page.getByRole('button', { name: /My agenda/ }).click();
  await expect(page.locator('.timeline-item')).toHaveCount(1);
  await audit(page);
  await page.getByRole('button', { name: 'Organizer', exact: true }).click();
  await page.getByRole('button', { name: "Edit Inside Cilium's Datapath", exact: true }).click();
  const editor = page.locator('.session-editor');
  await editor.getByLabel('Room', { exact: true }).fill('Quiet Annex');
  await editor.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(editor).toHaveCount(0);
  await page.getByRole('button', { name: 'Discover sessions', exact: true }).click();
  await expect(page.getByTestId('session-session-01')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Find my detour', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('real Jina semantic search finds relevant talks that keyword search misses', async ({ page, request }) => {
  const meta = await (await request.get('/api/meta')).json();
  test.skip(!meta.semantic_search, 'Semantic retrieval requires the isolated Elasticsearch target');
  await page.goto('/');
  await page.getByRole('combobox', { name: 'Search method', exact: true }).selectOption('keyword');
  await page.getByRole('searchbox').fill('sniffing interpod conversations');
  await page.getByRole('searchbox').press('Enter');
  await expect(page.getByText('A different path awaits.', { exact: true })).toBeVisible();
  await page.getByRole('combobox', { name: 'Search method', exact: true }).selectOption('semantic');
  await expect(page.getByRole('heading', { name: 'Seeing Traffic Without Sidecars', exact: true })).toBeVisible();
  await page.getByRole('combobox', { name: 'Search method', exact: true }).selectOption('hybrid');
  await expect(page.getByRole('heading', { name: 'Seeing Traffic Without Sidecars', exact: true })).toBeVisible();
});
