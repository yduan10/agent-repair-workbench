import { test, expect } from "@playwright/test";

// An explicitly prepared, disposable store and a real Docker image are required.
// This is never enabled by the ordinary mock/SQLite suite and does not prepare an image.
test("真实网页开始 → 容器运行 → 核验报告 → 请求停止超时任务", async ({ page }) => {
  test.skip(process.env.AWB_WEB_DOCKER_E2E !== "1", "Requires explicit AWB_WEB_DOCKER_E2E=1 with a disposable local API/store and prepared Docker image; skips do not count as passes.");
  test.setTimeout(120000);
  expect(process.env.AWB_STATE_DIR).toMatch(/awb-[^/]+\/state$/);
  expect(process.env.AWB_API_PORT).not.toBe("8030"); expect(process.env.PW_PORT).not.toBe("3010");
  await page.goto("/workspace/tasks");
  await expect(page.getByRole("button", { name: "开始复现", exact: true })).toBeEnabled();
  const response = page.waitForResponse(value => value.url().endsWith("/api/reproductions") && value.request().method() === "POST");
  await page.getByRole("button", { name: "开始复现", exact: true }).click();
  expect((await response).status()).toBe(202);
  const detail = page.getByRole("region", { name: "运行详情" });
  await expect(detail.locator(".verified-label")).toBeVisible({ timeout: 60000 });
  await expect(detail.locator(".report-summary")).toContainText("调用完成"); await expect(detail.locator(".report-summary")).toContainText("已回收");
  await expect(page.getByRole("button", { name: "开始复现", exact: true })).toBeEnabled({ timeout: 10000 });
  await page.getByRole("radio", { name: "调用超时", exact: true }).check();
  await page.getByRole("button", { name: "开始复现", exact: true }).click();
  await page.getByRole("button", { name: "请求停止运行" }).click();
  await expect(detail.locator(".run-detail-heading .run-status")).toHaveText(/已取消|结果未知|失败/, { timeout: 60000 });
  await expect(detail.locator(".verified-label")).toBeVisible({ timeout: 10000 });
  await expect(detail.locator(".report-summary")).toContainText(/已回收|未创建容器/);
});
