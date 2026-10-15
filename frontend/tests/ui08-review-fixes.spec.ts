import { test, expect, Page } from "@playwright/test";
import { createHash } from "node:crypto";

/** UI-08 review fixes: each test pins one Defect P2 from docs/reviews/UI-08-*-review.md. */
const X = "10000000-0000-4000-8000-0000000000aa";
const PENDING = "10000000-0000-4000-8000-0000000000bb";
const A = "10000000-0000-4000-8000-000000000001";
const B = "10000000-0000-4000-8000-000000000002";
const ATTEMPT = "20000000-0000-4000-8000-000000000001";
const HASH = "a".repeat(64);

const analysisCatalog = (slot: { status: "available" | "busy"; task_id: string | null }) => ({
  schema_version: 1,
  cases: [{ id: "output_mismatch", label: "返回值类型错误" }, { id: "passing", label: "正常调用" }],
  intents: [
    { id: "check_only", label: "仅检查契约", requires_model: false },
    { id: "diagnose", label: "分析原因", requires_model: true },
    { id: "propose_repair", label: "生成修复建议", requires_model: true },
  ],
  model: { configured: false, reason: "MODEL_NOT_CONFIGURED" },
  slot,
});
const sidebar = (page: Page) => page.getByRole("complementary", { name: "工作区" });

test("外壳 D1：分析目录读取失败时环境状态不显示就绪，并列出无法读取", async ({ page }) => {
  await page.route("**/api/analysis-runs/catalog", route => route.fulfill({ status: 500, body: "" }));
  await page.goto("/workspace");
  const trigger = sidebar(page).locator(".env-trigger");
  await expect(trigger).not.toHaveText(/正在检查环境/);
  await expect(trigger).not.toContainText("环境就绪");
  await trigger.click();
  const pop = page.getByRole("dialog", { name: "本机环境状态" });
  await expect(pop).toContainText("模型与分析");
  await expect(pop).toContainText("无法读取");
});

for (const width of [1440, 390])
  test(`外壳 D2：环境弹出层不超出侧栏（${width}）`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/workspace");
    if (width < 900) await page.getByRole("button", { name: "打开导航" }).click();
    await sidebar(page).locator(".env-trigger").click();
    const pop = page.getByRole("dialog", { name: "本机环境状态" });
    await expect(pop.getByRole("button", { name: "重新检查" })).toBeVisible();
    const [popBox, navBox] = await Promise.all([pop.boundingBox(), sidebar(page).boundingBox()]);
    expect(popBox!.x + popBox!.width).toBeLessThanOrEqual(navBox!.x + navBox!.width + 0.5);
    expect(await sidebar(page).evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
  });

test("外壳 D3：手机抽屉关闭时不可聚焦，打开后焦点进入抽屉，Esc 还给按钮", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/workspace");
  const aside = page.locator("aside#workspace-nav");
  await expect(aside).toHaveAttribute("inert", "");
  await page.keyboard.press("Tab");
  for (let i = 0; i < 4; i++) {
    await page.keyboard.press("Tab");
    expect(await page.evaluate(() => !!document.activeElement?.closest("#workspace-nav"))).toBe(false);
  }
  await page.getByRole("button", { name: "打开导航" }).click();
  await expect(aside).not.toHaveAttribute("inert", "");
  await expect(page.locator("main")).toHaveAttribute("inert", "");
  expect(await page.evaluate(() => !!document.activeElement?.closest("#workspace-nav"))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "打开导航" })).toBeFocused();
  await expect(aside).toHaveAttribute("inert", "");
});

test("外壳 D4：部分数据源失败时总览不显示空状态", async ({ page }) => {
  await page.route("**/api/runs?limit=50", route => route.fulfill({ status: 500, body: "" }));
  await page.route("**/api/repairs?limit=50", route => route.fulfill({ status: 500, body: "" }));
  await page.route("**/api/analyses?limit=50", route => route.fulfill({ json: { analyses: [] } }));
  await page.goto("/workspace");
  await expect(page.getByText("复现、修复记录暂时无法读取")).toBeVisible();
  await expect(page.getByText("还没有记录", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "运行第一次复现" })).toHaveCount(0);
});

test("外壳 D5：确认框在路由变化后关闭，确认不会作用于已离开的页面", async ({ page }) => {
  await page.goto("/workspace");
  await sidebar(page).getByRole("link", { name: "调用检查", exact: true }).click();
  await expect(page.locator(".cm-content")).toBeVisible();
  await page.getByRole("textbox", { name: "调用证据", exact: true }).fill('{"local_draft":true}');
  await sidebar(page).getByRole("link", { name: "复现", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "离开调用检查？" });
  await expect(dialog).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/workspace$/);
  await expect(dialog).toHaveCount(0);
  await expect(page).not.toHaveURL(/\/workspace\/tasks/);
});

test("分析 AN-01：环境轮询遇到 429 不会用旧的忙碌状态覆盖发起面板", async ({ page }) => {
  let mode: "busy" | "available" | "refuse" = "busy";
  await page.route("**/api/analysis-runs/catalog", route => {
    if (mode === "refuse") return route.fulfill({ status: 429, json: { error: "analysis_busy" } });
    const json = analysisCatalog(mode === "busy" ? { status: "busy", task_id: X } : { status: "available", task_id: null });
    if (mode === "busy") mode = "available"; // the first read (shell) sees busy, later reads see the slot freed
    return route.fulfill({ json });
  });
  await page.route("**/api/analyses**", route => route.fulfill(new URL(route.request().url()).pathname === "/api/analyses" ? { json: { analyses: [] } } : { status: 404, json: {} }));
  await page.goto("/workspace/diagnosis");
  const start = page.getByRole("button", { name: "开始分析", exact: true });
  await expect(start).toBeEnabled({ timeout: 8000 });
  mode = "refuse";
  const refused = page.waitForResponse(r => r.url().endsWith("/api/analysis-runs/catalog") && r.status() === 429);
  await page.evaluate(() => window.dispatchEvent(new Event("awb-environment-refresh")));
  await refused;
  await page.waitForTimeout(300);
  await expect(start).toBeEnabled();
  await expect(page.getByText("已有分析在运行")).toHaveCount(0);
});

test("分析 AN-02：服务端没有待确认请求时如实说明，可放弃且不发写请求", async ({ page }) => {
  const writes: string[] = [];
  page.on("request", r => { if (r.url().includes("/api/") && r.method() !== "GET") writes.push(r.url()); });
  await page.addInitScript(id => {
    if (!sessionStorage.getItem("awb-test-seeded")) {
      sessionStorage.setItem("awb-pending-analysis-v1", JSON.stringify({ request_id: id, case_name: "output_mismatch", intent: "check_only" }));
      sessionStorage.setItem("awb-test-seeded", "1");
    }
  }, PENDING);
  await page.route("**/api/analyses**", route => route.fulfill(new URL(route.request().url()).pathname === "/api/analyses" ? { json: { analyses: [] } } : { status: 404, json: {} }));
  await page.goto("/workspace/diagnosis");
  await expect(page.getByText("服务端没有这次提交的记录")).toBeVisible();
  await expect(page.getByText(/正在查询|记录或报告已不存在/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "用同一 ID 重新提交" })).toBeVisible();
  await expect(page.getByText("如果上次没有送达，这次会开始分析")).toBeVisible();
  await page.getByRole("button", { name: "放弃这次提交" }).click();
  await page.getByRole("dialog", { name: "放弃这次提交？" }).getByRole("button", { name: "放弃" }).click();
  await expect(page.getByRole("button", { name: "用同一 ID 重新提交" })).toHaveCount(0);
  expect(await page.evaluate(() => sessionStorage.getItem("awb-pending-analysis-v1"))).toBeNull();
  expect(writes).toEqual([]);
});

function runRecords(scenario: string, status: string) {
  const report = {
    sandbox_report_version: 1, record_id: A, run_id: ATTEMPT,
    mcp: {
      mcp_report_version: 1, invocation_id: ATTEMPT, adapter_outcome: "completed",
      source: {
        kind: "mcp_sdk_normalized", association: "sdk_dispatch", wire_json_integrity: "not_checked", sdk_version: "2.3.0", adapter_version: "1",
        protocol_version: "2025-11-25", profile: "isolated-fixture", config_sha256: HASH, case_sha256: HASH,
        server_code_sha256: HASH, server_dependencies_sha256: null, tool_schema_sha256: HASH, server_revision: null, source_tree_sha256: null,
      },
      contract_report: { schema_version: 1, checker_version: "0.1.0", evidence_sha256: HASH, status: "failed", checks: { input: "passed", output: "failed" }, findings: [{ code: "output_schema_violation", phase: "output", instance_path: "/result/structured_content/count", schema_path: "/properties/count/type" }], findings_truncated: false },
      preflight_findings: [], content_summary: [], elapsed_ms: 20,
    },
    execution: { image_id: `sha256:${HASH}`, source_sha256: HASH, scenario, seed: 0, policy: "offline-readonly-v1", stdout_bytes: 42, stderr_bytes: 0, frames: 3, error: null, cleanup: "removed", container_exit_code: 0, oom_killed: false },
  };
  const bytes = JSON.stringify(report);
  const run = (id: string) => ({
    run_id: id, attempt_id: ATTEMPT, status, version: 3, created_at: 1791853200, updated_at: 1791853205, lease_until: null,
    profile: "isolated-fixture", scenario, config_sha256: HASH, case_sha256: HASH, report_sha256: createHash("sha256").update(bytes).digest("hex"), executor_state: null,
  });
  return { bytes, records: [run(A), run(B)] };
}
async function mockRuns(page: Page, scenario: string, status: string) {
  const { bytes, records } = runRecords(scenario, status);
  const events = [
    { event_id: "30000000-0000-4000-8000-000000000001", version: 1, kind: "created", created_at: 1791853200 },
    { event_id: "30000000-0000-4000-8000-000000000003", version: 3, kind: "finished", created_at: 1791853205 },
  ];
  await page.route("**/api/reproductions/catalog", route => route.fulfill({ status: 503, json: { error: "not_ready" } }));
  await page.route("**/api/runs**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/report")) return route.fulfill({ contentType: "application/json", body: bytes });
    if (path === "/api/runs") return route.fulfill({ json: { runs: records } });
    const record = records.find(item => path.endsWith(item.run_id));
    return route.fulfill(record ? { json: { run: record, events } } : { status: 404, json: {} });
  });
}

test("复现 D2：终端场景不断言与预期不符", async ({ page }) => {
  await mockRuns(page, "wrong_type", "failed");
  await page.goto(`/workspace/tasks?run=${A}`);
  const detail = page.locator(".run-view");
  await expect(detail).toContainText("网页不判断");
  await expect(detail).not.toContainText("与预期不符");
  await expect(detail).not.toContainText("运行环境出错");
});

test("复现 D1：手机端返回列表不写入 hash，后退与选中记录一致", async ({ page }) => {
  await mockRuns(page, "pass", "succeeded");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/workspace/tasks?run=${A}`);
  await page.getByRole("button", { name: "返回列表" }).click();
  await expect(page.locator("#run-list-heading")).toBeFocused();
  expect(new URL(page.url()).hash).toBe("");
  await page.locator(`tr[data-run-id="${B}"]`).getByRole("link").click();
  await expect(page).toHaveURL(new RegExp(`run=${B}`));
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`run=${A}$`));
  await expect(page.locator(`tr[data-run-id="${A}"]`)).toHaveAttribute("aria-selected", "true");
});
