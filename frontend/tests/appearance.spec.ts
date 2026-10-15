import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const themeButton = (page: Page, name: "浅色" | "深色" | "跟随系统") =>
  page.getByRole("group", { name: "外观主题" }).first().getByRole("button", { name, exact: true });

test("主题选择跨刷新与路由保留，支持键盘", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/workspace");
  await themeButton(page, "深色").focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(themeButton(page, "深色")).toHaveAttribute("aria-pressed", "true");
  expect(await page.evaluate(() => localStorage.getItem("awb-theme"))).toBe("dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(themeButton(page, "深色")).toHaveAttribute("aria-pressed", "true");
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(themeButton(page, "深色")).toHaveAttribute("aria-pressed", "true");
  await themeButton(page, "浅色").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("跟随系统实时响应，手动主题优先", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/workbench");
  await themeButton(page, "跟随系统").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await themeButton(page, "浅色").click();
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
  await themeButton(page, "浅色").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("降低动效时不播放动画，平滑滚动关闭", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const path of ["/", "/workspace"]) {
    await page.goto(path);
    expect(await page.evaluate(() => getComputedStyle(document.documentElement).scrollBehavior)).toBe("auto");
    const running = await page.evaluate(() => document.getAnimations().filter(a => {
      const timing = a.effect?.getComputedTiming();
      return a.playState === "running" && Number(timing?.duration ?? 0) > 50;
    }).length);
    expect(running, path).toBe(0);
  }
});

test("工作区使用本地字体，不请求外部字体服务", async ({ page }) => {
  const external: string[] = [];
  page.on("request", request => { if (!request.url().startsWith("http://127.0.0.1")) external.push(request.url()); });
  await page.goto("/workspace");
  await page.evaluate(() => document.fonts.ready);
  const family = await page.evaluate(() => getComputedStyle(document.body).fontFamily);
  expect(family).toMatch(/Geist/i);
  expect(external).toEqual([]);
});

const routes = ["/", "/docs", "/updates", "/workspace", "/workbench", "/workspace/tasks", "/workspace/diagnosis", "/workspace/repairs", "/workspace/repairs?tab=regression", "/workspace/connections"];
for (const theme of ["dark", "light"] as const) {
  for (const width of [1440, 390]) {
    test(`${theme} 全站 ${width}px 对比度与布局`, async ({ page }) => {
      test.setTimeout(120000);
      await page.setViewportSize({ width, height: 960 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
      for (const path of routes) {
        await page.goto(path);
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        await page.waitForLoadState("networkidle");
        expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), path).toBe(false);
        const a11y = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
        expect(a11y.violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => ({ target: n.target, summary: n.failureSummary })) })), path).toEqual([]);
      }
    });
  }
}
