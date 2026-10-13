import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("主题选择跨刷新与路由保留，支持键盘", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  const select = page.getByRole("combobox", { name: "外观主题" });
  await select.focus();
  await select.selectOption("dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  expect(await page.evaluate(() => localStorage.getItem("awb-theme"))).toBe("dark");
  await page.reload();
  await expect(select).toHaveValue("dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("link", { name: "开发记录", exact: true }).first().click();
  await expect(page).toHaveURL(/\/updates$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("开发记录");
  const destinationTheme = page.getByRole("combobox", { name: "外观主题" });
  await expect(destinationTheme).toHaveValue("dark");
  await destinationTheme.focus();
  await expect(destinationTheme).toBeFocused();
  await page.keyboard.press("Home");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("跟随系统实时响应，手动主题优先", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/workbench");
  const select = page.getByRole("combobox", { name: "外观主题" });
  await select.selectOption("system");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await select.selectOption("light");
  await page.emulateMedia({ colorScheme: "light" });
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("主题在页面可见前设置，存储不可用仍可切换", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("awb-theme", "dark");
    document.addEventListener("DOMContentLoaded", () => {
      document.documentElement.dataset.themeAtReady = document.documentElement.dataset.theme;
    }, { once: true });
  });
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-theme-at-ready", "dark");
  await page.evaluate(() => { Storage.prototype.setItem = () => { throw new Error("blocked"); }; });
  await page.getByRole("combobox", { name: "外观主题" }).selectOption("light");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("降低动效、完整迭代历史与实际能力状态", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  expect(await page.locator(".hero-line > span").first().evaluate(el => getComputedStyle(el).animationName)).toBe("none");
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).scrollBehavior)).toBe("auto");
  await page.getByRole("link", { name: "开发记录", exact: true }).first().click();
  const milestones = page.locator(".milestone");
  await expect(milestones.first()).toContainText("UI-05");
  for (const id of ["P0-04", "UI-03", "P0-03", "UI-02", "DOC-02", "P0-02", "UI-01", "P0-01", "DOC-01"]) {
    const completed = milestones.filter({ has: page.locator(".milestone-meta > span", { hasText: id }) });
    await expect(completed).toHaveCount(1);
    await expect(completed).toContainText("已完成");
  }
  const mcp = milestones.filter({ has: page.locator(".milestone-meta", { hasText: "P0-02" }) });
  await expect(mcp).toContainText("已完成");
  await expect(milestones.filter({ has: page.locator(".milestone-meta", { hasText: "DOC-02" }) })).toContainText("维护边界");
  await expect(page.getByText(/这些编号不是正式发布版本/)).toBeVisible();
  const previous = milestones.filter({ has: page.locator(".milestone-meta", { hasText: "UI-01" }) });
  await expect(previous).not.toHaveAttribute("open", "");
  await previous.locator("summary").focus();
  await page.keyboard.press("Enter");
  await expect(previous).toHaveAttribute("open", "");
  await expect(previous.getByText(/99 项 Python/)).toBeVisible();
  await page.getByRole("link", { name: "查看工具接入进度" }).click();
  await expect(page.getByText("CLI 已验证", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "真实能力进度" })).toContainText("网页接入尚未开放");
  const progress = page.getByRole("region", { name: "真实能力进度" });
  await expect(progress).toContainText("P0-02 · MCP CLI 已验证");
  await expect(progress).toContainText("P0-03 · 受控 Docker CLI 已验证");
  await expect(progress).toContainText("18 项真实容器验收及独立复审通过");
  await expect(progress).toContainText("覆盖故障注入、取消回收与宿主进程终止");
  await expect(progress).toContainText("任务总览已能查看运行记录");
  await expect(progress).toContainText("网页发起工具执行仍按 P1-01 接入");
});

for (const theme of ["dark", "light"] as const) {
for (const width of [1440, 390]) {
  test(`${theme} 全站 ${width}px 对比度与布局`, async ({ page }) => {
    await page.setViewportSize({ width, height: 960 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
    for (const path of ["/", "/docs", "/updates", "/workbench", "/workspace/tasks", "/workspace/diagnosis", "/workspace/repairs", "/workspace/regression", "/workspace/memory", "/workspace/connections"]) {
      await page.goto(path);
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      await expect(page.getByRole("combobox", { name: "外观主题" })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), path).toBe(false);
      const a11y = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
      expect(a11y.violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => ({ target: n.target, summary: n.failureSummary })) })), path).toEqual([]);
      if (path === "/" || path === "/updates") await page.screenshot({ path: `../artifacts/ui02-${path === "/" ? "home" : "updates"}-${theme}-${width}.png`, fullPage: true });
    }
  });
}

}

test("产品信息位于页脚，短桌面与手机均可访问", async ({ page }) => {
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 720 });
    await page.goto("/workspace/connections");
    const sidebar = page.locator(".product-sidebar");
    await expect(sidebar.getByRole("link", { name: "产品介绍", exact: true })).toHaveCount(0);
    await expect(sidebar.getByRole("link", { name: /开发记录/ })).toHaveCount(0);
    const footer = page.getByRole("region", { name: "产品信息" });
    await expect(footer.getByRole("link", { name: "产品介绍", exact: true })).toHaveAttribute("href", "/");
    const history = footer.getByRole("link", { name: "开发记录", exact: true });
    await history.focus();
    await expect(history).toBeFocused();
    await history.press("Enter");
    await expect(page).toHaveURL(/\/updates$/);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("开发记录");
  }
});
