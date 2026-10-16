import { test, expect, type Page, type Route } from "@playwright/test";
const ID = "10000000-0000-4000-8000-000000000001", SHA = "a".repeat(64), KEY = "awb-pending-repair-v1";
const intent = { request_id: ID, case_id: "output_mismatch", mode: "three_role" };
function receipt(finished = false) {
  return {
    schema_version: 1, request_id: ID, task_id: ID, case_id: "output_mismatch", mode: "three_role",
    sha256: SHA, cancel_requested: false, active: !finished, reused: true,
    task: {
      schema_version: 1, task_id: ID, source_analysis_id: null, mode: "three_role",
      phase: finished ? "finished" : "model_pending", outcome: finished ? "candidate_verified" : null,
      error_code: null, revision: finished ? 4 : 1, started_at: "2026-10-16T00:00:00Z",
      finished_at: finished ? "2026-10-16T00:00:02Z" : null,
      budget: { total_tokens: 2000000, output_tokens: 8192, model_calls: 12, tool_calls: 20, candidates: 2, timeout_seconds: 600 },
      usage: { model_calls: 1, tool_calls: 0, reserved_tokens: finished ? 0 : 10000, known_input_tokens: 0, known_output_tokens: 0, usage_complete: finished },
      candidate_count: finished ? 1 : 0, cost_amount: null, model_config_sha256: SHA,
      baseline: { schema_version: 1, snapshot_id: "20000000-0000-4000-8000-000000000001", kind: "baseline", file: "server.py", manifest_sha256: SHA, file_sha256: SHA, tree_sha256: SHA, baseline_id: null, baseline_tree_sha256: null, patch_sha256: null },
    },
  };
}
async function setup(page: Page, state = receipt()) {
  const writes: string[] = [];
  await page.route("**/api/repairs**", route => route.fulfill({ json: new URL(route.request().url()).pathname === "/api/repairs" ? { schema_version: 2, repairs: [] } : { error: "repair_not_found" }, status: new URL(route.request().url()).pathname === "/api/repairs" ? 200 : 404 }));
  await page.route("**/api/repair-runs**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() !== "GET") writes.push(path);
    if (path.endsWith("catalog")) return route.fulfill({ json: { schema_version: 1, cases: [{ id: "output_mismatch", label: "返回类型错误" }, { id: "counter_offset", label: "计数值偏移" }], modes: [{ id: "single_role", label: "单角色" }, { id: "three_role", label: "三角色" }], budget: state.task.budget, model: { configured: true, reason: null }, image: { prepared: true }, slot: { status: state.active ? "busy" : "available", task_id: state.active ? ID : null }, accepting: true } });
    if (path.endsWith("events")) return route.fulfill({ json: { schema_version: 1, task_id: ID, revision: state.task.revision, events: Array.from({ length: state.task.revision + 1 }, (_, revision) => ({ revision, at: "2026-10-16T00:00:00Z", kind: revision ? "reserved" : "created", role: null, operation: null, tool: null, status: null, error_code: null })) } });
    if (path.endsWith("cancel")) return route.fulfill({ status: 202, json: { ...state, cancel_requested: true } });
    return route.fulfill({ json: state });
  });
  return writes;
}
test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "ignoreErrors" }); });
test("independent: recorded candidate pass is not presented as current verification", async ({ page }) => {
  await setup(page, receipt(true));
  await page.goto(`/workspace/repairs?task=${ID}`);
  const terminal = page.getByRole("region", { name: "执行控制台", exact: true });
  await expect(terminal).toBeVisible();
  await expect(terminal.getByText("回归通过", { exact: true })).toHaveCount(0);
  await expect(terminal).toContainText(/记录|查看|历史|曾/);
});
test("independent: delayed GET cannot reverse an acknowledged cancellation", async ({ page }) => {
  await setup(page);
  await page.goto(`/workspace/repairs?task=${ID}`);
  await expect(page.getByRole("button", { name: "停止修复", exact: true })).toBeVisible();
  let held: Route | undefined;
  await page.route(`**/api/repair-runs/${ID}`, async route => { held = route; });
  await page.getByRole("button", { name: "查询状态", exact: true }).click();
  await expect.poll(() => !!held).toBe(true);
  await page.getByRole("button", { name: "停止修复", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "停止修复", exact: true }).click();
  await expect(page.getByRole("button", { name: "正在停止", exact: true })).toBeDisabled();
  await held!.fulfill({ json: receipt() });
  await page.waitForTimeout(100);
  await expect(page.getByRole("button", { name: "正在停止", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "停止修复", exact: true })).toHaveCount(0);
});
test("independent: an empty stored value is corruption and must not be overwritten", async ({ page }) => {
  await page.addInitScript(key => sessionStorage.setItem(key, ""), KEY);
  const writes = await setup(page, receipt(true));
  await page.goto("/workspace/repairs");
  await expect(page.getByRole("button", { name: "开始修复", exact: true })).toBeDisabled();
  await expect(page.getByText("提交存储不可用", { exact: true })).toBeVisible();
  expect(await page.evaluate(key => sessionStorage.getItem(key), KEY)).toBe("");
  expect(writes).toEqual([]);
});
test("independent: refresh of pending 404 never sends a write or discards intent", async ({ page }) => {
  await page.addInitScript(({ key, intent }) => sessionStorage.setItem(key, JSON.stringify(intent)), { key: KEY, intent });
  const writes = await setup(page, receipt(true));
  await page.route(`**/api/repair-runs/${ID}`, route => route.fulfill({ status: 404, json: { error: "web_repair_not_found" } }));
  await page.goto("/workspace/repairs");
  await expect(page.getByText("提交结果待确认", { exact: true })).toBeVisible();
  expect(await page.evaluate(key => JSON.parse(sessionStorage.getItem(key)!), KEY)).toEqual(intent);
  await page.reload();
  await expect(page.getByRole("button", { name: "开始修复", exact: true })).toBeDisabled();
  expect(await page.evaluate(key => JSON.parse(sessionStorage.getItem(key)!), KEY)).toEqual(intent);
  expect(writes).toEqual([]);
});

test("independent: late acknowledgement preserves a newer terminal receipt", async () => {
  const { mergeReceipt, receiptSchema } = await import("../lib/repair-runs");
  const done = receiptSchema.parse({ ...receipt(true), cancel_requested: true });
  const old = receiptSchema.parse(receipt());
  const merged = mergeReceipt(done, old);
  expect(merged.task.phase).toBe("finished");
  expect(merged.active).toBe(false);
  expect(merged.cancel_requested).toBe(true);
  expect(merged.task.revision).toBe(done.task.revision);
});

test("independent: control panel keeps keyboard and theme layout at 390 and 1440", async ({ page }) => {
  await setup(page);
  for (const width of [390, 1440]) {
    for (const theme of ["light", "dark"] as const) {
      await page.setViewportSize({ width, height: 1000 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
      await page.goto(`/workspace/repairs?task=${ID}`);
      await expect(page.getByRole("button", { name: "停止修复", exact: true })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.getByRole("button", { name: "停止修复", exact: true }).focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("dialog")).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog")).not.toBeVisible();
      await page.screenshot({ path: `../artifacts/b3-review-${width}-${theme}.png`, fullPage: true });
    }
  }
});
