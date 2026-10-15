import { expect, test, type Page } from "@playwright/test";
import { formatDuration } from "../lib/format";

const id = "10000000-0000-4000-8000-000000000001";
const analysis = {
  schema_version: 1,
  cases: [{ id: "output_mismatch", label: "返回值类型错误" }, { id: "passing", label: "正常调用" }],
  intents: [{ id: "check_only", label: "仅检查契约", requires_model: false }, { id: "diagnose", label: "分析原因", requires_model: true }, { id: "propose_repair", label: "生成修复建议", requires_model: true }],
  model: { configured: true, reason: null }, slot: { status: "available", task_id: null },
};
async function environment(page: Page, busy = false) {
  await page.route("**/api/health", route => route.fulfill({ json: { status: "ok", checker_version: "test" } }));
  await page.route("**/api/reproductions/catalog", route => route.fulfill({ json: {
    version: 1, ready: !busy, reason: busy ? "runner_busy" : null, active_run_id: busy ? id : null,
    cases: ["pass", "tool_error", "timeout", "response_lost"].map(id => ({ id, title: id, description: id, expected: id })),
  } }));
  await page.route("**/api/analysis-runs/catalog", route => route.fulfill({ json: analysis }));
}

test("independent shell: two failed refreshes withdraw previous ready status, success restores it", async ({ page }) => {
  await environment(page);
  let failed = false;
  await page.route("**/api/analysis-runs/catalog", route => failed ? route.fulfill({ status: 500, body: "" }) : route.fulfill({ json: analysis }));
  await page.goto("/workspace/connections");
  const trigger = page.locator(".env-trigger");
  await expect(trigger).toContainText("环境就绪");
  await trigger.click();
  const popup = page.getByRole("dialog", { name: "本机环境状态" });
  failed = true;
  for (let i = 0; i < 2; i++) {
    const response = page.waitForResponse(r => r.url().endsWith("/api/analysis-runs/catalog") && r.status() === 500);
    await popup.getByRole("button", { name: "重新检查" }).click();
    await response;
    await page.waitForTimeout(80);
  }
  await expect(trigger).toContainText("部分功能不可用");
  await expect(popup).toContainText("模型与分析 · 无法读取");
  failed = false;
  await popup.getByRole("button", { name: "重新检查" }).click();
  await expect(trigger).toContainText("环境就绪");
});

test("independent shell: runner busy links exact run, Escape restores trigger focus", async ({ page }) => {
  await environment(page, true);
  await page.goto("/workspace/connections");
  const trigger = page.locator(".env-trigger");
  await expect(trigger).toContainText("正在运行");
  await trigger.click();
  const popup = page.getByRole("dialog", { name: "本机环境状态" });
  const link = popup.getByRole("link", { name: "查看", exact: true });
  await expect(link).toHaveAttribute("href", `/workspace/tasks?run=${id}`);
  await link.focus();
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
  await expect(popup).toHaveCount(0);
  await expect(page.locator("#status")).toContainText("正在运行一项复现，结束后可开始新的复现。");
});

test("independent shell: popup navigation respects unchecked draft guard", async ({ page }) => {
  await environment(page);
  await page.route("**/api/analysis-runs/catalog", route => route.fulfill({ json: { ...analysis, model: { configured: false, reason: "MODEL_NOT_CONFIGURED" } } }));
  await page.goto("/workbench");
  await page.getByRole("textbox", { name: "调用证据", exact: true }).fill('{"independent":true}');
  await page.locator(".env-trigger").click();
  await page.getByRole("dialog", { name: "本机环境状态" }).getByRole("link", { name: "处理方法" }).click();
  const dialog = page.getByRole("dialog", { name: "离开调用检查？" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "留在此页" }).click();
  await expect(page).toHaveURL(/\/workbench$/);
});

test("independent duration carry boundaries", () => {
  expect(formatDuration(59600)).toBe("1 分钟");
  expect(formatDuration(119600)).toBe("2 分钟");
  expect(formatDuration(3599700)).toBe("1 小时 0 分");
  expect(formatDuration(9960)).toBe("10 秒");
});
