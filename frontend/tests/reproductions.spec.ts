import { test, expect, Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { createHash } from "node:crypto";

const A = "10000000-0000-4000-8000-000000000001";
const B = "10000000-0000-4000-8000-000000000002";
const ATTEMPT = "20000000-0000-4000-8000-000000000001";
const HASH = "a".repeat(64);
const KEY = "awb-pending-reproduction-v1";
const scenarios = ["pass", "tool_error", "timeout", "response_lost"];
const catalog = (active: string | null = null) => ({ version: 1, ready: !active, reason: active ? "runner_busy" : null, active_run_id: active, cases: scenarios.map(id => ({ id, title: id, description: `审核过的 ${id} 合成场景。`, expected: id === "pass" ? "调用完成" : "明确记录故障，不自动重试。" })) });
function report(id: string) {
  return {
    sandbox_report_version: 1, record_id: id, run_id: ATTEMPT,
    mcp: {
      mcp_report_version: 1, invocation_id: ATTEMPT, adapter_outcome: "completed",
      source: { kind: "mcp_sdk_normalized", association: "sdk_dispatch", wire_json_integrity: "not_checked", sdk_version: "2.3.0", adapter_version: "1", protocol_version: "2025-11-25", profile: "isolated-fixture", config_sha256: HASH, case_sha256: HASH, server_code_sha256: HASH, server_dependencies_sha256: null, tool_schema_sha256: HASH, server_revision: null, source_tree_sha256: null },
      contract_report: { schema_version: 1, checker_version: "0.1.0", evidence_sha256: HASH, status: "passed", checks: { input: "passed", output: "passed" }, findings: [], findings_truncated: false }, preflight_findings: [], content_summary: [], elapsed_ms: 20,
    },
    execution: { image_id: `sha256:${HASH}`, source_sha256: HASH, scenario: "pass", seed: 0, policy: "offline-readonly-v1", stdout_bytes: 42, stderr_bytes: 0, frames: 3, error: null, cleanup: "removed", container_exit_code: 0, oom_killed: false },
  };
}
function run(id = A, status = "succeeded", scenario = "pass") {
  return { run_id: id, attempt_id: ATTEMPT, status, scenario, version: 3, created_at: 1791853200, updated_at: 1791853205, lease_until: null, profile: "isolated-fixture", config_sha256: HASH, case_sha256: HASH, report_sha256: status === "succeeded" ? createHash("sha256").update(JSON.stringify(report(id))).digest("hex") : null, executor_state: null };
}
const events = [{ event_id: "30000000-0000-4000-8000-000000000001", version: 1, kind: "created", created_at: 1791853200 }, { event_id: "30000000-0000-4000-8000-000000000002", version: 2, kind: "claimed", created_at: 1791853201 }];
async function setup(page: Page, records = [run()]) {
  const state = { records, active: null as string | null, posts: [] as { request_id: string; scenario: string }[], cancels: [] as string[] };
  await page.route("**/api/reproductions**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (path.endsWith("/catalog")) return route.fulfill({ json: catalog(state.active) });
    if (path.endsWith("/cancel")) { state.cancels.push(path); return route.fulfill({ status: 202, json: { run_id: state.active, status: "cancel_requested" } }); }
    const body = request.postDataJSON(); state.posts.push(body); state.active = body.request_id;
    const created = run(body.request_id, "running", body.scenario); state.records.unshift(created);
    return route.fulfill({ status: 202, json: { run: created, reused: false } });
  });
  await page.route("**/api/runs**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/runs") return route.fulfill({ json: { runs: state.records } });
    const id = path.split("/")[3];
    if (path.endsWith("/report")) return route.fulfill({ json: report(id) });
    const current = state.records.find(item => item.run_id === id);
    return route.fulfill(current ? { json: { run: current, events } } : { status: 404, json: { error: "not_found" } });
  });
  return state;
}
const row = (page: Page, id: string) => page.locator(`tr[data-run-id="${id}"]`);
const open = (page: Page, id: string) => row(page, id).getByRole("link").click();
const status = (page: Page) => page.getByRole("region", { name: "运行详情" }).locator(".run-status-badge");
async function confirmStop(page: Page) {
  const dialog = page.getByRole("dialog", { name: "停止这次复现？" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "停止运行" }).click();
}

test("显式开始只有一次 POST，真实终态与核验报告驱动结果展示", async ({ page }) => {
  const state = await setup(page, []);
  await page.goto("/workspace/tasks");
  await expect(page.getByRole("button", { name: "开始复现", exact: true })).toBeEnabled();
  expect(state.posts).toHaveLength(0);
  await page.getByRole("button", { name: "开始复现", exact: true }).evaluate(button => { (button as HTMLButtonElement).click(); (button as HTMLButtonElement).click(); });
  await expect.poll(() => state.posts.length).toBe(1);
  expect(state.posts[0]).toEqual({ request_id: expect.stringMatching(/^[a-f0-9-]{36}$/), scenario: "pass" });
  const id = state.posts[0].request_id;
  await expect(page).toHaveURL(new RegExp(`run=${id}`));
  await expect(status(page)).toHaveText("运行中");
  await expect(page.locator(".toast-region")).toContainText("复现已开始");
  expect(await page.evaluate(key => JSON.parse(sessionStorage.getItem(key) ?? "null"), KEY)).toBeNull();
  state.records = [run(id)]; state.active = null;
  const detail = page.getByRole("region", { name: "运行详情" });
  await expect(detail.locator(".report-verified")).toBeVisible({ timeout: 8000 });
  await expect(page.locator(".report-facts")).toContainText("20 毫秒");
  await expect(page.locator(".report-facts")).toContainText("已清理");
  await expect(detail.locator(".run-tech")).not.toHaveAttribute("open", "");
});

test("提交响应丢失仅 GET 查询，刷新保留原请求且不自动重发", async ({ page }) => {
  const state = await setup(page, []);
  await page.route("**/api/reproductions", route => { state.posts.push(route.request().postDataJSON()); return route.abort("connectionreset"); });
  await page.goto("/workspace/tasks");
  await page.getByRole("button", { name: "开始复现", exact: true }).click();
  await expect(page.getByText(/连接中断，无法确认复现是否已开始/)).toBeVisible();
  const id = state.posts[0].request_id;
  await expect(page.getByRole("button", { name: "查询提交结果" })).toBeEnabled();
  await page.getByRole("button", { name: "查询提交结果" }).click();
  await page.reload();
  await expect(page.getByText(/无法确认上次提交是否已开始/)).toBeVisible();
  await expect(page.getByRole("button", { name: `复制请求 ID ${id}` })).toBeVisible();
  await expect(page.getByRole("button", { name: "开始复现", exact: true })).toBeDisabled();
  expect(state.posts).toHaveLength(1);
  state.records = [run(id)];
  await page.getByRole("button", { name: "查询提交结果" }).click();
  await expect(page.getByText(/已找到这次提交的运行记录/)).toBeVisible();
  await expect(row(page, id)).toBeVisible();
  await expect(page.getByRole("button", { name: "查询提交结果" })).toHaveCount(0);
  expect(state.posts).toHaveLength(1);
});

test("停止需确认，响应不是终态，重复点击受控且 CLI 记录不可取消", async ({ page }) => {
  const state = await setup(page, [run(A, "running")]);
  await page.goto("/workspace/tasks");
  await open(page, A);
  const detail = page.getByRole("region", { name: "运行详情" });
  await expect(detail.getByRole("button", { name: "停止", exact: true })).toHaveCount(0);
  state.active = A;
  await page.locator(".page-header").getByRole("button", { name: "刷新" }).click();
  await expect(page.locator(".launcher-active")).toContainText("正常调用");
  await detail.getByRole("button", { name: "停止", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "取消" }).click();
  expect(state.cancels).toHaveLength(0);
  await detail.getByRole("button", { name: "停止", exact: true }).evaluate(button => { (button as HTMLButtonElement).click(); (button as HTMLButtonElement).click(); });
  await confirmStop(page);
  await expect(detail.getByRole("button", { name: "正在停止…", exact: true })).toBeDisabled();
  await expect(page.locator(".toast-region")).toContainText("已请求停止");
  expect(state.cancels).toHaveLength(1);
  await expect(status(page)).toHaveText("运行中");
  state.records = [run(A, "outcome_unknown")]; state.active = null;
  await expect(detail).toContainText("无法确认工具是否执行", { timeout: 8000 });
  await expect(page.getByRole("button", { name: /^(停止|正在停止…)$/ })).toHaveCount(0);
});

test("取消失败保留真实运行状态，离页只中止读取", async ({ page }) => {
  const state = await setup(page, [run(A, "running")]); state.active = A;
  await page.route(`**/api/reproductions/${A}/cancel`, route => { state.cancels.push(A); return route.abort("connectionreset"); });
  await page.goto("/workspace/tasks"); await open(page, A);
  await page.locator(".launcher-active").getByRole("button", { name: "停止", exact: true }).click();
  await confirmStop(page);
  await expect(page.getByText(/无法确认是否已停止/)).toBeVisible();
  await expect(status(page)).toHaveText("运行中");
  await page.getByRole("navigation", { name: "产品模块" }).getByRole("link", { name: "分析", exact: true }).click();
  await expect(page).toHaveURL(/workspace\/diagnosis/);
  expect(state.cancels).toHaveLength(1); expect(state.posts).toHaveLength(0);
});

test("准备状态与目录越界拒绝，槽忙响应和隐私错误安全显示", async ({ page }) => {
  const state = await setup(page, []);
  await page.route("**/api/reproductions/catalog", route => route.fulfill({ json: { ...catalog(), ready: false, reason: "docker_unavailable" } }));
  await page.goto("/workspace/tasks"); await expect(page.getByText(/Docker 未运行/)).toBeVisible();
  await expect(page.getByRole("button", { name: "开始复现", exact: true })).toBeDisabled();
  await page.route("**/api/reproductions/catalog", route => route.fulfill({ json: { ...catalog(), secret: "PRIVATE_ERROR" } }));
  await page.getByRole("button", { name: "重新检查环境" }).click();
  await expect(page.getByText(/无法读取场景列表/)).toBeVisible();
  await expect(page.locator("body")).not.toContainText("PRIVATE_ERROR");
  await page.route("**/api/reproductions/catalog", route => route.fulfill({ json: catalog() }));
  await page.getByRole("button", { name: "重新检查环境" }).click();
  await page.route("**/api/reproductions", route => { state.posts.push(route.request().postDataJSON()); return route.fulfill({ status: 429, json: { error: "PRIVATE_ERROR" } }); });
  await page.getByRole("button", { name: "开始复现", exact: true }).click();
  await expect(page.getByText(/已有一个复现在运行，同一时间只能运行一个/)).toBeVisible();
  await expect(page.locator("body")).not.toContainText("PRIVATE_ERROR");
  expect(state.posts).toHaveLength(1);
});

test("迟到提交响应不覆盖用户刚选择的历史，列表筛选保留选择", async ({ page }) => {
  const state = await setup(page, [run(A), run(B)]);
  let release: () => void = () => {};
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/reproductions", async route => { const body = route.request().postDataJSON(); state.posts.push(body); const created = run(body.request_id, "running"); state.records.unshift(created); await held; await route.fulfill({ status: 202, json: { run: created, reused: false } }); });
  await page.goto("/workspace/tasks"); await page.getByRole("button", { name: "开始复现", exact: true }).click();
  await expect.poll(() => state.posts.length).toBe(1);
  await open(page, B); release();
  await expect(page.locator(".toast-region")).toContainText("复现已开始");
  await expect(row(page, state.posts[0].request_id)).toBeVisible();
  await expect(row(page, B)).toHaveAttribute("aria-selected", "true");
  await expect(page).toHaveURL(new RegExp(`run=${B}`));
  await page.getByLabel("状态筛选").selectOption("running");
  await expect(row(page, B)).toHaveCount(0);
  await expect(page.getByRole("region", { name: "运行详情" })).toContainText(B);
});

test("四场景固定配置与复制命令一致，无任意命令执行", async ({ page, context }) => {
  const state = await setup(page, []); await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/workspace/tasks"); await page.getByText("在终端运行", { exact: true }).click();
  for (const [id, label] of [["pass", "正常调用"], ["tool_error", "工具错误"], ["timeout", "调用超时"], ["response_lost", "响应丢失"]]) {
    await page.getByRole("radio", { name: label, exact: true }).check();
    const nextDownload = page.waitForEvent("download"); await page.getByRole("button", { name: /下载场景配置/ }).click();
    const downloaded = await nextDownload; expect(downloaded.suggestedFilename()).toBe(`awb-${id}-server.json`);
    const chunks: Buffer[] = []; for await (const chunk of (await downloaded.createReadStream())!) chunks.push(Buffer.from(chunk));
    expect(JSON.parse(Buffer.concat(chunks).toString())).toEqual({ profile: "isolated-fixture", scenario: id, seed: 0, lifetime: 45 });
    await page.locator(".launcher-cli").getByRole("button", { name: "复制", exact: true }).click();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(`uv run --frozen agent-workbench sandbox-check --server-config ./awb-${id}-server.json --case examples/mcp/lookup-case.json`);
  }
  await expect(page.locator(".toast-region")).toContainText("已复制命令");
  expect(state.posts).toHaveLength(0);
});

for (const width of [1440, 390]) for (const theme of ["light", "dark"] as const) {
  test(`复现页 ${width}px ${theme} 键盘、局部滚动与 axe`, async ({ page }) => {
    await setup(page); await page.setViewportSize({ width, height: 960 }); await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
    await page.goto("/workspace/tasks"); await expect(page.getByRole("radio", { name: "正常调用", exact: true })).toBeEnabled(); await page.getByRole("radio", { name: "正常调用", exact: true }).focus(); await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("radio", { name: "工具错误", exact: true })).toBeChecked();
    await expect(page.locator(".launcher-desc")).toContainText("审核过的 tool_error 合成场景。");
    await open(page, A); await expect(page.locator(".report-verified")).toBeVisible();
    await page.getByText("在终端运行", { exact: true }).click(); await page.getByText("技术详情", { exact: true }).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze(); expect(audit.violations).toEqual([]);
    await page.evaluate(() => { (document.activeElement as HTMLElement)?.blur(); window.scrollTo(0, 0); });
    await page.screenshot({ path: `../artifacts/p101a-${width}-${theme}.png`, fullPage: true });
  });
}

test("报告摘要先验证 SHA、schema 与双 ID，失败不展示已核验结论", async ({ page }) => {
  const state = await setup(page);
  for (const [kind, corrupt] of [
    ["hash", { ...report(A) }],
    ["schema", { ...report(A), private_value: "PRIVATE_REPORT" }],
    ["record", { ...report(A), record_id: B }],
    ["attempt", { ...report(A), run_id: B }],
  ] as const) {
    const raw = JSON.stringify(corrupt);
    state.records = [{ ...run(), report_sha256: kind === "hash" ? HASH : createHash("sha256").update(raw).digest("hex") }];
    await page.route(`**/api/runs/${A}/report`, route => route.fulfill({ contentType: "application/json", body: raw }));
    await page.goto("/workspace/tasks"); await open(page, A);
    await expect(page.getByRole("region", { name: "运行详情" })).toContainText("摘要校验未通过");
    await expect(page.locator(".report-verified")).toHaveCount(0); await expect(page.locator(".report-facts")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "正常调用通过" })).toHaveCount(0);
    await expect(page.locator("body")).not.toContainText("PRIVATE_REPORT");
  }
});
