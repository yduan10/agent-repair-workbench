import { test, expect } from "@playwright/test";

// Browser calls the disposable real API through a test proxy, just as Next rewrites
// do. No response bodies, model replies or database records are mocked here.
test.beforeEach(async ({ page }) => {
  test.skip(process.env.AWB_CONSOLE_LIVE !== "1", "Requires a separately initialized disposable API on 8034.");
  expect(process.env.AWB_STATE_DIR).toMatch(/awb-console-live-[^/]+\/state$/);
  await page.route("**/api/**", async route => {
    const incoming = new URL(route.request().url());
    const response = await route.fetch({ url: `http://127.0.0.1:8034${incoming.pathname}${incoming.search}` });
    await route.fulfill({ response });
  });
});
test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "ignoreErrors" }); });

test("真实网页契约检查、证据阅读与刷新不重复提交", async ({ page, request }) => {
  const starts: string[] = [];
  page.on("request", req => { if (req.method() === "POST" && new URL(req.url()).pathname === "/api/analysis-runs") starts.push(req.postData()!); });
  await page.goto("/workspace/diagnosis");
  await page.getByLabel("目标", { exact: true }).selectOption("check_only");
  // History may already show a finished task. Bind every assertion to this POST's accepted ID.
  const accepted = page.waitForResponse(res => res.request().method() === "POST" && new URL(res.url()).pathname === "/api/analysis-runs");
  await page.getByRole("button", { name: "开始分析", exact: true }).click();
  const response = await accepted;
  expect(response.ok(), `analysis admission HTTP ${response.status()}`).toBeTruthy();
  const acceptance = await response.json();
  const id = JSON.parse(starts[0]).request_id;
  expect(acceptance.task_id).toBe(id);
  expect(acceptance.summary.task_id).toBe(id);
  await expect(page).toHaveURL(new RegExp(`analysis=${id}`));
  await expect(page.getByRole("region", { name: "实时执行事件" })).toContainText("分析已结束", { timeout: 20000 });
  let data: { summary: { task_id: string; state: { outcome: string }; usage: { model_calls: number } } };
  await expect.poll(async () => {
    const result = await request.get(`http://127.0.0.1:8034/api/analyses/${id}`);
    if ([404, 429].includes(result.status())) return `HTTP ${result.status()}`;
    expect(result.ok(), `analysis detail HTTP ${result.status()}`).toBeTruthy();
    data = await result.json();
    expect(data.summary.task_id).toBe(id);
    return data.summary.state.outcome;
  }, { timeout: 20000, intervals: [100, 250, 500] }).toBe("check_complete");
  expect(data!.summary.state.outcome).toBe("check_complete");
  expect(data!.summary.usage.model_calls).toBe(0);
  await page.getByRole("region", { name: "证据", exact: true }).getByRole("button", { name: "工具调用契约检查", exact: true }).click();
  await expect(page.getByLabel("字段路径 /result/structured_content/count")).toBeVisible();
  await page.reload();
  await expect(page).toHaveURL(new RegExp(`analysis=${id}`));
  await expect(page.getByRole("region", { name: "分析详情" })).toContainText("检查完成");
  expect(starts).toHaveLength(1);
});

for (const scenario of ["pass", "tool_error"] as const) test(`真实网页容器复现与结果：${scenario}`, async ({ page, request }) => {
  test.setTimeout(90000);
  await page.goto("/workspace/tasks");
  await page.getByRole("radio", { name: scenario === "pass" ? "正常调用" : "工具错误", exact: true }).check();
  const accepted = page.waitForResponse(res => res.request().method() === "POST" && new URL(res.url()).pathname === "/api/reproductions");
  await page.getByRole("button", { name: "开始复现", exact: true }).click();
  const response = await accepted;
  expect(response.ok()).toBeTruthy();
  const acceptance = await response.json();
  await expect(page).toHaveURL(new RegExp(`run=${acceptance.run.run_id}`));
  const detail = page.getByRole("region", { name: "运行详情" });
  await expect(detail.locator(".report-verified")).toBeVisible({ timeout: 60000 });
  const id = new URL(page.url()).searchParams.get("run");
  expect(id).toBeTruthy();
  const data = await (await request.get(`http://127.0.0.1:8034/api/runs/${id}`)).json();
  expect(data.run.scenario).toBe(scenario);
  expect(data.run.status).toBe(scenario === "pass" ? "succeeded" : "failed");
  expect(data.run.executor_state).toBe("absent");
  await expect(detail.locator(".run-detail-head .run-status-badge")).toHaveText(scenario === "pass" ? "调用成功" : "调用失败");
});

test("真实网页三角色模型建议，不冒充应用补丁", async ({ page, request }) => {
  test.skip(process.env.AWB_LIVE_MODEL !== "1", "Requires the user's existing model configured only in the API process.");
  test.setTimeout(240000);
  const started = page.waitForRequest(req => req.method() === "POST" && new URL(req.url()).pathname === "/api/analysis-runs");
  await page.goto("/workspace/diagnosis");
  await page.getByLabel("目标", { exact: true }).selectOption("propose_repair");
  await page.getByRole("button", { name: "开始分析", exact: true }).click();
  await expect(page.getByRole("region", { name: "实时执行事件" })).toContainText("分析已结束", { timeout: 220000 });
  const id = (await started).postDataJSON().request_id;
  await expect(page).toHaveURL(new RegExp(`analysis=${id}`));
  const data = await (await request.get(`http://127.0.0.1:8034/api/analyses/${id}`)).json();
  expect(data.summary.usage.model_calls).toBeGreaterThan(0);
  expect(data.summary.usage.usage_complete).toBe(true);
  expect(data.summary.state.outcome).toBe("proposal_only");
  const roles = new Set(data.events.map((e: {event: {role: string | null}}) => e.event.role));
  expect(roles.has("diagnosis") && roles.has("repair") && roles.has("verification")).toBe(true);
  await expect(page.getByRole("region", { name: "分析详情" })).toContainText("没有修改代码");
});
