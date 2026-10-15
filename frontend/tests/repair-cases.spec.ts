import { test, expect } from "@playwright/test";
import { detailSchema } from "../lib/repairs";
const upstream = process.env.AWB_REPAIR_CASES_LIVE_URL;
if (upstream && !/^http:\/\/127\.0\.0\.1:\d{4,5}$/.test(upstream))
  throw new Error("invalid_live_api");
test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "ignoreErrors" }); });
test("真实临时SQLite/API两案例：标签与task绑定、v1与未知case拒绝", async ({
  page,
  request,
}) => {
  test.skip(!upstream, "需要显式本地两案例API；无模型或容器执行");
  const response = await request.get(`${upstream}/api/repairs`);
  expect(response.ok()).toBeTruthy();
  const listing = await response.json();
  expect(listing.schema_version).toBe(2);
  expect(
    new Set(listing.repairs.map((t: { case_id: string }) => t.case_id)),
  ).toEqual(new Set(["output_mismatch", "counter_offset"]));
  await page.route("**/api/repairs**", async (route) => {
    const u = new URL(route.request().url());
    expect(route.request().method()).toBe("GET");
    const res = await request.get(`${upstream}${u.pathname}${u.search}`);
    await route.fulfill({ response: res });
  });
  await page.goto("/workspace/repairs");
  for (const item of listing.repairs) {
    const label =
      item.case_id === "output_mismatch" ? "返回类型错误" : "计数值偏移";
    const link = page.locator(`.rp-task-link[href*="task=${item.task_id}"]`);
    await expect(link).toContainText(label);
    await link.click();
    await expect(page.getByRole("region", { name: "修复记录详情" }).getByRole("heading", { name: label, exact: true })).toBeVisible();
    const detail = await (
      await request.get(`${upstream}/api/repairs/${item.task_id}`)
    ).json();
    expect(detailSchema.safeParse(detail).success).toBe(true);
    expect(
      detailSchema.safeParse({ ...detail, schema_version: 1 }).success,
    ).toBe(false);
    expect(
      detailSchema.safeParse({
        ...detail,
        task: { ...detail.task, case_id: "unknown" },
      }).success,
    ).toBe(false);
    // Synthetic host DTO only: prove each current verified case keeps its own fingerprint.
    const id = "20000000-0000-4000-8000-000000000001",
      sha = "a".repeat(64),
      time = "2026-10-14T00:00:00Z";
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
    const withCandidate = {
      ...detail,
      task: { ...detail.task, candidate_count: 1 },
      candidates: [
        {
          candidate_id: id,
          sequence: 1,
          status: "committed",
          snapshot_status: "verified",
          snapshot_sha256: sha,
          error_code: null,
          created_at: time,
          finished_at: time,
        },
      ],
      comparisons: [
        {
          schema_version: 1,
          task_id: item.task_id,
          comparison_id: "30000000-0000-4000-8000-000000000001",
          candidate_id: id,
          status: "finished",
          verification: "verified",
          recorded_outcome: "candidate_verified",
          current_outcome: "candidate_verified",
          reason: "frozen_suite_passed",
          unavailable_reason: null,
          suite_sha256: sha,
          oracle_sha256: sha,
          created_at: time,
          finished_at: time,
          accepted: false,
          slots: [
            "baseline_wrong_type",
            "baseline_pass",
            "candidate_wrong_type",
            "candidate_pass",
          ].map((slot, index) => ({
            slot,
            status: index === 0 ? "failed" : "passed",
            cleanup: "removed",
            steps: names.map((name) => {
              const failed =
                index === 0 &&
                ["valid_one", "valid_zero", "valid_negative"].includes(name);
              return {
                name,
                status: failed ? "failed" : "passed",
                code: failed
                  ? item.case_id === "output_mismatch"
                    ? "count_type"
                    : "count_value"
                  : "ok",
                result_sha256: null,
              };
            }),
          })),
        },
      ],
    };
    expect(detailSchema.safeParse(withCandidate).success).toBe(true);
    for (const length of [0, 1, 3]) {
      const malformed = {
        ...withCandidate,
        comparisons: [
          {
            ...withCandidate.comparisons[0],
            slots: withCandidate.comparisons[0].slots.slice(0, length),
          },
        ],
      };
      expect(() => detailSchema.safeParse(malformed)).not.toThrow();
      expect(detailSchema.safeParse(malformed).success).toBe(false);
    }
    withCandidate.task.case_id =
      item.case_id === "output_mismatch" ? "counter_offset" : "output_mismatch";
    expect(detailSchema.safeParse(withCandidate).success).toBe(false);
  }
  await page.route("**/api/repairs?limit=50", (route) =>
    route.fulfill({ json: { ...listing, schema_version: 1 } }),
  );
  await page.getByRole("button", { name: "刷新", exact: true }).click();
  await expect(page.locator("#main").getByRole("alert")).toContainText(
    "格式或关联与页面不一致",
  );
});
