import { test, expect, Page } from "@playwright/test";
// Independent UI-08 follow-up counterexample. All repair API responses are mocked.
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

test("已撤回候选的通过不能在切换另一个未验收候选后恢复", async ({ page }) => {
  const value = sample();
  const second = "20000000-0000-4000-8000-000000000002";
  value.task.candidate_count = 2;
  value.candidates.push({ ...value.candidates[0], candidate_id: second, sequence: 2 });
  await mock(page, [value]);
  await page.route("**/api/repairs/*/candidates/*/diff", route => {
    const payload = diff();
    if (route.request().url().includes(second)) {
      payload.candidate_id = second;
      payload.diff.candidate.snapshot_id = second;
    } else payload.diff.candidate.tree_sha256 = "b".repeat(64);
    return route.fulfill({ json: payload });
  });
  await page.goto("/workspace/repairs");
  await expect(page.locator(".rp-detail-title")).toContainText("结果已过期");
  await page.getByRole("link", { name: "候选 2", exact: true }).click();
  await expect(page.locator(".rp-verdict")).toContainText("尚无回归结果");
  await expect(page.locator(".rp-diff-verified")).toBeVisible();
  await expect(page.locator(".rp-detail-title")).toContainText("结果已过期");
  await expect(page.locator(".rp-task[data-active]")).not.toContainText("回归通过");
  await expect(page.getByRole("link", { name: "候选 1", exact: true }).locator(".status-dot")).not.toHaveAttribute("data-tone", "pass");
});

test("一个候选撤回不抹去另一个已核验候选的任务通过", async ({ page }) => {
  const value = sample();
  const second = "20000000-0000-4000-8000-000000000002";
  value.task.candidate_count = 2;
  value.candidates.push({ ...value.candidates[0], candidate_id: second, sequence: 2 });
  value.comparisons.push({ ...value.comparisons[0], comparison_id: "40000000-0000-4000-8000-000000000002", candidate_id: second });
  await mock(page, [value]);
  await page.route("**/api/repairs/*/candidates/*/diff", route => {
    const payload = diff();
    if (route.request().url().includes(second)) {
      payload.candidate_id = second;
      payload.diff.candidate.snapshot_id = second;
    } else payload.diff.candidate.tree_sha256 = "b".repeat(64);
    return route.fulfill({ json: payload });
  });
  await page.goto("/workspace/repairs");
  await expect(page.locator(".rp-verdict")).toContainText("无法核对代码差异");
  await expect(page.locator(".rp-detail-title")).toContainText("回归通过");
  await expect(page.getByRole("link", { name: "候选 1", exact: true }).locator(".status-dot")).not.toHaveAttribute("data-tone", "pass");
  await page.getByRole("link", { name: "候选 2", exact: true }).click();
  await expect(page.locator(".rp-diff-verified")).toBeVisible();
  await expect(page.locator(".rp-verdict")).toContainText("回归通过");
  await expect(page.locator(".rp-detail-title")).toContainText("回归通过");
});

test("schema2案例名称由task决定，交叉失败指纹拒绝展示", async ({ page }) => {
  const value = sample();
  value.task.case_id = "counter_offset";
  for (const item of value.comparisons[0].slots[0].steps) {
    if (item.code === "count_type") item.code = "count_value";
  }
  await mock(page, [value]);
  await page.goto("/workspace/repairs");
  await expect(page.locator(".rp-task-link")).toContainText("计数值偏移");
  await expect(page.locator(".rp-detail-title")).toContainText("计数值偏移");
  await expect(page.locator(".rp-verdict")).toContainText("回归通过");
  await page.route("**/api/runs**", route => route.fulfill({ json: { runs: [] } }));
  await page.route("**/api/analyses**", route => route.fulfill({ json: { analyses: [] } }));
  await page.goto("/workspace");
  await expect(page.getByRole("table")).toContainText("计数值偏移");
  await expect(page.getByRole("table")).toContainText("记录为通过");
  value.task.case_id = "output_mismatch";
  await page.goto("/workspace/repairs");
  await expect(page.locator(".rp-detail").getByRole("alert")).toContainText("格式或关联与页面不一致");
  await expect(page.locator(".rp-verdict")).toHaveCount(0);
});
