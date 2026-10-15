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
const row = (page: Page, id: string) => page.locator(`tr[data-run-id="${id}"]`);
const open = (page: Page, id: string) => row(page, id).getByRole("link").click();

test("运行空态提供真实入口，不填入合成运行", async ({ page }) => {
  const writes = await mockRecords(page, []);
  await page.goto("/workspace/tasks");
  await expect(page.getByRole("heading", { name: "还没有运行记录" })).toBeVisible();
  await expect(page.getByText(/也可以在终端运行 sandbox-check/)).toBeVisible();
  await expect(page.getByText("完整交互预览", { exact: true })).toHaveCount(0);
  await expect(page.locator("tr[data-run-id]")).toHaveCount(0);
  await expect(page.getByRole("region", { name: "运行详情" })).toHaveCount(0);
  expect(writes).toEqual([]);
});

test("自动选中最新记录，选择写入 URL，刷新不覆盖选择", async ({ page }) => {
  const writes = await mockRecords(page);
  await page.goto("/workspace/tasks");
  const detail = page.getByRole("region", { name: "运行详情" });
  await expect(row(page, A)).toHaveAttribute("aria-selected", "true");
  await expect(detail.getByRole("heading", { level: 2 })).toHaveText("正常调用");
  await expect(page).toHaveURL(new RegExp(`run=${A}`));
  await open(page, B);
  await expect(page).toHaveURL(new RegExp(`\\?run=${B}$`));
  await expect(row(page, B)).toHaveAttribute("aria-selected", "true");
  await expect(row(page, B).getByRole("link")).toHaveAttribute("aria-current", "true");
  await expect(row(page, B)).toContainText("正常调用");
  await expect(row(page, B)).toContainText("结果未知");
  await expect(detail).toContainText(B);
  await expect(detail).toContainText("发送后没有收到结果，无法确认工具是否执行；不会自动重试。");
  await expect(detail.getByText("无法确认工具是否执行", { exact: false })).toHaveCount(1);
  await expect(detail).toContainText("开始运行");
  await expect(page.getByRole("button", { name: "下载报告" })).toBeDisabled();
  await page.goBack();
  await expect(row(page, A)).toHaveAttribute("aria-selected", "true");
  await page.goForward();
  await expect(row(page, B)).toHaveAttribute("aria-selected", "true");
  await page.route("**/api/runs?limit=50", route => route.fulfill({ json: { runs: [run()] } }));
  await page.locator(".page-header").getByRole("button", { name: "刷新" }).click();
  await expect(detail).toContainText(B);
  await expect(row(page, B)).toHaveCount(0);
  await page.reload();
  await expect(detail).toContainText(B);
  expect(writes).toEqual([]);
});

test("搜索与状态筛选写入 URL，方向键切换选择", async ({ page }) => {
  await mockRecords(page);
  await page.goto("/workspace/tasks?status=outcome_unknown");
  await expect(page.getByLabel("状态筛选")).toHaveValue("outcome_unknown");
  await expect(row(page, A)).toHaveCount(0);
  await expect(row(page, B)).toHaveAttribute("aria-selected", "true");
  await page.getByLabel("状态筛选").selectOption("");
  await expect(page).not.toHaveURL(/status=/);
  await page.getByLabel("搜索运行").fill("zzz");
  await expect(page).toHaveURL(/q=zzz/);
  await expect(page.getByRole("heading", { name: "没有符合条件的运行" })).toBeVisible();
  await page.getByRole("button", { name: "清除筛选" }).click();
  await expect(page).not.toHaveURL(/q=/);
  await row(page, A).getByRole("link").focus();
  await page.keyboard.press("ArrowDown");
  await expect(row(page, B)).toHaveAttribute("aria-selected", "true");
  await expect(row(page, B).getByRole("link")).toBeFocused();
  await expect(page).toHaveURL(new RegExp(`run=${B}`));
  await page.keyboard.press("ArrowUp");
  await expect(row(page, A)).toHaveAttribute("aria-selected", "true");
});

test("服务错误与响应越界拒绝，重试恢复且不泄露错误正文", async ({ page }) => {
  await mockRecords(page);
  await page.route("**/api/runs?limit=50", route => route.fulfill({ status: 503, json: { error: "PRIVATE_SERVER_TEXT" } }));
  await page.goto("/workspace/tasks");
  const list = page.getByRole("region", { name: "运行记录" });
  await expect(list.getByRole("alert")).toContainText("暂时不可用");
  await expect(page.locator("body")).not.toContainText("PRIVATE_SERVER_TEXT");
  await page.route("**/api/runs?limit=50", route => route.fulfill({ json: { runs: [{ ...run(), lease_token: "PRIVATE_TOKEN" }] } }));
  await list.getByRole("button", { name: "重试" }).click();
  await expect(list.getByRole("alert")).toContainText("不符合数据约定");
  await expect(page.locator("body")).not.toContainText("PRIVATE_TOKEN");
  await page.route("**/api/runs?limit=50", route => route.fulfill({ contentType: "application/json", body: " ".repeat(1024 * 1024 + 1) }));
  await list.getByRole("button", { name: "重试" }).click();
  await expect(list.getByRole("alert")).toContainText("超过 1 MiB");
  await page.route("**/api/runs?limit=50", route => route.fulfill({ json: { runs: [run()] } }));
  await list.getByRole("button", { name: "重试" }).click();
  await expect(row(page, A)).toBeVisible();
  await expect(list.getByRole("alert")).toHaveCount(0);
});

test("重复ID、未知状态、越界日期与过多记录拒绝展示", async ({ page }) => {
  await mockRecords(page);
  for (const records of [[run(), run()], [{ ...run(), status: "guess_success" }], [{ ...run(), created_at: 1e30 }], Array.from({ length: 51 }, () => run())]) {
    await page.route("**/api/runs?limit=50", route => route.fulfill({ json: { runs: records } }));
    await page.goto("/workspace/tasks");
    await expect(page.getByRole("region", { name: "运行记录" }).getByRole("alert")).toContainText("不符合数据约定");
    await expect(page.locator("tr[data-run-id]")).toHaveCount(0);
  }
});

test("详情错误关联、逆序事件及404不显示为成功", async ({ page }) => {
  await mockRecords(page);
  await page.route(`**/api/runs/${A}`, route => route.fulfill({ json: { run: run(B), events } }));
  await page.goto(`/workspace/tasks?run=${A}`);
  const detail = page.getByRole("region", { name: "运行详情" });
  await expect(detail.getByRole("alert")).toContainText("不符合数据约定");
  await page.route(`**/api/runs/${A}`, route => route.fulfill({ json: { run: run(), events: [...events].reverse() } }));
  await detail.getByRole("button", { name: "重试" }).click();
  await expect(detail.getByRole("alert")).toContainText("不符合数据约定");
  await page.route(`**/api/runs/${A}`, route => route.fulfill({ status: 404, json: { code: "not_found" } }));
  await detail.getByRole("button", { name: "重试" }).click();
  await expect(detail).toContainText("已不存在");
  await expect(page.getByRole("button", { name: "下载报告" })).toHaveCount(0);
  await expect(detail.getByText("调用成功")).toHaveCount(0);
});

test("切换选择与离页中止慢请求，不允许迟到详情覆盖", async ({ page }) => {
  await mockRecords(page);
  let release: () => void = () => {};
  const hold = new Promise<void>(resolve => { release = resolve; });
  let started: () => void = () => {};
  const received = new Promise<void>(resolve => { started = resolve; });
  await page.route(`**/api/runs/${A}`, async route => { started(); await hold; await route.fulfill({ json: { run: run(), events } }).catch(() => {}); });
  await page.goto(`/workspace/tasks?run=${B}`);
  await expect(page.getByRole("region", { name: "运行详情" })).toContainText(B);
  await open(page, A);
  await received;
  await expect(row(page, A)).toHaveAttribute("aria-selected", "true");
  const aborted = page.waitForEvent("requestfailed", request => request.url().endsWith(A));
  // The switch aborts A before B is requested; release A only after that point.
  const switched = page.waitForRequest(request => request.url().endsWith(B));
  await open(page, B);
  await switched; release(); await aborted;
  const detail = page.getByRole("region", { name: "运行详情" });
  await expect(detail).toContainText(B);
  await expect(detail).not.toContainText(A);
  await page.route(`**/api/runs/${A}`, async () => new Promise<void>(() => {}));
  await open(page, A);
  await expect(detail.getByRole("status").filter({ hasText: "正在读取运行详情" })).toBeAttached();
  const leaving = page.waitForEvent("requestfailed", request => request.url().endsWith(A));
  await page.getByRole("navigation", { name: "产品模块" }).getByRole("link", { name: "分析", exact: true }).click();
  await leaving;
  await expect(page).toHaveURL(/workspace\/diagnosis/);
});

test("报告下载保留原始字节，摘要不符拒绝", async ({ page }) => {
  const writes = await mockRecords(page);
  await page.goto("/workspace/tasks");
  await open(page, A);
  const detail = page.getByRole("region", { name: "运行详情" });
  await expect(detail.locator(".report-verified")).toBeVisible();
  await expect(detail.getByRole("heading", { name: "正常调用通过" })).toBeVisible();
  const nextDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载报告" }).click();
  const downloaded = await nextDownload;
  expect(downloaded.suggestedFilename()).toBe(`run-${A}.json`);
  const chunks: Buffer[] = [];
  for await (const chunk of (await downloaded.createReadStream())!) chunks.push(Buffer.from(chunk));
  expect(Buffer.concat(chunks).toString("utf8")).toBe(reportBytes);
  await expect(page.locator(".toast-region")).toContainText("已开始下载报告");
  const downloads: string[] = [];
  page.on("download", item => downloads.push(item.suggestedFilename()));
  await page.route(`**/api/runs/${A}/report`, route => route.fulfill({ contentType: "application/json", body: reportBytes + "\n" }));
  await page.getByRole("button", { name: "下载报告" }).click();
  await expect(detail).toContainText("摘要校验未通过");
  await expect(detail.locator(".report-verified")).toHaveCount(0);
  expect(downloads).toEqual([]);
  expect(writes).toEqual([]);
});

for (const width of [1440, 390]) {
  test(`记录详情 ${width}px 布局及可访问性`, async ({ page }) => {
    await mockRecords(page);
    await page.setViewportSize({ width, height: 960 });
    await page.emulateMedia({ colorScheme: width === 390 ? "dark" : "light", reducedMotion: "reduce" });
    await page.goto("/workspace/tasks");
    await open(page, A);
    const detail = page.getByRole("region", { name: "运行详情" });
    await detail.getByText("技术详情", { exact: true }).click();
    await expect(detail).toContainText("运行结束");
    await expect(detail).toContainText("offline-readonly-v1");
    await expect(detail).toContainText("耗时 5.0 秒");
    if (width === 390) {
      const listBox = (await page.getByRole("region", { name: "运行记录" }).boundingBox())!;
      const detailBox = (await detail.boundingBox())!;
      expect(listBox.y).toBeLessThan(detailBox.y);
      await expect(detail.getByRole("button", { name: "返回列表" })).toBeVisible();
    } else {
      await expect(detail.getByRole("button", { name: "返回列表" })).toBeHidden();
    }
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
  await page.goto(`/workspace/tasks?run=${A}`);
  await page.getByRole("button", {name: "下载报告"}).click();
  await received;
  await expect(page.getByRole("button", {name: "正在下载…"})).toBeDisabled();
  const aborted = page.waitForEvent("requestfailed", request => request.url().endsWith("/report"));
  const switched = page.waitForRequest(request => request.url().endsWith(B));
  await open(page, B);
  await switched; await aborted;
  release();
  await expect(page.getByRole("region", {name: "运行详情"})).toContainText(B);
  await expect(page.getByRole("button", {name: "下载报告"})).toBeDisabled();
  await expect(page.locator(".toast-region")).not.toContainText("已开始下载");
  expect(downloads).toEqual([]);
});

for (const variant of ["expected", "environment", "unconfirmed", "wrong-scenario", "missing-finding", "unverified"] as const) {
  test(`复现结论区分预设故障与异常：${variant}`, async ({ page }) => {
    const value = structuredClone(report);
    value.execution.scenario = "tool_error";
    value.mcp.adapter_outcome = "tool_error";
    value.mcp.contract_report.status = "failed";
    value.mcp.contract_report.checks.output = "skipped";
    // These fixtures exercise the HTTP report contract, not a real tool run.
    const payload = { ...value, mcp: { ...value.mcp, contract_report: { ...value.mcp.contract_report, findings: [{ code: "tool_error", phase: "result", instance_path: "/result", schema_path: "" }] } } };
    if (variant === "environment") Object.assign(payload.execution, { error: "runner_unavailable" });
    if (variant === "unconfirmed") payload.execution.cleanup = "unconfirmed";
    if (variant === "wrong-scenario") payload.execution.scenario = "pass";
    if (variant === "missing-finding") payload.mcp.contract_report.findings = [];
    const bytes = JSON.stringify(payload);
    const record = { ...run(), status: "failed", scenario: "tool_error", report_sha256: createHash("sha256").update(bytes).digest("hex") };
    await mockRecords(page, [record]);
    await page.route(`**/api/runs/${A}/report`, route => route.fulfill({ contentType: "application/json", body: bytes + (variant === "unverified" ? " " : "") }));
    await page.goto(`/workspace/tasks?run=${A}`);
    const detail = page.getByRole("region", { name: "运行详情" });
    await expect(detail.locator(".run-status-badge")).toHaveText("调用失败");
    if (variant === "expected") {
      await expect(detail.getByRole("heading", { name: "已复现工具错误" })).toBeVisible();
      await expect(detail).toContainText("判定为不通过；容器已清理");
      await expect(detail.locator(".finding-list")).toContainText("tool_error");
      await expect(detail.locator(".finding-list .path-trail")).toHaveAttribute("title", "/result");
      await expect(detail.getByRole("link", { name: "发起分析" })).toHaveAttribute("href", "/workspace/diagnosis");
    } else {
      await expect(detail.getByRole("heading", { name: "已复现工具错误" })).toHaveCount(0);
      await expect(detail).toContainText(variant === "unverified" ? "摘要校验未通过" : variant === "wrong-scenario" ? "报告与运行不匹配" : variant === "missing-finding" ? "与预期不符" : "运行环境出错");
    }
  });
}
