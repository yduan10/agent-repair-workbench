import { test, expect } from '@playwright/test';

const region = (page: import('@playwright/test').Page) => page.getByRole('region', { name: '角色与工具接口', exact: true });

for (const [name, body] of [
  ['oversize', Buffer.from(' '.repeat(131073))],
  ['invalid_utf8', Buffer.from([0xc3, 0x28])],
  ['invalid_json', Buffer.from('{"secret":"REVIEW_PRIVATE",')],
] as const) {
  test(`reviewer rejects ${name} without exposing response`, async ({ page }) => {
    await page.route('**/api/agent-contracts', route => route.fulfill({ status: 200, body, contentType: 'application/json' }));
    await page.goto('/workspace/connections');
    const catalog = region(page);
    await expect(catalog.getByRole('alert')).toBeVisible();
    await expect(catalog.getByRole('button', { name: '下载完整目录' })).toHaveCount(0);
    await expect(page.locator('body')).not.toContainText('REVIEW_PRIVATE');
    await page.unroute('**/api/agent-contracts');
    await catalog.getByRole('button', { name: '重试', exact: true }).click();
    await expect(catalog.locator('.contract-item[data-role="diagnosis"]')).toBeVisible();
  });
}

test('reviewer timeout becomes retryable error', async ({ page }) => {
  let release!: () => void;
  const waiting = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/agent-contracts', async route => { await waiting; await route.abort().catch(() => {}); });
  await page.goto('/workspace/connections');
  const catalog = region(page);
  await expect(catalog.getByRole('status')).toBeVisible();
  try {
    await expect(catalog.getByRole('alert')).toBeVisible({ timeout: 18000 });
    await expect(catalog.getByRole('button', { name: '重试', exact: true })).toBeVisible();
  } finally { release(); }
});

test('reviewer navigation aborts loading request without stale state', async ({ page }) => {
  await page.addInitScript(() => {
    const original = window.fetch;
    (window as unknown as { catalogAborted: boolean }).catalogAborted = false;
    window.fetch = (input, init) => {
      if (input === '/api/agent-contracts') init?.signal?.addEventListener('abort', () => {
        (window as unknown as { catalogAborted: boolean }).catalogAborted = true;
      });
      return original(input, init);
    };
  });
  let release!: () => void;
  const waiting = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/agent-contracts', async route => { await waiting; await route.abort().catch(() => {}); });
  await page.goto('/workspace/connections');
  await expect(region(page).getByRole('status')).toBeVisible();
  try {
    await page.getByRole('navigation', { name: '产品模块' }).getByRole('link', { name: '复现', exact: true }).click();
    await expect(page).toHaveURL(/\/workspace\/tasks$/);
    await expect.poll(() => page.evaluate(() => (window as unknown as { catalogAborted: boolean }).catalogAborted)).toBe(true);
    await expect(region(page)).toHaveCount(0);
  } finally { release(); }
});
