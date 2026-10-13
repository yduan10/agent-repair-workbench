import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFile } from "node:fs/promises";

test("真实协作接口可按角色查看并下载，页面不执行工具", async ({ page }) => {
  const writes: string[] = [];
  page.on("request", request => { if (request.method() !== "GET") writes.push(request.url()); });
  await page.goto("/workspace/connections");
  const catalog = page.getByRole("region", { name: "协作接口", exact: true });
  await expect(catalog.getByRole("tab", { name: "诊断角色" })).toHaveAttribute("aria-selected", "true");
  await expect(catalog.locator(".contract-tool-list li")).toHaveCount(5);
  await catalog.getByRole("tab", { name: "诊断角色" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(catalog.getByRole("tab", { name: "修复角色" })).toBeFocused();
  await expect(catalog.locator(".contract-tool-list li")).toHaveCount(3);
  await expect(catalog.getByRole("tabpanel")).not.toContainText("申请受控复现");
  await catalog.getByText("查看修复角色输出格式", { exact: true }).click();
  await expect(catalog.locator(".role-output pre")).toContainText("proposal_only");
  await catalog.getByText("读取源码片段", { exact: true }).click();
  await expect(catalog.locator(".contract-tool-list details[open] pre")).toContainText("snapshot_id");
  const downloadPromise = page.waitForEvent("download");
  await catalog.getByRole("button", { name: "下载接口约定" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("agent-contracts-v1.json");
  const saved = JSON.parse(await readFile((await download.path())!, "utf8"));
  const actual = await (await page.request.get("/api/agent-contracts")).json();
  expect(saved).toEqual(actual);
  expect(saved.runtime_available).toBe(false);
  expect(writes).toEqual([]);
});

test("协作目录故障可重试，未知版本和提前开放标记拒绝展示", async ({ page }) => {
  await page.route("**/api/agent-contracts", route => route.fulfill({ status: 503, body: "PRIVATE_ERROR" }));
  await page.goto("/workspace/diagnosis");
  const catalog = page.getByRole("region", { name: "协作接口", exact: true });
  await expect(catalog.getByRole("alert")).toBeVisible();
  await expect(catalog).not.toContainText("PRIVATE_ERROR");
  await page.unroute("**/api/agent-contracts");
  await catalog.getByRole("button", { name: "重试读取" }).click();
  await expect(catalog.getByRole("tab", { name: "诊断角色" })).toBeVisible();
  const original = await (await page.request.get("/api/agent-contracts")).json();
  for (const change of [{ catalog_version: 99 }, { runtime_available: true }, { roles: [original.roles[0], original.roles[0], original.roles[0]] }]) {
    await page.route("**/api/agent-contracts", route => route.fulfill({ json: { ...original, ...change } }));
    await page.reload();
    await expect(catalog.getByRole("alert")).toBeVisible();
    await expect(catalog.getByRole("button", { name: "下载接口约定" })).toHaveCount(0);
    await page.unroute("**/api/agent-contracts");
  }
});

for (const theme of ["light", "dark"] as const) {
  for (const width of [1280, 390]) {
    test(`协作接口 ${theme} ${width}px 可读、键盘可用且无溢出`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
      await page.goto("/workspace/connections");
      const catalog = page.getByRole("region", { name: "协作接口", exact: true });
      await catalog.scrollIntoViewIfNeeded();
      await expect(catalog.getByRole("tab", { name: "诊断角色" })).toBeVisible();
      await catalog.getByRole("tab", { name: "诊断角色" }).focus();
      await page.keyboard.press("End");
      await expect(catalog.getByRole("tab", { name: "验证角色" })).toBeFocused();
      await catalog.getByText("查看验证角色输出格式", { exact: true }).click();
      await expect(catalog.locator(".role-output pre")).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
      expect(await catalog.getByRole("tab", { name: "验证角色" }).evaluate(el => getComputedStyle(el).transitionDuration)).toBe("0s");
      const a11y = await new AxeBuilder({ page }).include(".agent-contracts").withTags(["wcag2a", "wcag2aa"]).analyze();
      expect(a11y.violations).toEqual([]);
      await page.screenshot({ path: `../artifacts/p005a-${theme}-${width}.png`, fullPage: true });
    });
  }
}
