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
const row = (page: Page, id: string) => page.locator(`.an-row[data-analysis-id="${id}"]`);
test("分析空态提供CLI且不制造任务或发起写请求", async ({ page }) => {
  const writes = await mock(page, []);
  await page.goto("/workspace/diagnosis");
  await expect(page.getByRole("heading", { name: "还没有分析记录" })).toBeVisible();
  await expect(page.locator(".an-row")).toHaveCount(0);
  await page.getByRole("navigation", { name: "分析列表" }).getByRole("button", { name: "在终端运行" }).click();
  await expect(page.locator("#analysis-cli-toggle")).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator("#analysis-cli-toggle")).toBeFocused();
  await expect(page.getByLabel("初始化命令", { exact: true })).toContainText("runs init");
  await expect(page.getByLabel("分析命令", { exact: true })).toContainText("agent-workbench analyze --case");
  await expect(page.getByText("完整交互预览", { exact: true })).toHaveCount(0);
  expect(writes).toEqual([]);
});
test("真实形状摘要显示未知用量与运行关联，刷新保留选择", async ({ page }) => {
  const writes = await mock(page);
  await page.goto("/workspace/diagnosis");
  await row(page, A).click();
  const detail = page.getByRole("region", { name: "分析详情" });
  await expect(detail).toContainText("4,296");
  await expect(detail.getByRole("meter")).toBeVisible();
  await expect(detail).toContainText("2,000,000");
  await expect(detail.getByText("未配置单价")).toHaveCount(1);
  await expect(detail.getByText(/用量待确认/)).toHaveCount(1);
  await expect(detail.locator(`a[href="/workspace/tasks?run=${RUN}"]`)).toBeVisible();
  await page.getByRole("button", { name: "刷新", exact: true }).click();
  await expect(row(page, A)).toHaveAttribute("aria-current", "true");
  expect(writes).toEqual([]);
});
test("桌面端无选择时自动打开最新记录，手机端先显示列表", async ({ page }) => {
  await mock(page);
  await page.goto("/workspace/diagnosis");
  await expect(page).toHaveURL(new RegExp(`analysis=${A}`));
  await expect(row(page, A)).toHaveAttribute("aria-current", "true");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/workspace/diagnosis");
  await expect(row(page, A)).toBeVisible();
  await expect(page).not.toHaveURL(/analysis=/);
  await expect(page.getByRole("region", { name: "分析详情" })).toBeHidden();
  await row(page, B).click();
  await expect(page).toHaveURL(new RegExp(`analysis=${B}`));
  const list = await page.getByRole("navigation", { name: "分析列表" }).boundingBox();
  const detail = await page.getByRole("region", { name: "分析详情" }).boundingBox();
  expect(list!.y).toBeLessThan(detail!.y);
});
test("切换分析取消迟到详情，旧结果不覆盖当前选择", async ({ page }) => {
  await mock(page);
  let release!: () => void;
  const wait = new Promise<void>(resolve => { release = resolve; });
  await page.route(`**/api/analyses/${A}`, async route => { await wait; await route.fulfill({ json: sample() }).catch(() => {}); });
  await page.goto("/workspace/diagnosis");
  await row(page, A).click();
  await row(page, B).click();
  await expect(page.getByRole("region", { name: "分析详情" })).toContainText("用量与预算");
  release();
  await page.getByText("技术详情", { exact: true }).click();
  await expect(page.getByRole("region", { name: "分析详情" })).toContainText(B);
  await expect(row(page, B)).toHaveAttribute("aria-current", "true");
});
test("服务错误、私有字段与错误关联拒绝，不回显正文", async ({ page }) => {
  await mock(page);
  await page.route("**/api/analyses?limit=50", route => route.fulfill({ status: 503, body: "PRIVATE_ERROR" }));
  await page.goto("/workspace/diagnosis");
  await expect(page.getByRole("alert").filter({ hasText: "暂时不可用" })).toBeVisible();
  await expect(page.locator("body")).not.toContainText("PRIVATE_ERROR");
  await page.unroute("**/api/analyses?limit=50");
  await page.getByRole("button", { name: "重试", exact: true }).click();
  for (const body of [{ ...sample(), raw_text: "PRIVATE_MODEL" }, { ...sample(), summary: { ...sample().summary, task_id: B } }, { ...sample(), events: [{ ...sample().events[0], event: { ...sample().events[0].event, error_code: "PRIVATE_ERROR" } }] }]) {
    await page.route(`**/api/analyses/${A}`, route => route.fulfill({ json: body }));
    await page.reload();
    await row(page, A).click();
    await expect(page.getByRole("region", { name: "分析详情" }).getByRole("alert")).toContainText("不符合数据约定");
    await expect(page.locator("body")).not.toContainText("PRIVATE_MODEL");
    await expect(page.locator("body")).not.toContainText("PRIVATE_ERROR");
    await page.unroute(`**/api/analyses/${A}`);
  }
});
for (const theme of ["light", "dark"] as const) for (const width of [1280, 390]) {
  test(`分析账本 ${theme} ${width} 可读无溢出`, async ({ page }) => {
    await mock(page); await page.setViewportSize({ width, height: 900 }); await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
    await page.goto("/workspace/diagnosis"); await row(page, A).click();
    await expect(page.getByRole("region", { name: "分析详情" })).toContainText("用量与预算");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    expect(audit.violations).toEqual([]);
    await page.screenshot({ path: `../artifacts/ui08-analysis-${theme}-${width}.png`, fullPage: true });
  });
}

test("紧凑分析保留可操作入口，日志筛选分页与完整下载", async ({ page }) => {
  const value = sample();
  const base = value.events[0];
  value.events = [...value.events.slice(0, 4), ...Array.from({ length: 37 }, () => ({ ...base, event: { ...base.event, kind: "phase_changed" } })), value.events[4]].map((item, revision) => ({ ...item, revision }));
  value.summary.summary_revision = value.events.length - 1;
  await mock(page, [value]);
  await page.goto("/workspace/diagnosis");
  await row(page, A).click();
  const detail = page.getByRole("region", { name: "分析详情" });
  await expect(detail.getByRole("heading", { name: "结果未知", exact: true })).toBeVisible();
  await expect(detail.getByText(/结果未确认/)).toBeVisible();
  await expect(detail.locator(".an-tech").first()).not.toHaveAttribute("open", "");
  const log = detail.locator(".an-events");
  await expect(log.locator(".an-log > ol > li")).toHaveCount(2);
  await expect(log.locator('.an-log li[data-level="error"]')).toContainText("MODEL_USAGE_UNKNOWN");
  await log.getByLabel("事件", { exact: true }).selectOption("all");
  const seen: string[] = [];
  for (let pageIndex = 0; pageIndex < 4; pageIndex++) {
    seen.push(...await log.locator(".an-log-index").allTextContents());
    expect(await log.locator(".an-log").evaluate(el => el.clientHeight)).toBeLessThanOrEqual(390);
    if (pageIndex < 3) {
      const scroll = log.locator(".an-log");
      await scroll.evaluate(el => { el.scrollTop = el.scrollHeight; });
      await log.getByRole("button", { name: "下一页" }).click();
      await expect.poll(() => scroll.evaluate(el => el.scrollTop)).toBe(0);
    }
  }
  expect(seen).toEqual(value.events.map((_, i) => String(i + 1)));
  await expect(log.getByRole("button", { name: "下一页" })).toBeDisabled();
  await log.getByLabel("角色", { exact: true }).selectOption("repair");
  await expect(log.getByText("没有匹配的事件。", { exact: false })).toBeVisible();
  await log.getByRole("button", { name: "显示全部事件" }).click();
  await expect(log.getByRole("button", { name: "上一页" })).toBeDisabled();
  const downloaded = page.waitForEvent("download");
  await detail.getByRole("button", { name: "下载分析" }).click();
  const chunks: Buffer[] = [];
  for await (const chunk of (await (await downloaded).createReadStream())!) chunks.push(Buffer.from(chunk));
  expect(JSON.parse(Buffer.concat(chunks).toString()).events).toEqual(value.events);
});

test("分析选择可刷新与后退，筛选不改写记录，终端入口可收起", async ({ page }) => {
  const writes = await mock(page);
  await page.goto("/workspace/diagnosis");
  await row(page, A).click();
  await row(page, B).click();
  await expect(page).toHaveURL(new RegExp(`analysis=${B}`));
  await page.reload();
  await expect(row(page, B)).toHaveAttribute("aria-current", "true");
  await page.goBack();
  await expect(row(page, A)).toHaveAttribute("aria-current", "true");
  await page.getByRole("searchbox", { name: "搜索分析记录" }).fill("找不到");
  await expect(page.locator(".an-row")).toHaveCount(0);
  await page.getByRole("button", { name: "清除筛选" }).click();
  await expect(page.locator(".an-row")).toHaveCount(2);
  await expect(page.getByRole("button", { name: "新建分析", exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "角色与工具接口" })).toHaveAttribute("href", "/workspace/connections#contracts");
  const toggle = page.locator("#analysis-cli-toggle");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByLabel("分析命令", { exact: true })).toBeVisible();
  await expect(page.getByLabel("核对命令", { exact: true }).first()).toContainText("analyses reconcile");
  await expect(toggle).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#analysis-cli")).toBeHidden();
  expect(writes).toEqual([]);
});
