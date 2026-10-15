import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import passing from "../../examples/passing.json";

const editor = (page: Page) => page.getByRole("textbox", { name: "调用证据", exact: true });
async function openWorkbench(page: Page, path = "/workbench") {
  await page.goto(path);
  await expect(page.locator(".cm-content")).toBeVisible();
}
const run = (page: Page) => page.getByRole("button", { name: "运行检查", exact: true }).click();

test("产品入口到真实检查与报告下载", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "打开工作台" }).first().click();
  await expect(page).toHaveURL(/\/workspace$/);
  await page.getByRole("navigation", { name: "产品模块" }).getByRole("link", { name: "调用检查" }).click();
  await expect(page).toHaveURL(/workbench/);
  await expect(page.locator(".cm-content")).toBeVisible();
  await expect(page.getByRole("heading", { name: "运行检查后，在这里查看结果" })).toBeVisible();
  await run(page);
  await expect(page.getByRole("heading", { name: "不通过", exact: true })).toBeVisible();
  await expect(page.getByLabel("字段路径 /result/structured_content/count")).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载报告" }).click();
  expect((await downloaded).suggestedFilename()).toBe("check-report.json");
});

test("成功、缺失结果与编辑失效", async ({ page }) => {
  await openWorkbench(page);
  await page.getByRole("button", { name: "正常调用", exact: true }).click();
  await run(page);
  await expect(page.getByRole("heading", { name: "通过", exact: true })).toBeVisible();
  await editor(page).fill("{}");
  await expect(page.getByRole("heading", { name: "通过", exact: true })).not.toBeVisible();
  await run(page);
  await expect(page.getByText("invalid_document", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "缺失结果", exact: true }).click();
  await page.getByRole("dialog", { name: "替换编辑器中的内容？" }).getByRole("button", { name: "替换" }).click();
  await run(page);
  await expect(page.getByText("result_missing", { exact: true })).toBeVisible();
});

test("浏览器保持原始数字与重复键", async ({ page }) => {
  await openWorkbench(page, "/workbench?source=custom");
  const raw = JSON.stringify(passing).replace('"id":1', '"id":9007199254740993.0');
  await editor(page).fill(raw);
  const request = page.waitForRequest(r => r.url().endsWith("/api/check"));
  await run(page);
  expect((await request).postData()).toBe(raw);
  await expect(page.getByText("unsupported_number", { exact: true })).toBeVisible();
  await editor(page).fill(JSON.stringify(passing).replace('"id":1', '"id":1,"id":2'));
  await run(page);
  await expect(page.getByText("invalid_document", { exact: true })).toBeVisible();
});

test("导入文件与断网恢复", async ({ page }) => {
  await openWorkbench(page);
  await page.getByLabel("导入 JSON 文件").setInputFiles({ name: "call.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(passing)) });
  const replace = page.getByRole("dialog", { name: "替换编辑器中的内容？" });
  if (await replace.isVisible().catch(() => false)) await replace.getByRole("button", { name: "替换" }).click();
  await page.route("**/api/check", route => route.abort());
  await run(page);
  await expect(page.locator("#input-error")).toContainText("未能取得检查结果");
  await page.unroute("**/api/check");
  await run(page);
  await expect(page.getByRole("heading", { name: "通过", exact: true })).toBeVisible();
});

test("BOM 文件保真与未保存导航保护", async ({ page }) => {
  await openWorkbench(page);
  const raw = Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from(JSON.stringify(passing))]);
  await page.getByLabel("导入 JSON 文件").setInputFiles({ name: "bom.json", mimeType: "application/json", buffer: raw });
  const replace = page.getByRole("dialog", { name: "替换编辑器中的内容？" });
  if (await replace.isVisible().catch(() => false)) await replace.getByRole("button", { name: "替换" }).click();
  let request = page.waitForRequest(r => r.url().endsWith("/api/check"));
  await run(page);
  expect((await request).postDataBuffer()).toEqual(raw);
  await expect(page.getByText("invalid_document", { exact: true })).toBeVisible();

  const leave = page.getByRole("dialog", { name: "离开调用检查？" });
  const nav = page.getByRole("navigation", { name: "产品模块" });
  await nav.getByRole("link", { name: "复现", exact: true }).click();
  await leave.getByRole("button", { name: "留在此页" }).click();
  await expect(page).toHaveURL(/workbench/);
  for (const name of ["文档", "更新记录"]) {
    await page.getByRole("navigation", { name: "帮助" }).getByRole("link", { name, exact: true }).click();
    await leave.getByRole("button", { name: "留在此页" }).click();
    await expect(page).toHaveURL(/workbench/);
  }
  request = page.waitForRequest(r => r.url().endsWith("/api/check"));
  await run(page);
  expect((await request).postDataBuffer(), "草稿在取消离开后保持原始字节").toEqual(raw);

  await nav.getByRole("link", { name: "复现", exact: true }).click();
  await leave.getByRole("button", { name: "离开" }).click();
  await expect(page).toHaveURL(/workspace\/tasks/);
});

for (const width of [1440, 390]) {
  test(`产品页和各模块 ${width}px 布局及可访问性`, async ({ page }) => {
    test.setTimeout(90000);
    await page.setViewportSize({ width, height: 960 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    for (const path of ["/", "/workspace", "/workbench", "/workspace/tasks", "/workspace/diagnosis", "/workspace/repairs", "/workspace/connections"]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await page.waitForLoadState("networkidle");
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), path).toBe(false);
      const accessibility = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
      expect(accessibility.violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => n.target) })), path).toEqual([]);
      if (path === "/") await page.screenshot({ path: `../artifacts/ui08-home-${width}.png`, fullPage: true });
    }
  });
}
