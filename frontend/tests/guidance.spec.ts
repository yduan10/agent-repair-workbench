import { test, expect } from "@playwright/test";

const source = "https://github.com/ykduan0916/agent-repair-workbench";

test("首次访问能找到真实功能、文档和源码", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("找出 Agent 工具调用中不符合契约的字段");
  const footer = page.getByRole("navigation", { name: "页脚导航" });
  await footer.getByRole("link", { name: "复现" }).click();
  await expect(page).toHaveURL(/\/workspace\/tasks$/);
  await page.goto("/");
  await footer.getByRole("link", { name: "文档", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("文档");
  await page.locator("#reference").getByRole("link", { name: "架构与技术决策" }).click();
  await expect(page).toHaveURL(/\/docs\/02-architecture$/);
  await expect(page.locator(".doc-prose")).toContainText("技术");
  await page.goto("/");
  const github = page.getByRole("banner").getByRole("link", { name: /GitHub/ });
  await expect(github).toHaveAttribute("href", source);
  await expect(github).toHaveAttribute("target", "_blank");
  await expect(github).toHaveAttribute("rel", "noopener noreferrer");
});

for (const theme of ["dark", "light"] as const) {
  test(`${theme} 空状态指明下一步`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/workbench");
    await expect(page.locator(".cm-content")).toBeVisible();
    const empty = page.locator(".wb-empty");
    await expect(empty).toContainText("再点击「运行检查」");
    expect(await empty.evaluate(el => getComputedStyle(el).backgroundImage)).toBe("none");
    await page.getByRole("button", { name: "运行检查", exact: true }).click();
    await expect(page.getByRole("heading", { name: "不通过", exact: true })).toBeVisible();
  });
}

test("手机键盘可横向阅读长命令", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto("/docs/27-local-development-guide");
  const region = page.getByRole("region", { name: "代码示例，可横向滚动" }).first();
  await region.focus();
  await expect(region).toBeFocused();
  await region.press("ArrowRight");
  await expect.poll(() => region.evaluate(el => el.scrollLeft)).toBeGreaterThan(0);
});
