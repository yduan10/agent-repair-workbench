import { test, expect } from "@playwright/test";

const source = "https://github.com/yduan10/agent-repair-workbench";

test("首次访问能找到真实功能、文档和源码", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("定位工具调用失败");
  const start = page.getByRole("region", { name: "按你要做的事，直接进入。" });
  await start.getByRole("link", { name: /运行一次工具复现/ }).click();
  await expect(page).toHaveURL(/\/workspace\/tasks$/);
  const footer = page.getByRole("region", { name: "产品信息" });
  await footer.getByRole("link", { name: "项目文档", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("项目文档");
  await expect(page.locator("#agent-testing")).toContainText("P0-05b 待接通");
  await page.getByRole("link", { name: /架构与技术决策/ }).click();
  await expect(page).toHaveURL(/\/docs\/02-architecture$/);
  await expect(page.locator(".markdown-document")).toContainText("技术");
  await page.goto("/");
  const github = page.getByRole("region", { name: "文档与源码" }).getByRole("link", { name: /GitHub 源码/ });
  await expect(github).toHaveAttribute("href", source);
  await expect(github).toHaveAttribute("target", "_blank");
  await expect(github).toHaveAttribute("rel", "noopener noreferrer");
});

for (const theme of ["dark", "light"] as const) {
  test(`${theme} 空状态不再用固定浅色光晕且指明下一步`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/workbench");
    const empty = page.locator(".empty-result");
    await expect(empty).toContainText("再点击「运行检查」");
    expect(await empty.evaluate(el => getComputedStyle(el).backgroundImage)).toBe("none");
    await page.getByRole("button", { name: "运行检查", exact: true }).click();
    await expect(page.getByRole("heading", { name: "发现不符合项" })).toBeVisible();
  });
}

test("手机键盘可横向阅读测试矩阵与长命令", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto("/docs");
  for (const name of ["Agent 测试层级，可横向滚动", "测试命令，可横向滚动"]) {
    const region = page.getByRole("region", { name, exact: true });
    await region.focus();
    await expect(region).toBeFocused();
    await region.press("ArrowRight");
    await expect.poll(() => region.evaluate(el => el.scrollLeft)).toBeGreaterThan(0);
  }
});
