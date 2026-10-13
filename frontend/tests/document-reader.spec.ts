import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("工程文档在本站完整阅读，目录和交叉引用可用", async ({ page }) => {
  await page.goto("/docs");
  const links = page.locator("#engineering-docs .docs-links a");
  for (const href of await links.evaluateAll(elements => elements.map(el => el.getAttribute("href")))) expect(href).toMatch(/^\/docs\//);
  await page.getByRole("link", { name: /架构与技术决策/ }).click();
  await expect(page).toHaveURL(/\/docs\/02-architecture$/);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.locator(".markdown-document")).toContainText("LangGraph");
  const toc = page.getByRole("navigation", { name: "本页章节", exact: true });
  const section = toc.getByRole("link").first();
  const anchor = await section.getAttribute("href");
  await section.click();
  expect(new URL(page.url()).hash).toBe(encodeURI(anchor!));
  expect(await page.locator(".markdown-document h2").first().evaluate(el => el.id)).toBe(anchor!.slice(1));
  await page.goto("/docs/index");
  await page.locator(".markdown-document").getByRole("link", { name: "17 agents, tools and testing", exact: true }).click();
  await expect(page).toHaveURL(/\/docs\/17-agent-tools-testing-plan$/);
  await expect(page.locator(".markdown-document")).toContainText("A01");
  await page.goBack();
  await expect(page).toHaveURL(/\/docs\/index$/);
});

for (const theme of ["dark", "light"] as const) {
  for (const width of [1440, 390]) {
    test(`${theme} ${width}px 文档阅读排版与可访问性`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
      for (const url of ["/docs/02-architecture", "/docs/17-agent-tools-testing-plan", "/docs/getting-started"]) {
        await page.goto(url);
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), url).toBe(false);
        const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
        expect(results.violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => n.target) })), url).toEqual([]);
      }
      if (width === 390) {
        const code = page.locator(".markdown-document pre").first();
        await code.focus();
        await expect(code).toBeFocused();
        await page.locator(".document-mobile-toc summary").click();
        await expect(page.getByRole("navigation", { name: "本页章节（移动版）" })).toBeVisible();
      }
    });
  }
}

test("未知文档返回404，源码入口仍指向独立GitHub仓库", async ({ page }) => {
  const response = await page.goto("/docs/not-a-document");
  expect(response?.status()).toBe(404);
  await page.goto("/docs/02-architecture");
  const source = page.locator(".document-source").getByRole("link", { name: "GitHub 源码 ↗" });
  await expect(source).toHaveAttribute("href", "https://github.com/yduan10/agent-repair-workbench");
  await expect(source).toHaveAttribute("target", "_blank");
});

test("架构图可阅读、随主题切换，手机键盘可滚动并查看源码", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto("/docs/02-architecture");
  const diagram = page.locator(".document-diagram img");
  await expect(diagram).toBeVisible();
  await expect.poll(() => diagram.evaluate(el => (el as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  expect(decodeURIComponent((await diagram.getAttribute("src"))!)).not.toContain("<foreignObject");
  await page.getByRole("combobox", { name: "外观主题" }).selectOption("light");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  const lightImage = await diagram.getAttribute("src");
  await page.getByRole("combobox", { name: "外观主题" }).selectOption("dark");
  await expect.poll(() => diagram.getAttribute("src")).not.toBe(lightImage);
  await expect.poll(() => diagram.evaluate(el => (el as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  const scroll = page.locator(".document-diagram-scroll");
  await scroll.focus();
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => scroll.evaluate(el => el.scrollLeft)).toBeGreaterThan(0);
  await page.getByText("查看图表源码", { exact: true }).click();
  await expect(page.getByRole("region", { name: "图表源码，可横向滚动" })).toContainText("flowchart LR");
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
});
