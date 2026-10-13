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

test("显式开始只有一次 POST，真实终态与核验报告驱动结果展示", async ({ page }) => {
  const state = await setup(page, []);
  await page.goto("/workspace/tasks");
  await expect(page.getByRole("button", { name: "开始复现", exact: true })).toBeEnabled();
  expect(state.posts).toHaveLength(0);
  await page.getByRole("button", { name: "开始复现", exact: true }).evaluate(button => { (button as HTMLButtonElement).click(); (button as HTMLButtonElement).click(); });
  await expect.poll(() => state.posts.length).toBe(1);
  expect(state.posts[0]).toEqual({ request_id: expect.stringMatching(/^[a-f0-9-]{36}$/), scenario: "pass" });
  const id = state.posts[0].request_id;
  await expect(page.getByRole("region", { name: "运行详情" })).toContainText("执行中");
  expect(await page.evaluate(key => JSON.parse(sessionStorage.getItem(key) ?? "null"), KEY)).toBeNull();
  state.records = [run(id)]; state.active = null;
  await expect(page.getByRole("region", { name: "运行详情" })).toContainText("结构、关联与摘要已校验", { timeout: 8000 });
  await expect(page.locator(".report-summary")).toContainText("20 ms");
  await expect(page.locator(".report-summary")).toContainText("已回收");
  await expect(page.getByRole("region", { name: "运行详情" }).locator(".run-digests")).not.toHaveAttribute("open", "");
});

test("提交响应丢失仅 GET 查询，刷新保留原请求且不自动重发", async ({ page }) => {
  const state = await setup(page, []);
  await page.route("**/api/reproductions", route => { state.posts.push(route.request().postDataJSON()); return route.abort("connectionreset"); });
  await page.goto("/workspace/tasks");
  await page.getByRole("button", { name: "开始复现", exact: true }).click();
  await expect(page.getByText(/提交结果待确认/)).toBeVisible();
  const id = state.posts[0].request_id;
  await expect(page.getByRole("button", { name: "仅查询提交结果" })).toBeEnabled();
  await page.getByRole("button", { name: "仅查询提交结果" }).click();
  await page.reload();
  await expect(page.getByText(/发现上次尚未确认的提交/)).toBeVisible();
  await expect(page.getByRole("button", { name: "开始复现", exact: true })).toBeDisabled();
  expect(state.posts).toHaveLength(1);
  state.records = [run(id)];
  await page.getByRole("button", { name: "仅查询提交结果" }).click();
  await expect(page.getByText(/已找到本次提交的运行记录/)).toBeVisible();
  await expect(page.getByRole("button", { name: `查看运行 ${id}` })).toBeVisible();
  expect(state.posts).toHaveLength(1);
});

test("停止响应不是终态，重复点击受控且 CLI 记录不可取消", async ({ page }) => {
  const state = await setup(page, [run(A, "running")]);
  await page.goto("/workspace/tasks");
  await page.getByRole("button", { name: `查看运行 ${A}` }).click();
  await expect(page.getByRole("button", { name: "请求停止运行" })).toHaveCount(0);
  state.active = A;
  await page.getByRole("button", { name: "刷新记录" }).click();
  await page.getByRole("button", { name: "请求停止运行" }).evaluate(button => { (button as HTMLButtonElement).click(); (button as HTMLButtonElement).click(); });
  await expect(page.getByRole("button", { name: "已请求停止", exact: true })).toBeDisabled();
  expect(state.cancels).toHaveLength(1);
  await expect(page.getByRole("region", { name: "运行详情" }).getByRole("status").first()).toHaveText("执行中");
  state.records = [run(A, "outcome_unknown")]; state.active = null;
  await expect(page.getByRole("region", { name: "运行详情" })).toContainText("这不代表执行没有发生", { timeout: 8000 });
  await expect(page.getByRole("button", { name: "请求停止运行" })).toHaveCount(0);
});

test("取消失败保留真实运行状态，离页只中止读取", async ({ page }) => {
  const state = await setup(page, [run(A, "running")]); state.active = A;
  await page.route(`**/api/reproductions/${A}/cancel`, route => { state.cancels.push(A); return route.abort("connectionreset"); });
  await page.goto("/workspace/tasks"); await page.getByRole("button", { name: `查看运行 ${A}` }).click();
  await page.getByRole("button", { name: "请求停止运行" }).click();
  await expect(page.getByText(/停止请求结果未确认/)).toBeVisible();
  await expect(page.getByRole("region", { name: "运行详情" }).getByRole("status").first()).toHaveText("执行中");
  await page.getByRole("link", { name: /诊断分析 开发中/ }).click();
  expect(state.cancels).toHaveLength(1); expect(state.posts).toHaveLength(0);
});

test("准备状态与目录越界拒绝，槽忙响应和隐私错误安全显示", async ({ page }) => {
  const state = await setup(page, []);
  await page.route("**/api/reproductions/catalog", route => route.fulfill({ json: { ...catalog(), ready: false, reason: "docker_unavailable" } }));
  await page.goto("/workspace/tasks"); await expect(page.getByText(/Docker 暂不可用/)).toBeVisible();
  await expect(page.getByRole("button", { name: "开始复现", exact: true })).toBeDisabled();
  await page.route("**/api/reproductions/catalog", route => route.fulfill({ json: { ...catalog(), secret: "PRIVATE_ERROR" } }));
  await page.getByRole("button", { name: "重新检查准备状态" }).click();
  await expect(page.getByText(/场景目录不符合约定/)).toBeVisible();
  await expect(page.locator("body")).not.toContainText("PRIVATE_ERROR");
  await page.route("**/api/reproductions/catalog", route => route.fulfill({ json: catalog() }));
  await page.getByRole("button", { name: "重新检查准备状态" }).click();
  await page.route("**/api/reproductions", route => { state.posts.push(route.request().postDataJSON()); return route.fulfill({ status: 429, json: { error: "PRIVATE_ERROR" } }); });
  await page.getByRole("button", { name: "开始复现", exact: true }).click();
  await expect(page.getByText(/已有网页任务占用执行槽/)).toBeVisible();
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
  await page.getByRole("button", { name: `查看运行 ${B}` }).click(); release();
  await expect(page.getByText(/复现已接收/)).toBeVisible();
  await expect(page.getByRole("button", { name: `查看运行 ${B}` })).toHaveAttribute("aria-pressed", "true");
  await page.getByLabel("状态筛选").selectOption("running");
  await expect(page.getByRole("button", { name: `查看运行 ${B}` })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "运行详情" })).toContainText(B);
});

test("四场景固定配置与复制命令一致，无任意命令执行", async ({ page, context }) => {
  const state = await setup(page, []); await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/workspace/tasks"); await page.getByText("在终端运行此场景", { exact: true }).click();
  for (const [id, label] of [["pass", "正常调用"], ["tool_error", "工具错误"], ["timeout", "调用超时"], ["response_lost", "响应丢失"]]) {
    await page.getByRole("radio", { name: label, exact: true }).check();
    const nextDownload = page.waitForEvent("download"); await page.getByRole("button", { name: "下载场景配置" }).click();
    const downloaded = await nextDownload; expect(downloaded.suggestedFilename()).toBe(`awb-${id}-server.json`);
    const chunks: Buffer[] = []; for await (const chunk of (await downloaded.createReadStream())!) chunks.push(Buffer.from(chunk));
    expect(JSON.parse(Buffer.concat(chunks).toString())).toEqual({ profile: "isolated-fixture", scenario: id, seed: 0, lifetime: 45 });
    await page.getByRole("button", { name: "复制命令" }).click();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(`uv run --frozen agent-workbench sandbox-check --server-config ./awb-${id}-server.json --case examples/mcp/lookup-case.json`);
  }
  expect(state.posts).toHaveLength(0);
});

for (const width of [1440, 390]) for (const theme of ["light", "dark"] as const) {
  test(`复现页 ${width}px ${theme} 键盘、局部滚动与 axe`, async ({ page }) => {
    await setup(page); await page.setViewportSize({ width, height: 960 }); await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
    await page.goto("/workspace/tasks"); await page.getByRole("radio", { name: "正常调用", exact: true }).focus(); await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("radio", { name: "工具错误", exact: true })).toBeChecked();
    await page.getByRole("button", { name: `查看运行 ${A}` }).click(); await expect(page.locator(".verified-label")).toBeVisible();
    await page.getByText("在终端运行此场景", { exact: true }).click(); await page.getByText("技术详情：ID、版本与摘要", { exact: true }).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    expect(await page.locator(".scenario-picker label").first().evaluate(node => getComputedStyle(node).transitionDuration)).toBe("0s");
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
    await page.goto("/workspace/tasks"); await page.getByRole("button", { name: `查看运行 ${A}` }).click();
    await expect(page.getByRole("region", { name: "运行详情" })).toContainText("摘要校验未通过");
    await expect(page.locator(".verified-label")).toHaveCount(0); await expect(page.locator(".report-summary")).toHaveCount(0);
    await expect(page.locator("body")).not.toContainText("PRIVATE_REPORT");
  }
});
