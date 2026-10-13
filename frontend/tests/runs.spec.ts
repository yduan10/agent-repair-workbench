import { test, expect, Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { createHash } from "node:crypto";

const A = "10000000-0000-4000-8000-000000000001";
const B = "10000000-0000-4000-8000-000000000002";
const ATTEMPT = "20000000-0000-4000-8000-000000000001";
const HASH = "a".repeat(64);
const report = {
  sandbox_report_version: 1, record_id: A, run_id: ATTEMPT,
  mcp: {
    mcp_report_version: 1, invocation_id: ATTEMPT, adapter_outcome: "completed",
    source: {
      kind: "mcp_sdk_normalized", association: "sdk_dispatch", wire_json_integrity: "not_checked", sdk_version: "2.3.0", adapter_version: "1",
      protocol_version: "2025-11-25", profile: "isolated-fixture", config_sha256: HASH, case_sha256: HASH,
      server_code_sha256: HASH, server_dependencies_sha256: null, tool_schema_sha256: HASH, server_revision: null, source_tree_sha256: null,
    },
    contract_report: { schema_version: 1, checker_version: "0.1.0", evidence_sha256: HASH, status: "passed", checks: { input: "passed", output: "passed" }, findings: [], findings_truncated: false },
    preflight_findings: [], content_summary: [], elapsed_ms: 20,
  },
  execution: { image_id: `sha256:${HASH}`, source_sha256: HASH, scenario: "pass", seed: 0, policy: "offline-readonly-v1", stdout_bytes: 42, stderr_bytes: 0, frames: 3, error: null, cleanup: "removed", container_exit_code: 0, oom_killed: false },
};
const reportBytes = JSON.stringify(report);
const run = (id = A, status = "succeeded") => ({
  run_id: id, attempt_id: status === "queued" ? null : ATTEMPT, status, version: 3,
  created_at: 1791853200, updated_at: 1791853205, lease_until: null, profile: "isolated-fixture", scenario: "pass",
  config_sha256: HASH, case_sha256: HASH, report_sha256: status === "succeeded" ? createHash("sha256").update(reportBytes).digest("hex") : null, executor_state: null,
});
const events = [
  { event_id: "30000000-0000-4000-8000-000000000001", version: 1, kind: "created", created_at: 1791853200 },
  { event_id: "30000000-0000-4000-8000-000000000002", version: 2, kind: "claimed", created_at: 1791853201 },
  { event_id: "30000000-0000-4000-8000-000000000003", version: 3, kind: "finished", created_at: 1791853205 },
];
async function mockRecords(page: Page, records = [run(), run(B, "outcome_unknown")]) {
  await page.route("**/api/reproductions/catalog", route => route.fulfill({ status: 503, json: { error: "not_ready" } }));
  const writes: string[] = [];
  page.on("request", request => { if (request.url().includes("/api/runs") && request.method() !== "GET") writes.push(request.method()); });
  await page.route("**/api/runs**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/report")) return route.fulfill({ contentType: "application/json", body: reportBytes });
    if (path === "/api/runs") return route.fulfill({ json: { runs: records } });
    const record = records.find(item => path.endsWith(item.run_id));
    return route.fulfill(record ? { json: { run: record, events } } : { status: 404, json: { code: "not_found" } });
  });
  return writes;
}

test("运行空态提供真实入口，不填入合成运行", async ({ page }) => {
  const writes = await mockRecords(page, []);
  await page.goto("/workspace/tasks");
  await expect(page.getByRole("heading", { name: "还没有运行记录" })).toBeVisible();
  await expect(page.getByText(/从项目 CLI 使用 sandbox-check 开始记录/)).toBeVisible();
  await expect(page.getByText("完整交互预览", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /查看运行 / })).toHaveCount(0);
  expect(writes).toEqual([]);
});

test("选择记录与事件，刷新不覆盖选择", async ({ page }) => {
  const writes = await mockRecords(page);
  await page.goto("/workspace/tasks");
  await expect(page.getByRole("heading", { name: "选择一次运行" })).toBeVisible();
  await page.getByRole("button", { name: `查看运行 ${B}` }).click();
  await expect(page.getByText("当前记录来自已审核的合成故障场景，执行与状态是真实记录。")).toBeVisible();
  await expect(page.getByRole("button", { name: `查看运行 ${B}` })).toContainText("正常调用");
  const detail = page.getByRole("region", { name: "运行详情" });
  await expect(detail).toContainText(B);
  await expect(detail).toContainText("这不代表执行没有发生");
  await expect(detail).toContainText("执行已领取");
  await expect(page.getByRole("button", { name: "下载运行报告" })).toBeDisabled();
  await page.route("**/api/runs?limit=50", route => route.fulfill({ json: { runs: [run()] } }));
  await page.getByRole("button", { name: "刷新记录" }).click();
  await expect(detail).toContainText(B);
  await expect(page.getByRole("button", { name: `查看运行 ${B}` })).toHaveCount(0);
  expect(writes).toEqual([]);
});

test("服务错误与响应越界拒绝，重试恢复且不泄露错误正文", async ({ page }) => {
  await mockRecords(page);
  await page.route("**/api/runs?limit=50", route => route.fulfill({ status: 503, json: { error: "PRIVATE_SERVER_TEXT" } }));
  await page.goto("/workspace/tasks");
  await expect(page.locator(".run-error[role=alert]")).toContainText("暂时不可用");
  await expect(page.locator("body")).not.toContainText("PRIVATE_SERVER_TEXT");
  await page.route("**/api/runs?limit=50", route => route.fulfill({ json: { runs: [{ ...run(), lease_token: "PRIVATE_TOKEN" }] } }));
  await page.getByRole("button", { name: "重试读取列表" }).click();
  await expect(page.locator(".run-error[role=alert]")).toContainText("不符合数据约定");
  await expect(page.locator("body")).not.toContainText("PRIVATE_TOKEN");
  await page.route("**/api/runs?limit=50", route => route.fulfill({ contentType: "application/json", body: " ".repeat(1024 * 1024 + 1) }));
  await page.getByRole("button", { name: "重试读取列表" }).click();
  await expect(page.locator(".run-error[role=alert]")).toContainText("超过 1 MiB");
  await page.route("**/api/runs?limit=50", route => route.fulfill({ json: { runs: [run()] } }));
  await page.getByRole("button", { name: "重试读取列表" }).click();
  await expect(page.getByRole("button", { name: `查看运行 ${A}` })).toBeVisible();
});

test("重复ID、未知状态、越界日期与过多记录拒绝展示", async ({ page }) => {
  await mockRecords(page);
  for (const records of [[run(), run()], [{ ...run(), status: "guess_success" }], [{ ...run(), created_at: 1e30 }], Array.from({ length: 51 }, () => run())]) {
    await page.route("**/api/runs?limit=50", route => route.fulfill({ json: { runs: records } }));
    await page.goto("/workspace/tasks");
    await expect(page.locator(".run-error[role=alert]")).toContainText("不符合数据约定");
    await expect(page.getByRole("button", { name: /查看运行 / })).toHaveCount(0);
  }
});

test("详情错误关联、逆序事件及404不显示为成功", async ({ page }) => {
  await mockRecords(page);
  await page.goto("/workspace/tasks");
  await page.route(`**/api/runs/${A}`, route => route.fulfill({ json: { run: run(B), events } }));
  await page.getByRole("button", { name: `查看运行 ${A}` }).click();
  const detail = page.getByRole("region", { name: "运行详情" });
  await expect(detail).toContainText("不符合数据约定");
  await page.route(`**/api/runs/${A}`, route => route.fulfill({ json: { run: run(), events: [...events].reverse() } }));
  await page.getByRole("button", { name: "重试读取详情" }).click();
  await expect(detail).toContainText("不符合数据约定");
  await page.route(`**/api/runs/${A}`, route => route.fulfill({ status: 404, json: { code: "not_found" } }));
  await page.getByRole("button", { name: "重试读取详情" }).click();
  await expect(detail).toContainText("已不存在");
  await expect(page.getByRole("button", { name: "下载运行报告" })).toHaveCount(0);
});

test("切换选择与离页中止慢请求，不允许迟到详情覆盖", async ({ page }) => {
  await mockRecords(page);
  let release: () => void = () => {};
  const hold = new Promise<void>(resolve => { release = resolve; });
  let started: () => void = () => {};
  const received = new Promise<void>(resolve => { started = resolve; });
  await page.route(`**/api/runs/${A}`, async route => { started(); await hold; await route.fulfill({ json: { run: run(), events } }).catch(() => {}); });
  await page.goto("/workspace/tasks");
  await page.getByRole("button", { name: `查看运行 ${A}` }).click();
  await received;
  const aborted = page.waitForEvent("requestfailed", request => request.url().endsWith(A));
  await page.getByRole("button", { name: `查看运行 ${B}` }).click();
  release(); await aborted;
  const detail = page.getByRole("region", { name: "运行详情" });
  await expect(detail).toContainText(B);
  await expect(detail).not.toContainText(A);
  await page.route(`**/api/runs/${A}`, async () => new Promise<void>(() => {}));
  await page.getByRole("button", { name: `查看运行 ${A}` }).click();
  const leaving = page.waitForEvent("requestfailed", request => request.url().endsWith(A));
  await page.getByRole("link", { name: /诊断分析 开发中/ }).click();
  await leaving;
  await expect(page).toHaveURL(/workspace\/diagnosis/);
});

test("报告下载保留原始字节，摘要不符拒绝", async ({ page }) => {
  const writes = await mockRecords(page);
  await page.goto("/workspace/tasks");
  await page.getByRole("button", { name: `查看运行 ${A}` }).click();
  const nextDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载运行报告" }).click();
  const downloaded = await nextDownload;
  expect(downloaded.suggestedFilename()).toBe(`run-${A}.json`);
  const chunks: Buffer[] = [];
  for await (const chunk of (await downloaded.createReadStream())!) chunks.push(Buffer.from(chunk));
  expect(Buffer.concat(chunks).toString("utf8")).toBe(reportBytes);
  const downloads: string[] = [];
  page.on("download", item => downloads.push(item.suggestedFilename()));
  await page.route(`**/api/runs/${A}/report`, route => route.fulfill({ contentType: "application/json", body: reportBytes + "\n" }));
  await page.getByRole("button", { name: "下载运行报告" }).click();
  await expect(page.getByRole("region", { name: "运行详情" })).toContainText("摘要校验未通过");
  expect(downloads).toEqual([]);
  expect(writes).toEqual([]);
});

for (const width of [1440, 390]) {
  test(`记录详情 ${width}px 布局及可访问性`, async ({ page }) => {
    await mockRecords(page);
    await page.setViewportSize({ width, height: 960 });
    await page.emulateMedia({ colorScheme: width === 390 ? "dark" : "light", reducedMotion: "reduce" });
    await page.goto("/workspace/tasks");
    await page.getByRole("button", { name: `查看运行 ${A}` }).click();
    await page.getByText("技术详情：ID、版本与摘要", { exact: true }).click();
    await expect(page.getByRole("region", { name: "运行详情" })).toContainText("执行已结束");
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    expect(audit.violations.map(item => ({ id: item.id, nodes: item.nodes.map(node => node.target) }))).toEqual([]);
    await page.evaluate(() => { (document.activeElement as HTMLElement)?.blur(); window.scrollTo(0, 0); });
    await page.screenshot({ path: `../artifacts/p004-runs-${width}.png`, fullPage: true });
  });
}

test("独立负例：切换记录终止下载，迟到报告不能触发文件", async ({ page }) => {
  await mockRecords(page);
  let release: () => void = () => {};
  let started: () => void = () => {};
  const held = new Promise<void>(resolve => { release = resolve; });
  const received = new Promise<void>(resolve => { started = resolve; });
  await page.route(`**/api/runs/${A}/report`, async route => {
    started(); await held;
    await route.fulfill({contentType: "application/json", body: reportBytes}).catch(() => {});
  });
  const downloads: string[] = [];
  page.on("download", value => downloads.push(value.suggestedFilename()));
  await page.goto("/workspace/tasks");
  await page.getByRole("button", {name: `查看运行 ${A}`}).click();
  await page.getByRole("button", {name: "下载运行报告"}).click();
  await received;
  const aborted = page.waitForEvent("requestfailed", request => request.url().endsWith("/report"));
  await page.getByRole("button", {name: `查看运行 ${B}`}).click();
  await aborted;
  release();
  await expect(page.getByRole("region", {name: "运行详情"})).toContainText(B);
  await expect(page.getByRole("button", {name: "下载运行报告"})).toBeDisabled();
  await expect(page.getByRole("region", {name: "运行详情"})).not.toContainText("报告校验通过");
  expect(downloads).toEqual([]);
});
