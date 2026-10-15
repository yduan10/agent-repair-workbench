import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFile } from "node:fs/promises";

const contractsRegion = (page: import("@playwright/test").Page) => page.getByRole("region", { name: "角色与工具接口", exact: true });

test("角色与工具接口可查看契约并下载，页面不执行工具", async ({ page }) => {
  const writes: string[] = [];
  page.on("request", request => { if (request.method() !== "GET") writes.push(request.url()); });
  await page.goto("/workspace/connections#contracts");
  const catalog = contractsRegion(page);
  await expect(catalog.locator(".contract-item[data-role]")).toHaveCount(3);
  await expect(catalog.locator(".contract-item[data-tool]")).toHaveCount(5);
  await expect(catalog.locator('[data-role="diagnosis"] .chip')).toHaveCount(5);
  const repair = catalog.locator('[data-role="repair"]');
  await expect(repair.locator(".chip")).toHaveCount(3);
  await expect(repair).not.toContainText("申请复现");
  await expect(catalog.locator('[data-tool="request_reproduction"] .chip')).toHaveText(["诊断", "验证"]);

  const repairToggle = catalog.getByRole("button", { name: "查看契约：修复角色输出" });
  await expect(repairToggle).toHaveAttribute("aria-expanded", "false");
  await repairToggle.click();
  await expect(repairToggle).toHaveAttribute("aria-expanded", "true");
  await expect(repair.locator(".contract-schema pre")).toContainText("proposal_only");
  const roleDownload = page.waitForEvent("download");
  await repair.getByRole("button", { name: "下载", exact: true }).click();
  expect((await roleDownload).suggestedFilename()).toBe("agent-role-repair-output.schema.json");
  await repairToggle.focus();
  await page.keyboard.press("Enter");
  await expect(repairToggle).toHaveAttribute("aria-expanded", "false");
  await expect(repair.locator(".contract-schema")).toBeHidden();

  await catalog.getByRole("button", { name: "查看契约：读取源码片段请求" }).click();
  await expect(catalog.locator('[data-tool="read_source"] .contract-schema pre')).toContainText("snapshot_id");

  const downloadPromise = page.waitForEvent("download");
  await catalog.getByRole("button", { name: "下载完整目录" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("agent-contracts-v3.json");
  const saved = JSON.parse(await readFile((await download.path())!, "utf8"));
  const actual = await (await page.request.get("/api/agent-contracts")).json();
  expect(saved).toEqual(actual);
  expect(saved.cli_runtime_available).toBe(true);
  expect(saved.web_runtime_available).toBe(true);
  expect(writes).toEqual([]);
});

test("角色与工具目录故障可重试，未知版本和提前开放标记拒绝展示", async ({ page }) => {
  await page.route("**/api/agent-contracts", route => route.fulfill({ status: 503, body: "PRIVATE_ERROR" }));
  await page.goto("/workspace/connections");
  const catalog = contractsRegion(page);
  await expect(catalog.getByRole("alert")).toBeVisible();
  await expect(catalog).not.toContainText("PRIVATE_ERROR");
  await page.unroute("**/api/agent-contracts");
  await catalog.getByRole("button", { name: "重试", exact: true }).click();
  await expect(catalog.locator(".contract-item[data-role]")).toHaveCount(3);
  const original = await (await page.request.get("/api/agent-contracts")).json();
  for (const change of [{ catalog_version: 99 }, { cli_runtime_available: false }, { web_runtime_available: false }, { roles: [original.roles[0], original.roles[0], original.roles[0]] }]) {
    await page.route("**/api/agent-contracts", route => route.fulfill({ json: { ...original, ...change } }));
    await page.reload();
    await expect(catalog.getByRole("alert")).toBeVisible();
    await expect(catalog.getByRole("button", { name: "下载完整目录" })).toHaveCount(0);
    await expect(catalog.locator(".contract-item")).toHaveCount(0);
    await page.unroute("**/api/agent-contracts");
  }
});

for (const theme of ["light", "dark"] as const) {
  for (const width of [1280, 390]) {
    test(`环境与接入 ${theme} ${width}px 可读、键盘可用且无溢出`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
      await page.goto("/workspace/connections");
      await expect(page.getByRole("heading", { level: 1 })).toContainText("环境与接入");
      for (const name of ["本机环境", "模型", "本机数据", "角色与工具接口", "命令行"]) await expect(page.getByRole("region", { name, exact: true })).toBeVisible();
      const catalog = contractsRegion(page);
      const toggle = catalog.getByRole("button", { name: "查看契约：验证角色输出" });
      await toggle.scrollIntoViewIfNeeded();
      await toggle.focus();
      await page.keyboard.press("Enter");
      await expect(catalog.locator('[data-role="verification"] .contract-schema pre')).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
      const a11y = await new AxeBuilder({ page }).include(".env-page").withTags(["wcag2a", "wcag2aa"]).analyze();
      expect(a11y.violations).toEqual([]);
      await page.screenshot({ path: `../artifacts/ui08-connections-${theme}-${width}.png`, fullPage: true });
    });
  }
}

test("环境与接入不再提供复现入口，只读且不发写请求", async ({ page }) => {
  const writes: string[] = [];
  page.on("request", request => { if (request.method() !== "GET") writes.push(request.url()); });
  await page.goto("/workspace/connections");
  await expect(page.getByRole("region", { name: "本机环境", exact: true })).toContainText("127.0.0.1:8030");
  await expect(page.getByRole("button", { name: "开始复现" })).toHaveCount(0);
  await expect(page.getByRole("radio")).toHaveCount(0);
  await expect(page.getByRole("region", { name: "命令行", exact: true })).toContainText("接入自己的 MCP 服务尚未开放；目前只能运行内置示例。");
  const model = page.getByRole("region", { name: "模型", exact: true });
  for (const name of ["AWB_MODEL_BASE_URL", "AWB_MODEL_NAME", "AWB_MODEL_API_KEY", "AWB_MODEL_LIMIT_PROFILE"]) await expect(model).toContainText(name);
  await page.getByRole("navigation", { name: "本页内容" }).getByRole("link", { name: "本机数据" }).click();
  await expect(page).toHaveURL(/#data$/);
  await page.getByRole("button", { name: "重新检查" }).click();
  await expect(page.getByText(/检查于/)).toBeVisible();
  expect(writes).toEqual([]);
});
