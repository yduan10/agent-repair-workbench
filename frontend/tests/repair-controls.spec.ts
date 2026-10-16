import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
const KEY = "awb-pending-repair-v1", SHA = "a".repeat(64);
const ID = "10000000-0000-4000-8000-000000000001";
const budget = { total_tokens: 2000000, output_tokens: 8192, model_calls: 12, tool_calls: 20, candidates: 2, timeout_seconds: 600 };
function record(id: string, case_id = "output_mismatch", mode = "three_role") {
  return { schema_version: 1, request_id: id, task_id: id, case_id, mode, sha256: SHA, cancel_requested: false, active: true, reused: false,
    task: { schema_version: 1, task_id: id, mode, source_analysis_id: null, phase: "model_pending", outcome: null as string | null, error_code: null, revision: 1, started_at: "2026-10-16T00:00:00Z", finished_at: null as string | null, budget,
      usage: { model_calls: 1, tool_calls: 0, reserved_tokens: 10000, known_input_tokens: 0, known_output_tokens: 0, usage_complete: false }, candidate_count: 0, cost_amount: null, model_config_sha256: SHA,
      baseline: { schema_version: 1, snapshot_id: ID, kind: "baseline", file: "server.py", manifest_sha256: SHA, file_sha256: SHA, tree_sha256: SHA, baseline_id: null, baseline_tree_sha256: null, patch_sha256: null } } };
}
async function setup(page: Page, options: { lost?: boolean; unavailable?: boolean; mismatch?: boolean; recovery?: boolean } = {}) {
  const starts: { request_id: string; case_id: string; mode: string }[] = []; const cancels: string[] = []; let r: ReturnType<typeof record> | null = null;
  await page.route("**/api/repairs**", route => route.fulfill({ json: new URL(route.request().url()).pathname === "/api/repairs" ? { schema_version: 2, repairs: [] } : { error: "repair_not_found" }, status: new URL(route.request().url()).pathname === "/api/repairs" ? 200 : 404 }));
  await page.route("**/api/repair-runs**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("catalog")) return route.fulfill({ json: { schema_version: 1, cases: [{ id: "output_mismatch", label: "返回类型错误" }, { id: "counter_offset", label: "计数值偏移" }], modes: [{ id: "single_role", label: "单角色" }, { id: "three_role", label: "三角色" }], budget, model: { configured: !options.unavailable, reason: options.unavailable ? "model_not_configured" : null }, image: { prepared: true }, slot: { status: options.recovery ? "recovery_required" : r?.active ? "busy" : "available", task_id: options.recovery ? ID : r?.active ? r.task_id : null }, accepting: true } });
    if (path.endsWith("events") && r) return route.fulfill({ json: { schema_version: 1, task_id: r.task_id, revision: r.task.revision, events: Array.from({ length: r.task.revision + 1 }, (_, revision) => ({ revision, at: r!.task.started_at, kind: revision ? "reserved" : "created", role: revision ? "diagnosis" : null, operation: revision ? "model" : null, tool: null, status: revision ? "pending" : null, error_code: null })) } });
    if (path.endsWith("cancel") && r) { cancels.push(r.task_id); r.cancel_requested = true; return route.fulfill({ status: 202, json: r }); }
    if (path === "/api/repair-runs" && route.request().method() === "POST") {
      const body = route.request().postDataJSON(); starts.push(body);
      r = record(body.request_id, body.case_id, body.mode);
      if (options.lost && starts.length === 1) { r = null; return route.abort("connectionfailed"); }
      if (options.mismatch) return route.fulfill({ status: 202, json: { ...r, mode: body.mode === "three_role" ? "single_role" : "three_role" } });
      return route.fulfill({ status: 202, json: r });
    }
    return route.fulfill({ status: r ? 200 : 404, json: r ?? { error: "web_repair_not_found" } });
  });
  return { starts, cancels, finish() { if (r) { r.active = false; r.task.phase = "finished"; r.task.outcome = "cancelled"; r.task.finished_at = "2026-10-16T00:00:03Z"; r.task.revision++; r.task.usage.reserved_tokens = 0; r.task.usage.usage_complete = true; } } };
}
test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "ignoreErrors" }); });
for (const [caseId, mode] of [["output_mismatch", "single_role"], ["counter_offset", "three_role"]]) {
  test(`start ${caseId}/${mode}, stop and clear only confirmed terminal`, async ({ page }) => {
    const state = await setup(page); await page.goto("/workspace/repairs");
    await page.getByLabel("案例", { exact: true }).selectOption(caseId); await page.getByLabel("协作方式").selectOption(mode);
    await expect(page.getByRole("button", { name: "开始修复", exact: true })).toBeEnabled();
    await page.getByRole("button", { name: "开始修复", exact: true }).dblclick();
    await expect(page.getByRole("button", { name: "停止修复", exact: true })).toBeVisible();
    expect(state.starts).toHaveLength(1); expect(state.starts[0]).toMatchObject({ case_id: caseId, mode });
    await page.reload(); await expect(page.getByRole("button", { name: "停止修复", exact: true })).toBeVisible(); expect(state.starts).toHaveLength(1);
    await page.getByRole("button", { name: "停止修复", exact: true }).click(); await page.getByRole("dialog").getByRole("button", { name: "停止修复", exact: true }).click();
    await expect(page.getByRole("button", { name: "正在停止", exact: true })).toBeDisabled(); expect(state.cancels).toEqual([state.starts[0].request_id]);
    expect(await page.evaluate(key => sessionStorage.getItem(key), KEY)).not.toBeNull();
    state.finish(); await page.getByRole("button", { name: "查询状态", exact: true }).click();
    await expect.poll(() => page.evaluate(key => sessionStorage.getItem(key), KEY)).toBeNull();
    await expect(page.getByRole("button", { name: "开始修复", exact: true })).toBeEnabled();
  });
}
test("lost response and 404 retain identity; only explicit retry writes", async ({ page }) => {
  const state = await setup(page, { lost: true }); await page.goto("/workspace/repairs");
  await page.getByRole("button", { name: "开始修复", exact: true }).click();
  await expect(page.getByText("提交结果待确认", { exact: true })).toBeVisible();
  const original = state.starts[0]; await page.reload();
  await expect(page.getByRole("button", { name: "重新提交同一请求" })).toBeEnabled(); expect(state.starts).toHaveLength(1);
  await page.getByRole("button", { name: "重新提交同一请求" }).click();
  await expect(page.getByRole("button", { name: "停止修复", exact: true })).toBeVisible(); expect(state.starts).toEqual([original, original]);
});
test("storage write failure prevents any POST", async ({ page }) => {
  await page.addInitScript(() => { Storage.prototype.setItem = () => { throw new Error("disabled"); }; });
  const state = await setup(page); await page.goto("/workspace/repairs");
  await expect(page.getByText("提交存储不可用", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "开始修复", exact: true })).toBeDisabled(); expect(state.starts).toHaveLength(0);
});
for (const option of ["unavailable", "recovery"] as const) test(`${option} blocks launch and guides environment`, async ({ page }) => {
  await setup(page, { [option]: true }); await page.goto("/workspace/repairs");
  await expect(page.getByRole("button", { name: "开始修复", exact: true })).toBeDisabled();
  await expect(page.getByRole("link", { name: "查看环境", exact: true })).toBeVisible();
});
for (const [theme, width] of [["light", 1440], ["dark", 390]] as const) test(`${theme} ${width} keyboard and accessible controls`, async ({ page }) => {
  await setup(page); await page.setViewportSize({ width, height: 900 }); await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" }); await page.goto("/workspace/repairs");
  const region = page.getByRole("region", { name: "新建修复", exact: true });
  await region.getByLabel("案例", { exact: true }).focus(); await page.keyboard.press("Tab"); await expect(region.getByLabel("协作方式")).toBeFocused();
  await expect(page.getByRole("button", { name: "开始修复", exact: true })).toBeEnabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect((await new AxeBuilder({ page }).include('.rp-launch').analyze()).violations).toEqual([]);
  await page.screenshot({ path: `../artifacts/b3-${theme}-${width}.png`, fullPage: true });
});

test("mismatched write receipt never confirms a different mode", async ({ page }) => {
  const state = await setup(page, { mismatch: true });
  await page.route(/\/api\/repair-runs\/[a-f0-9-]{36}$/, route => route.fulfill({ status: 404, json: { error: "web_repair_not_found" } }));
  await page.goto("/workspace/repairs");
  await page.getByRole("button", { name: "开始修复", exact: true }).click();
  await expect(page.getByText("提交结果待确认", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "停止修复", exact: true })).toHaveCount(0);
  const saved = await page.evaluate(key => JSON.parse(sessionStorage.getItem(key)!), KEY);
  expect(saved).toEqual(state.starts[0]);
  await expect(page.getByRole("button", { name: "开始修复", exact: true })).toBeDisabled();
});

test("a CLI-only history has no web cancellation control", async ({ page }) => {
  const state = await setup(page);
  await page.goto(`/workspace/repairs?task=${ID}`);
  await expect(page.getByRole("button", { name: "开始修复", exact: true })).toBeEnabled();
  await expect(page.getByRole("button", { name: "停止修复", exact: true })).toHaveCount(0);
  expect(state.cancels).toEqual([]);
  expect(await page.evaluate(key => sessionStorage.getItem(key), KEY)).toBeNull();
});
