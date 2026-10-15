import { test, expect, Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
const A = "10000000-0000-4000-8000-000000000001",
  B = "10000000-0000-4000-8000-000000000002";
const C = "20000000-0000-4000-8000-000000000001",
  BASE = "30000000-0000-4000-8000-000000000001",
  COMP = "40000000-0000-4000-8000-000000000001",
  SHA = "a".repeat(64);
const names = [
  "initialize",
  "schema_before",
  "valid_one",
  "invalid_type",
  "valid_zero",
  "valid_negative",
  "schema_after",
  "alive",
];
function sample(id = A) {
  return {
    schema_version: 2,
    task: {
      task_id: id,
      case_id: "output_mismatch",
      source_analysis_id: null,
      mode: "three_role",
      phase: "finished",
      recorded_outcome: "candidate_verified",
      error_code: null,
      revision: 12,
      sha256: SHA,
      started_at: "2026-10-14T00:00:00Z",
      finished_at: "2026-10-14T00:00:05Z",
      budget: {
        total_tokens: 2000000,
        output_tokens: 8192,
        model_calls: 12,
        tool_calls: 20,
        candidates: 2,
        timeout_seconds: 600,
      },
      usage: {
        model_calls: 3,
        tool_calls: 3,
        reserved_tokens: 0,
        known_input_tokens: 300,
        known_output_tokens: 300,
        usage_complete: true,
      },
      candidate_count: 1,
      cost_amount: null,
    },
    candidates: [
      {
        candidate_id: C,
        sequence: 1,
        status: "committed",
        snapshot_status: "verified",
        snapshot_sha256: SHA,
        error_code: null,
        created_at: "2026-10-14T00:00:02Z",
        finished_at: "2026-10-14T00:00:03Z",
      },
    ],
    comparisons: [
      {
        schema_version: 1,
        task_id: id,
        comparison_id: COMP,
        candidate_id: C,
        status: "finished",
        verification: "verified",
        recorded_outcome: "candidate_verified",
        current_outcome: "candidate_verified",
        reason: "frozen_suite_passed",
        unavailable_reason: null,
        suite_sha256: SHA,
        oracle_sha256: SHA,
        created_at: "2026-10-14T00:00:03Z",
        finished_at: "2026-10-14T00:00:05Z",
        accepted: false,
        slots: [
          "baseline_wrong_type",
          "baseline_pass",
          "candidate_wrong_type",
          "candidate_pass",
        ].map((slot, i) => ({
          slot,
          status: i === 0 ? "failed" : "passed",
          cleanup: "removed",
          steps: names.map((name) => ({
            name,
            status:
              i === 0 &&
              ["valid_one", "valid_zero", "valid_negative"].includes(name)
                ? "failed"
                : "passed",
            code:
              i === 0 &&
              ["valid_one", "valid_zero", "valid_negative"].includes(name)
                ? "count_type"
                : "ok",
            result_sha256: null,
          })),
        })),
      },
    ],
  };
}
function diff(id = A) {
  const base = {
    schema_version: 1,
    snapshot_id: BASE,
    kind: "baseline",
    file: "server.py",
    manifest_sha256: SHA,
    file_sha256: SHA,
    tree_sha256: SHA,
    baseline_id: null,
    baseline_tree_sha256: null,
    patch_sha256: null,
  };
  return {
    schema_version: 1,
    task_id: id,
    candidate_id: C,
    verification: "verified",
    diff: {
      schema_version: 1,
      path: "source/server.py",
      baseline: base,
      candidate: {
        ...base,
        snapshot_id: C,
        kind: "candidate",
        baseline_id: BASE,
        baseline_tree_sha256: SHA,
        patch_sha256: SHA,
      },
      unified_diff:
        '--- baseline/source/server.py\n+++ candidate/source/server.py\n@@ -1 +1 @@\n-    return {"count": str(count)}\n+    return {"count": count}\n',
    },
  };
}
async function mock(page: Page, values = [sample(), sample(B)]) {
  const writes: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/") && r.method() !== "GET")
      writes.push(r.method());
  });
  await page.route("**/api/repairs**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/repairs")
      return route.fulfill({
        json: { schema_version: 2, repairs: values.map((v) => v.task) },
      });
    const item = values.find((v) =>
      path.startsWith(`/api/repairs/${v.task.task_id}`),
    );
    return route.fulfill(
      item
        ? { json: path.endsWith("/diff") ? diff(item.task.task_id) : item }
        : { status: 404, body: "PRIVATE_SERVER" },
    );
  });
  return writes;
}
const diffRegion = (page: Page) => page.getByRole("region", { name: "source/server.py 的差异内容" });
const verdict = (page: Page) => page.locator(".rp-verdict");

test("空态提供真实CLI说明，不灌记录不发写请求", async ({ page }) => {
  const writes = await mock(page, []);
  await page.goto("/workspace/repairs");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("修复");
  await expect(page.getByRole("heading", { name: "还没有修复记录" })).toBeVisible();
  await expect(page.getByLabel("修复命令", { exact: true })).toContainText("agent-workbench repair --mode three_role");
  await expect(page.getByRole("link", { name: "查看使用指南" })).toHaveAttribute("href", /\/docs\//);
  await expect(page.locator("#main")).not.toContainText(/P0-0\d|验收/);
  expect(writes).toEqual([]);
});
test("自动选中最新记录；代码差异带行号与统计，技术详情默认折叠且不自动接受", async ({ page }) => {
  const writes = await mock(page);
  await page.goto("/workspace/repairs");
  await expect(page).toHaveURL(new RegExp(`\\?task=${A}$`));
  await expect(page.locator(`.rp-task-link[href="/workspace/repairs?task=${A}"]`)).toHaveAttribute("aria-current", "true");
  await expect(page.locator(`.rp-task-link[href="/workspace/repairs?task=${A}"]`)).toContainText("返回类型错误");
  await expect(diffRegion(page)).toContainText('return {"count": count}');
  await expect(page.locator(".rp-diff-path")).toHaveText("source/server.py");
  await expect(page.locator(".rp-diff-stat")).toContainText("+1");
  await expect(page.locator(".rp-diff-stat")).toContainText("−1");
  await expect(page.locator('[data-kind="add"] .rp-ln').nth(1)).toHaveAttribute("data-ln", "1");
  await expect(verdict(page).getByRole("heading")).toContainText("回归通过");
  await expect(verdict(page)).toContainText("候选通过冻结规则：原错误已修复，正常路径无回归。");
  await expect(verdict(page)).toContainText("人工接受尚未开放");
  const tech = page.locator(".rp-tech").getByText(A, { exact: true });
  await expect(tech).not.toBeVisible();
  await page.getByText("技术详情", { exact: true }).click();
  await expect(tech).toBeVisible();
  await expect(page.locator("#main")).not.toContainText(/P0-0\d|验收/);
  expect(writes).toEqual([]);
});
test("回归结果：基线与候选在两个场景下逐项对照", async ({ page }) => {
  await mock(page);
  await page.goto("/workspace/regression");
  await expect(page).toHaveURL(new RegExp(`tab=regression`));
  await expect(page.getByRole("link", { name: "回归结果" })).toHaveAttribute("aria-current", "page");
  const table = page.getByRole("table");
  await expect(table).toHaveCount(1);
  await expect(table.getByRole("columnheader", { name: /原错误场景/ })).toBeVisible();
  await expect(table.getByRole("columnheader", { name: /正常调用场景/ })).toBeVisible();
  await expect(table.getByRole("rowheader")).toHaveCount(10);
  await expect(table.getByText("计数类型不一致", { exact: true })).toHaveCount(3);
  await expect(table.getByText("已复现错误", { exact: true })).toHaveCount(1);
});
test("历史通过在版本失效后不得显示当前通过", async ({ page }) => {
  const value = sample();
  Object.assign(value.comparisons[0], {
    verification: "unavailable",
    current_outcome: null,
    reason: null,
    unavailable_reason: "artifact_or_version_mismatch",
    slots: [],
  });
  value.candidates[0].snapshot_status = "unavailable";
  await mock(page, [value]);
  for (const path of ["/workspace/regression", "/workspace/repairs"]) {
    await page.goto(path);
    await expect(verdict(page).getByRole("heading")).toContainText("结果已过期");
    await expect(verdict(page)).toContainText("记录时的结果已撤回");
    await expect(page.locator("#main").getByText("回归通过", { exact: true }).filter({ visible: true })).toHaveCount(0);
    await expect(page.getByText("人工接受尚未开放")).toHaveCount(0);
    await expect(page.getByRole("table")).toHaveCount(0);
    await expect(diffRegion(page)).toHaveCount(0);
  }
});
for (const kind of ["task", "private", "accepted", "false_success"])
  test(`拒绝损坏详情：${kind}`, async ({ page }) => {
    await mock(page);
    const value = sample();
    if (kind === "task") value.comparisons[0].task_id = B;
    if (kind === "private") Object.assign(value, { claim_sha256: "PRIVATE_SECRET" });
    if (kind === "accepted") Object.assign(value.comparisons[0], { accepted: true });
    if (kind === "false_success") value.comparisons[0].slots[3].steps[0].status = "not_run";
    await page.route(`**/api/repairs/${A}`, (r) => r.fulfill({ json: value }));
    await page.goto("/workspace/repairs");
    await expect(page.locator("#main").getByRole("alert")).toContainText("与页面不一致");
    await expect(diffRegion(page)).toHaveCount(0);
    await expect(page.getByText("PRIVATE_SECRET")).toHaveCount(0);
  });
test("差异候选版本错配被拒绝，且撤回通过结果", async ({ page }) => {
  await mock(page);
  const value = diff();
  value.diff.candidate.tree_sha256 = "b".repeat(64);
  await page.route("**/api/repairs/*/candidates/*/diff", (r) => r.fulfill({ json: value }));
  await page.goto("/workspace/repairs");
  await expect(page.locator("#main").getByRole("alert")).toContainText("与记录的候选快照不一致");
  await expect(diffRegion(page)).toHaveCount(0);
  await expect(verdict(page).getByRole("heading")).toContainText("无法核对代码差异");
  // Neither the detail header nor the selected row may still claim a pass.
  await expect(page.locator(".rp-detail").getByText("回归通过", { exact: true }).filter({ visible: true })).toHaveCount(0);
  await expect(page.locator(".rp-task[data-active]")).toContainText("结果已过期");
});
test("未选中的失效记录在列表和总览中不得显示回归通过", async ({ page }) => {
  const stale = sample(B);
  Object.assign(stale.comparisons[0], {
    verification: "unavailable",
    current_outcome: null,
    reason: null,
    unavailable_reason: "artifact_or_version_mismatch",
    slots: [],
  });
  stale.candidates[0].snapshot_status = "unavailable";
  await mock(page, [sample(), stale]);
  await page.goto("/workspace/repairs");
  await expect(verdict(page).getByRole("heading")).toContainText("回归通过");
  const other = page.locator(".rp-task:not([data-active])");
  await expect(other).toHaveCount(1);
  await expect(other).toContainText("记录为通过");
  await expect(other.getByText("回归通过", { exact: true })).toHaveCount(0);
  await other.getByRole("link").click();
  await expect(page.locator(".rp-task[data-active]")).toContainText("结果已过期");
  await expect(page.locator(".rp-task:not([data-active])")).toContainText("记录为通过");
  await page.route("**/api/runs**", (r) => r.fulfill({ json: { runs: [] } }));
  await page.route("**/api/analyses**", (r) => r.fulfill({ json: { analyses: [] } }));
  await page.goto("/workspace");
  const activity = page.getByRole("table");
  await expect(activity.getByText("记录为通过", { exact: true })).toHaveCount(2);
  await expect(activity.getByText("回归通过", { exact: true })).toHaveCount(0);
});
test("差异核对失败后切到回归结果仍不显示通过", async ({ page }) => {
  await mock(page);
  const value = diff();
  value.diff.candidate.tree_sha256 = "b".repeat(64);
  await page.route("**/api/repairs/*/candidates/*/diff", (r) => r.fulfill({ json: value }));
  await page.goto("/workspace/repairs");
  await expect(verdict(page).getByRole("heading")).toContainText("无法核对代码差异");
  await page.getByRole("link", { name: "回归结果" }).click();
  await expect(page).toHaveURL(/tab=regression/);
  await expect(verdict(page).getByRole("heading")).toContainText("无法核对代码差异");
  await expect(page.locator(".rp-detail").getByText("回归通过", { exact: true }).filter({ visible: true })).toHaveCount(0);
  await expect(page.locator(".rp-task[data-active]")).toContainText("结果已过期");
  await expect(page.getByText("代码差异未通过核对")).toBeVisible();
});
test("切换记录取消迟到详情与差异，后退恢复上一条", async ({ page }) => {
  await mock(page);
  let release!: () => void;
  const waiting = new Promise<void>((r) => {
    release = r;
  });
  await page.route(`**/api/repairs/${A}/candidates/*/diff`, async (r) => {
    await waiting;
    await r
      .fulfill({ json: { ...diff(), diff: { ...diff().diff, unified_diff: "OLD_DIFF_NEVER_SHOWN" } } })
      .catch(() => {});
  });
  await page.goto("/workspace/repairs");
  await expect(verdict(page).getByRole("heading")).toContainText("回归通过");
  await page.locator(".rp-task").nth(1).getByRole("link").click();
  await expect(page).toHaveURL(new RegExp(`task=${B}`));
  await expect(diffRegion(page)).toContainText('return {"count": count}');
  release();
  await expect(page.getByText("OLD_DIFF_NEVER_SHOWN")).toHaveCount(0);
  await page.getByText("技术详情", { exact: true }).click();
  await expect(page.locator(".rp-tech").getByText(B, { exact: true })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`task=${A}`));
  await expect(page.locator(".rp-task").first().getByRole("link")).toHaveAttribute("aria-current", "true");
});
test("网络失败可重试且不显示服务端正文", async ({ page }) => {
  await mock(page);
  await page.route("**/api/repairs?limit=50", (r) => r.fulfill({ status: 503, body: "PRIVATE_BACKEND" }));
  await page.goto("/workspace/repairs");
  await expect(page.locator("#main").getByRole("alert")).toContainText("暂时不可用");
  await expect(page.getByText("PRIVATE_BACKEND")).toHaveCount(0);
  await page.unroute("**/api/repairs?limit=50");
  await page.getByRole("button", { name: "重试读取列表" }).click();
  await expect(diffRegion(page)).toBeVisible();
});
for (const width of [1280, 390])
  for (const colorScheme of ["light", "dark"] as const)
    for (const tab of ["diff", "regression"] as const)
      test(`布局与无障碍 ${tab} ${width} ${colorScheme}`, async ({ page }) => {
        await page.setViewportSize({ width, height: 1000 });
        await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
        await mock(page);
        await page.goto(tab === "regression" ? "/workspace/regression" : "/workspace/repairs");
        if (tab === "regression") await expect(page.getByRole("table").first()).toBeVisible();
        else await expect(diffRegion(page)).toBeVisible();
        await page.getByText("技术详情", { exact: true }).click();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
        const audit = await new AxeBuilder({ page }).include("#main").analyze();
        expect(audit.violations).toEqual([]);
        await page.screenshot({ path: `artifacts/ui08-repairs-${tab}-${colorScheme}-${width}.png`, fullPage: true });
      });

test("候选2在代码差异与回归结果之间保持选择，陌生候选明确回退，旧 ?repair= 链接仍可用", async ({ page }) => {
  const value = sample();
  const second = "20000000-0000-4000-8000-000000000002";
  value.task.candidate_count = 2;
  value.candidates.push({ ...value.candidates[0], candidate_id: second, sequence: 2 });
  value.comparisons.push({ ...value.comparisons[0], comparison_id: "40000000-0000-4000-8000-000000000002", candidate_id: second });
  await mock(page, [value]);
  await page.route(`**/api/repairs/${A}/candidates/${second}/diff`, (r) => {
    const d = diff();
    d.candidate_id = second;
    d.diff.candidate.snapshot_id = second;
    return r.fulfill({ json: d });
  });
  const switcher = page.getByRole("navigation", { name: "选择候选" });
  await page.goto("/workspace/repairs");
  await switcher.getByRole("link", { name: "候选 2", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`candidate=${second}`));
  await page.getByRole("link", { name: "回归结果" }).click();
  await expect(switcher.getByRole("link", { name: "候选 2", exact: true })).toHaveAttribute("aria-current", "true");
  await expect(page.getByRole("table")).toHaveCount(1);
  await page.getByRole("link", { name: "代码差异" }).click();
  await expect(switcher.getByRole("link", { name: "候选 2", exact: true })).toHaveAttribute("aria-current", "true");
  await expect(diffRegion(page)).toBeVisible();
  await page.goto(`/workspace/regression?repair=${A}&candidate=${B}`);
  await expect(page).toHaveURL(new RegExp(`task=${A}`));
  await expect(page.getByText("链接中的候选不属于这条修复记录，已改为显示候选 1。")).toBeVisible();
  await expect(switcher.getByRole("link", { name: "候选 1", exact: true })).toHaveAttribute("aria-current", "true");
});
