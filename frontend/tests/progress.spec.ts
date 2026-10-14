import { test, expect } from "@playwright/test";

test("每个模块从侧栏到首屏展示实际进度与可用入口", async ({ page }) => {
  const writes: string[] = [];
  page.on("request", request => { if (request.method() !== "GET") writes.push(request.url()); });
  const states = [
    ["tasks", "任务总览", "受控复现", "P1-01a"],
    ["diagnosis", "诊断分析", "网页只读", "P0-06"],
    ["repairs", "候选修复", "待开发", "P0-06"],
    ["regression", "回归验证", "待开发", "P0-06"],
    ["memory", "项目记忆", "待开发", "P1-02"],
    ["connections", "工具接入", "CLI 可用", "四种固定合成场景"],
  ];
  for (const [section, label, status, next] of states) {
    await page.goto(`/workspace/${section}`);
    const navigation = page.getByRole("navigation", { name: "产品模块" });
    await expect(navigation).not.toContainText("预览");
    await expect(navigation.getByRole("link", { name: new RegExp(label) })).toContainText(status);
    await expect(navigation.getByRole("link", { name: /调用检查/ })).toContainText("网页可用");
    await expect(page.locator(".topbar .preview-status")).toHaveText(status);
    if (section === "tasks" || section === "diagnosis") await page.getByText("当前能力与后续计划", { exact: true }).click();
    const progress = page.getByRole("region", { name: "真实能力进度" });
    await expect(progress).toBeVisible();
    await expect(progress).toContainText("已完成的基础");
    await expect(progress).toContainText("现在怎么用");
    await expect(progress).toContainText(next);
    await expect(progress).toContainText("非实时任务状态");
    if (section === "regression") {
      await expect(progress).toContainText("344 项 Python 验收用例");
      await expect(progress).toContainText("尚不能在网页运行用户项目的基线与候选对比");
    }
  }
  await page.getByText("使用已完成的 CLI 功能", { exact: true }).click();
  await expect(page.locator(".cli-instructions")).toContainText("agent-workbench mcp-check");
  await expect(page.locator(".cli-instructions")).toContainText("agent-workbench sandbox-check");
  await page.getByRole("link", { name: "查看验收记录", exact: true }).click();
  await expect(page).toHaveURL(/\/updates#P0-03$/);
  await expect(page.locator("#P0-03 summary")).toBeVisible();
  expect(writes).toEqual([]);
});
