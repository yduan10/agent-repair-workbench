import { test, expect } from "@playwright/test";
const api = process.env.AWB_REPAIR_LIVE_URL;
if (api && !/^http:\/\/127\.0\.0\.1:\d{4,5}$/.test(api))
  throw new Error("invalid_live_api");
test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "ignoreErrors" }); });
test("真实只读API：当前核验候选与逐项结果来自同一保存任务", async ({
  page,
  request,
}) => {
  test.skip(!api, "需要显式提供含已验证任务的本地只读 API");
  const list = await request.get(`${api}/api/repairs?limit=50`);
  expect(list.ok()).toBeTruthy();
  const entries = (await list.json()).repairs as Array<{
    task_id: string;
    case_id: string;
  }>;
  let target:
    | {
        taskId: string;
        candidateId: string;
        sequence: number;
        caseId: string;
      }
    | undefined;
  for (const entry of entries) {
    const detail = await request.get(`${api}/api/repairs/${entry.task_id}`);
    expect(detail.ok()).toBeTruthy();
    const value = await detail.json();
    const verified = value.comparisons.find(
      (item: { verification: string; current_outcome: string }) =>
        item.verification === "verified" &&
        item.current_outcome === "candidate_verified",
    );
    if (verified) {
      target = {
        taskId: entry.task_id,
        caseId: entry.case_id,
        candidateId: verified.candidate_id,
        sequence: value.candidates.find(
          (c: { candidate_id: string }) =>
            c.candidate_id === verified.candidate_id,
        ).sequence,
      };
      break;
    }
  }
  expect(target, "该显式实链路门禁必须含一条当前核验通过记录").toBeTruthy();
  if (!target) return;
  const writes: string[] = [];
  page.on("request", (req) => {
    if (req.url().includes("/api/") && req.method() !== "GET")
      writes.push(req.method());
  });
  const readFailures: Array<{ path: string; status: number }> = [];
  await page.route("**/api/repairs**", async (route) => {
    const u = new URL(route.request().url());
    const response = await request.get(`${api}${u.pathname}${u.search}`, {
      headers: { Origin: "http://127.0.0.1:3012" },
    });
    if (!response.ok()) readFailures.push({ path: u.pathname, status: response.status() });
    await route.fulfill({ response });
  });
  await page.goto(
    `/workspace/repairs?task=${target.taskId}&candidate=${target.candidateId}`,
  );
  const region = page.getByRole("region", { name: /的差异内容$/ });
  const alerts = page.locator("#main").getByRole("alert");
  // Observe the real refusal, then use the existing UI retry. Never synthesize a success body.
  let failureCursor = 0;
  for (let retry = 0; retry <= 3; retry++) {
    await expect.poll(async () => (await region.isVisible()) || (await alerts.count()) > 0,
      { timeout: 15000 }).toBe(true);
    if ((await region.isVisible()) && (await alerts.count()) === 0) break;
    const newlyFailed = readFailures.slice(failureCursor);
    failureCursor = readFailures.length;
    expect(newlyFailed.length, "UI error must correspond to an observed actual 429").toBeGreaterThan(0);
    expect(newlyFailed.every(item => item.status === 429), JSON.stringify(newlyFailed)).toBe(true);
    expect(retry, "bounded manual retry exhausted").toBeLessThan(3);
    await test.info().attach(`actual-429-${retry}`, { body: JSON.stringify(newlyFailed), contentType: "application/json" });
    const retryButton = alerts.first().getByRole("button", { name: /^重试读取列表$|^重试读取详情$|^重试$/ });
    await retryButton.click();
    await expect(alerts).toHaveCount(0);
  }
  await expect(region).toBeVisible();
  // Fetch the byte-for-byte reference only after the UI has finished its own reads.
  const diffResponse = await request.get(
    `${api}/api/repairs/${target.taskId}/candidates/${target.candidateId}/diff`,
  );
  expect(diffResponse.ok()).toBeTruthy();
  const actual = (await diffResponse.json()).diff.unified_diff as string;
  // Every line after the two file headers is rendered verbatim, in order, one row each.
  const rendered = await region.locator("[data-diff-row] .rp-diff-code").allTextContents();
  const expected = actual.replace(/\n$/, "").split("\n").filter(
    (line, i) => !(i < 2 && (line.startsWith("--- ") || line.startsWith("+++ "))),
  );
  expect(rendered).toEqual(expected);
  const verdict = page.locator(".rp-verdict");
  await expect(verdict.getByRole("heading")).toContainText(
    `候选 ${target.sequence}`,
  );
  await expect(verdict.getByRole("heading")).toContainText("回归通过");
  await page.screenshot({
    path: "artifacts/ui08-live-diff.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "回归结果" }).click();
  await expect(page).toHaveURL(/tab=regression/);
  await expect(page.getByRole("table")).toHaveCount(1);
  await expect(page.getByText(target.caseId === "counter_offset" ? "计数值不一致" : "计数类型不一致", { exact: true })).toHaveCount(
    3,
  );
  await expect(verdict.getByRole("heading")).toContainText("回归通过");
  await page.screenshot({
    path: "artifacts/ui08-live-regression.png",
    fullPage: true,
  });
  expect(writes).toEqual([]);
});
