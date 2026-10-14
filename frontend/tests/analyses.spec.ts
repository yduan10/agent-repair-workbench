import { test, expect, Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
const A = "10000000-0000-4000-8000-000000000001";
const B = "10000000-0000-4000-8000-000000000002";
const RUN = "20000000-0000-4000-8000-000000000001";
const SHA = "a".repeat(64);
const ref = { evidence_id: RUN, sha256: SHA };
function sample(id = A) {
  const event = { kind: "created", role: null, assessment: null, reason_code: null, tool: null, evidence_refs: [], call_id: null, request_sha256: null, input_reserved: null, output_reserved: null, reservation_sha256: null, known_input_tokens: null, known_output_tokens: null, error_code: null };
  const model = { ...event, role: "diagnosis", call_id: B, request_sha256: SHA, input_reserved: 200, output_reserved: 4096, reservation_sha256: SHA };
  return {
    summary: { schema_version: 1, task_id: id, summary_revision: 4, source_kind: "synthetic", state: { task_id: id, intent: "diagnose", phase: "finished", revision: 2, outcome: "outcome_unknown" }, started_at: "2026-10-14T00:00:00Z", finished_at: "2026-10-14T00:00:05Z", budget: { total_tokens: 2000000, output_tokens: 8192, model_calls: 12, tool_calls: 20, candidates: 2, timeout_seconds: 600 }, usage: { model_calls: 1, tool_calls: 0, reserved_tokens: 4296, known_input_tokens: 0, known_output_tokens: 0, usage_complete: false }, evidence_refs: [ref], execution_record_ids: [RUN], proposal_count: 0, model_config_sha256: SHA, cost_amount: null }, sha256: SHA,
    events: [event, { ...event, kind: "phase_changed" }, { ...model, kind: "model_started" }, { ...model, kind: "model_unknown", error_code: "MODEL_USAGE_UNKNOWN" }, { ...event, kind: "finished" }].map((e, i) => ({ revision: i, created_at: 1791936000 + i, sha256: SHA, event: e })),
  };
}
async function mock(page: Page, values = [sample(), sample(B)]) {
  const writes: string[] = [];
  page.on("request", request => { if (request.url().includes("/api/") && request.method() !== "GET") writes.push(request.method()); });
  await page.route("**/api/analyses**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/analyses") return route.fulfill({ json: { analyses: values.map(({ summary, sha256 }) => ({ summary, sha256 })) } });
    const found = values.find(v => path.endsWith(v.summary.task_id));
    return route.fulfill(found ? { json: found } : { status: 404, json: { error: "private" } });
  });
  return writes;
}
test("分析空态提供CLI且不制造任务或发起写请求", async ({ page }) => {
  const writes = await mock(page, []);
  await page.goto("/workspace/diagnosis");
  await expect(page.getByRole("heading", { name: "第一份分析，从真实执行开始。" })).toBeVisible();
  await expect(page.getByRole("button", { name: /查看分析 / })).toHaveCount(0);
  await expect(page.getByLabel("检查命令", { exact: true })).toContainText("--intent check_only");
  await expect(page.getByText("完整交互预览", { exact: true })).toHaveCount(0);
  expect(writes).toEqual([]);
});
test("真实形状摘要显示未知用量与运行关联，刷新保留选择", async ({ page }) => {
  const writes = await mock(page);
  await page.goto("/workspace/diagnosis");
  await page.getByRole("button", { name: `查看分析 ${A}` }).click();
  const detail = page.getByRole("region", { name: "分析详情" });
  await expect(detail).toContainText("4,296");
  await expect(detail).toContainText("2,000,000");
  await expect(detail).toContainText("费用未知");
  await expect(detail).toContainText("保留本次预留");
  await expect(detail.getByRole("link", { name: `查看运行 ${RUN}` })).toHaveAttribute("href", `/workspace/tasks?run=${RUN}`);
  await page.getByRole("button", { name: "刷新分析" }).click();
  await expect(page.getByRole("button", { name: `查看分析 ${A}` })).toHaveAttribute("aria-pressed", "true");
  expect(writes).toEqual([]);
});
test("切换分析取消迟到详情，旧结果不覆盖当前选择", async ({ page }) => {
  await mock(page);
  let release!: () => void;
  const wait = new Promise<void>(resolve => { release = resolve; });
  await page.route(`**/api/analyses/${A}`, async route => { await wait; await route.fulfill({ json: sample() }).catch(() => {}); });
  await page.goto("/workspace/diagnosis");
  await page.getByRole("button", { name: `查看分析 ${A}` }).click();
  await page.getByRole("button", { name: `查看分析 ${B}` }).click();
  await expect(page.getByRole("region", { name: "分析详情" })).toContainText("调用与预算");
  release();
  await page.getByText("摘要、证据与恢复说明", { exact: true }).click();
  await expect(page.getByRole("region", { name: "分析详情" })).toContainText(B);
  await expect(page.getByRole("button", { name: `查看分析 ${B}` })).toHaveAttribute("aria-pressed", "true");
});
test("服务错误、私有字段与错误关联拒绝，不回显正文", async ({ page }) => {
  await mock(page);
  await page.route("**/api/analyses?limit=50", route => route.fulfill({ status: 503, body: "PRIVATE_ERROR" }));
  await page.goto("/workspace/diagnosis");
  await expect(page.getByRole("alert").filter({ hasText: "暂时不可用" })).toBeVisible();
  await expect(page.locator("body")).not.toContainText("PRIVATE_ERROR");
  await page.unroute("**/api/analyses?limit=50");
  await page.getByRole("button", { name: "重试读取分析" }).click();
  for (const body of [{ ...sample(), raw_text: "PRIVATE_MODEL" }, { ...sample(), summary: { ...sample().summary, task_id: B } }, { ...sample(), events: [{ ...sample().events[0], event: { ...sample().events[0].event, error_code: "PRIVATE_ERROR" } }] }]) {
    await page.route(`**/api/analyses/${A}`, route => route.fulfill({ json: body }));
    await page.reload();
    await page.getByRole("button", { name: `查看分析 ${A}` }).click();
    await expect(page.getByRole("region", { name: "分析详情" }).getByRole("alert")).toContainText("不符合数据约定");
    await expect(page.locator("body")).not.toContainText("PRIVATE_MODEL");
    await expect(page.locator("body")).not.toContainText("PRIVATE_ERROR");
    await page.unroute(`**/api/analyses/${A}`);
  }
});
for (const theme of ["light", "dark"] as const) for (const width of [1280, 390]) {
  test(`分析账本 ${theme} ${width} 可读无溢出`, async ({ page }) => {
    await mock(page); await page.setViewportSize({ width, height: 900 }); await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
    await page.goto("/workspace/diagnosis"); await page.getByRole("button", { name: `查看分析 ${A}` }).click();
    await expect(page.getByRole("region", { name: "分析详情" })).toContainText("调用与预算");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    expect(audit.violations).toEqual([]);
    await page.screenshot({ path: `../artifacts/p005b-analysis-${theme}-${width}.png`, fullPage: true });
  });
}
test("wrong_type关联运行可按URL选中，Web目录不增加场景", async ({ page }) => {
  await page.route("**/api/reproductions/catalog", route => route.fulfill({ status: 503 }));
  const run = { run_id: RUN, attempt_id: A, status: "failed", version: 3, created_at: 1791936000, updated_at: 1791936005, lease_until: null, profile: "isolated-fixture", scenario: "wrong_type", config_sha256: SHA, case_sha256: SHA, report_sha256: null, executor_state: "absent" };
  await page.route("**/api/runs**", route => route.fulfill({ json: new URL(route.request().url()).pathname === "/api/runs" ? { runs: [run] } : { run, events: [] } }));
  await page.goto(`/workspace/tasks?run=${RUN}`);
  await expect(page.getByRole("region", { name: "运行详情" })).toContainText("输出类型不一致");
  await expect(page.getByRole("button", { name: `查看运行 ${RUN}` })).toHaveAttribute("aria-pressed", "true");
});
