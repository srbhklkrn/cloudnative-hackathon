import { expect, test } from '@playwright/test';

test('the same search can be submitted again after a failure', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.session-card')).toHaveCount(30);
  let attempts = 0;
  await page.route('**/api/search?**', async route => {
    if (new URL(route.request().url()).searchParams.get('q') === 'networking' && ++attempts === 1) {
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Search temporarily unavailable' }) });
    } else await route.continue();
  });
  await page.getByRole('searchbox').fill('networking');
  await page.getByRole('button', { name: 'Find my sessions', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Search temporarily unavailable');
  await page.getByRole('button', { name: 'Find my sessions', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.locator('.results-note')).toContainText('available sessions for “networking”');
  expect(attempts).toBe(2);
});

// Each browser has its own agenda; these tests never reset the shared program.
test('accessibility filters respond immediately and can be cleared from an empty result', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.session-card')).toHaveCount(30);
  await page.getByRole('combobox', { name: 'Filter topic', exact: true }).selectOption('security');
  await page.getByRole('combobox', { name: 'Filter level', exact: true }).selectOption('beginner');
  await page.getByRole('combobox', { name: 'Sessions starting after', exact: true }).selectOption('13:00');
  await expect(page.locator('.session-card')).toHaveCount(2);

  let release: () => void = () => {};
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/agenda', async route => {
    if (route.request().method() === 'POST') await gate;
    await route.continue();
  });
  const captions = page.getByLabel('Live captions', { exact: true });
  await captions.click();
  try {
    await expect(captions).toBeChecked({ timeout: 1000 });
  } finally { release(); }
  await expect(captions).toBeEnabled();
  await page.unroute('**/api/agenda');
  await page.getByLabel('Hearing loop', { exact: true }).click();
  await expect(page.getByLabel('Hearing loop', { exact: true })).toBeEnabled();
  await page.getByLabel('Quiet space', { exact: true }).click();
  await expect(page.getByText('A different path awaits.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Clear all filters', exact: true }).click();
  await expect(captions).not.toBeChecked();
  await expect(page.getByLabel('Hearing loop', { exact: true })).not.toBeChecked();
  await expect(page.getByLabel('Quiet space', { exact: true })).not.toBeChecked();
  await expect(page.locator('.session-card')).toHaveCount(30);
});

test('agenda saves compatible sessions, explains conflicts and survives reload', async ({ page }) => {
  await page.goto('/');
  const first = page.getByRole('button', { name: "Save Inside Cilium's Datapath", exact: true });
  await first.click();
  await expect(page.getByRole('button', { name: "Remove Inside Cilium's Datapath", exact: true })).toBeEnabled();
  const conflicting = page.getByTestId('session-session-02');
  await expect(conflicting.getByRole('button', { name: /Save/ })).toBeDisabled();
  await expect(conflicting).toContainText("Inside Cilium's Datapath");
  await page.getByRole('button', { name: 'Save Packets, Policies and Pod Identity', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Remove Packets, Policies and Pod Identity', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: /My agenda/ }).click();
  await expect(page.locator('.timeline-item')).toHaveCount(2);
  await page.reload();
  await expect(page.locator('.timeline-item')).toHaveCount(2);
  await page.getByRole('button', { name: "Remove Inside Cilium's Datapath from agenda", exact: true }).click();
  await expect(page.locator('.timeline-item')).toHaveCount(1);
  await expect(page.getByRole('button', { name: 'Save A Safer Cluster, One Policy at a Time', exact: true })).toBeEnabled();
});

test('failed agenda saves stop showing progress and remain visible after a background refresh', async ({ page }) => {
  await page.clock.install();
  await page.goto('/');
  const save = page.getByRole('button', { name: "Save Inside Cilium's Datapath", exact: true });
  await expect(save).toBeEnabled();
  await page.route('**/api/agenda', async route => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: 'The agenda changed. Refresh and try again.' }) });
    } else await route.continue();
  });
  await save.click();
  await expect(page.getByRole('alert')).toContainText('The agenda changed.');
  await expect(page.getByText('Saving your change…', { exact: true })).toHaveCount(0);
  const poll = page.waitForResponse(response => response.url().endsWith('/api/sessions'));
  await page.clock.fastForward(8000);
  await poll;
  await expect(page.getByRole('alert')).toContainText('The agenda changed.');
  await expect(page.locator('.timeline-item')).toHaveCount(0);
  await page.getByLabel('Live captions', { exact: true }).click();
  await expect(page.getByLabel('Live captions', { exact: true })).toBeEnabled();
  await expect(page.getByLabel('Live captions', { exact: true })).not.toBeChecked();
});
