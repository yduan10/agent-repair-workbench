import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import passing from "../../examples/passing.json";

test("产品入口到真实检查与报告下载", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "体验调用检查" }).click();
  await expect(page).toHaveURL(/workbench/);
  await expect(
    page.getByRole("heading", { name: "运行检查后，在这里查看结果" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "运行检查", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "发现不符合项" }),
  ).toBeVisible();
  await expect(
    page.getByText("/result/structured_content/count", { exact: true }),
  ).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载报告" }).click();
  expect((await downloaded).suggestedFilename()).toBe("check-report.json");
  await page.screenshot({
    path: "../artifacts/ui-check-desktop.png",
    fullPage: true,
  });
});

test("成功、缺失结果与编辑失效", async ({ page }) => {
  await page.goto("/workbench");
  await page.getByRole("button", { name: "正常调用", exact: true }).click();
  await page.getByRole("button", { name: "运行检查", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "检查通过", exact: true }),
  ).toBeVisible();
  await page.getByRole("textbox", { name: "调用证据", exact: true }).fill("{}");
  await expect(
    page.getByRole("heading", { name: "检查通过", exact: true }),
  ).not.toBeVisible();
  await page.getByRole("button", { name: "运行检查", exact: true }).click();
  await expect(
    page.getByText("invalid_document", { exact: true }),
  ).toBeVisible();
  page.on("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "缺失结果", exact: true }).click();
  await page.getByRole("button", { name: "运行检查", exact: true }).click();
  await expect(page.getByText("result_missing", { exact: true })).toBeVisible();
});

test("浏览器保持原始数字与重复键", async ({ page }) => {
  await page.goto("/workbench?source=custom");
  const raw = JSON.stringify(passing).replace(
    '"id":1',
    '"id":9007199254740993.0',
  );
  await page.getByRole("textbox", { name: "调用证据", exact: true }).fill(raw);
  await page.getByRole("button", { name: "运行检查", exact: true }).click();
  await expect(
    page.getByText("unsupported_number", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "调用证据", exact: true })
    .fill(JSON.stringify(passing).replace('"id":1', '"id":1,"id":2'));
  await page.getByRole("button", { name: "运行检查", exact: true }).click();
  await expect(
    page.getByText("invalid_document", { exact: true }),
  ).toBeVisible();
});

test("导入文件与断网恢复", async ({ page }) => {
  await page.goto("/workbench");
  await page
    .getByLabel("导入 JSON 文件")
    .setInputFiles({
      name: "call.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(passing)),
    });
  await page.route("**/api/check", (route) => route.abort());
  await page.getByRole("button", { name: "运行检查", exact: true }).click();
  await expect(page.locator("#input-error")).toContainText("未能取得检查结果");
  await page.unroute("**/api/check");
  await page.getByRole("button", { name: "运行检查", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "检查通过", exact: true }),
  ).toBeVisible();
});

test("预览模块可导航、筛选与展开", async ({ page }) => {
  for (const section of [
    "diagnosis",
    "repairs",
    "regression",
    "memory",
    "connections",
  ]) {
    await page.goto(`/workspace/${section}`);
    await expect(page.getByText("完整交互预览", { exact: true })).toBeVisible();
    await page
      .getByRole("button", {
        name:
          section === "connections"
            ? "查看连接流程"
            : /查看示例任务|预览诊断依据|预览候选补丁|预览回归对照|预览经验条目/,
      })
      .click();
    await expect(page.getByRole("region", { name: "示例详情" })).toBeVisible();
  }
  await page.goto("/workspace/diagnosis");
  await page.getByRole("textbox", { name: "筛选示例" }).fill("不存在");
  await expect(
    page.getByRole("heading", { name: "没有匹配的示例" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "清空筛选" }).click();
  await expect(
    page.getByRole("button", { name: "预览诊断依据" }),
  ).toBeVisible();
});

for (const width of [1440, 390]) {
  test(`产品页和各模块 ${width}px 布局及可访问性`, async ({ page }) => {
    await page.setViewportSize({ width, height: 960 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    for (const path of [
      "/",
      "/workbench",
      "/workspace/tasks",
      "/workspace/diagnosis",
      "/workspace/repairs",
      "/workspace/regression",
      "/workspace/memory",
      "/workspace/connections",
    ]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      );
      expect(overflow, path).toBe(false);
      const accessibility = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa"])
        .analyze();
      expect(
        accessibility.violations.map((v) => ({
          id: v.id,
          nodes: v.nodes.map((n) => n.target),
        })),
        path,
      ).toEqual([]);
      if (path === "/")
        await page.screenshot({
          path: `../artifacts/ui-home-${width}.png`,
          fullPage: true,
        });
    }
  });
}

test("BOM 文件保真与未保存导航保护", async ({ page }) => {
  await page.goto("/workbench");
  const raw = Buffer.concat([
    Buffer.from([0xef, 0xbb, 0xbf]),
    Buffer.from(JSON.stringify(passing)),
  ]);
  await page
    .getByLabel("导入 JSON 文件")
    .setInputFiles({
      name: "bom.json",
      mimeType: "application/json",
      buffer: raw,
    });
  const request = page.waitForRequest((r) => r.url().endsWith("/api/check"));
  await page.getByRole("button", { name: "运行检查", exact: true }).click();
  expect((await request).postDataBuffer()).toEqual(raw);
  await expect(
    page.getByText("invalid_document", { exact: true }),
  ).toBeVisible();
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("link", { name: "任务总览 记录可用" }).click();
  await expect(page).toHaveURL(/workbench/);
  await expect(
    page.getByRole("textbox", { name: "调用证据", exact: true }),
  ).toHaveValue(raw.toString("utf8"));
  for (const name of ["产品介绍", "开发记录", "项目文档"]) {
    page.once("dialog", dialog => dialog.dismiss());
    await page.getByRole("region", { name: "产品信息" }).getByRole("link", { name, exact: true }).click();
    await expect(page).toHaveURL(/workbench/);
    await expect(page.getByRole("textbox", { name: "调用证据", exact: true })).toHaveValue(raw.toString("utf8"));
  }
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("link", { name: "任务总览 记录可用" }).click();
  await expect(page).toHaveURL(/workspace\/tasks/);
});

test("非法模块路径返回 404", async ({ page }) => {
  const response = await page.goto("/workspace/toString");
  expect(response?.status()).toBe(404);
});
