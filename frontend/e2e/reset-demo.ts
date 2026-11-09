import { expect, type APIRequestContext } from '@playwright/test';

export async function resetDemo(request: APIRequestContext) {
  const meta = await (await request.get('/api/meta')).json();
  if (meta.store !== 'memory') {
    const response = await request.get('/__test_scope');
    expect(response.ok(), 'Reset-based tests require the isolated browser test server, never the shared demo').toBeTruthy();
    const scope = await response.json();
    expect(scope.isolated).toBe(true);
    expect(scope.index_prefix).toMatch(/^detour-demo-browser-[a-f0-9]{32}$/);
  }
  const response = await request.post('/api/demo/reset', { data: {} });
  expect(response.ok()).toBeTruthy();
}
