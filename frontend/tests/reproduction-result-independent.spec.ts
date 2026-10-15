import { test, expect, Page } from "@playwright/test";
import { reproductionResult } from "../lib/reproduction-result";
import type { RunView, SandboxReport } from "../lib/runs";
import { createHash } from "node:crypto";

const A = "10000000-0000-4000-8000-000000000001";
const B = "10000000-0000-4000-8000-000000000002";
const ATTEMPT = "20000000-0000-4000-8000-000000000001";
const HASH = "a".repeat(64);
const report = {
  sandbox_report_version: 1, record_id: A, run_id: ATTEMPT,
  mcp: {
    mcp_report_version: 1, invocation_id: ATTEMPT, adapter_outcome: "completed",
    source: {
      kind: "mcp_sdk_normalized", association: "sdk_dispatch", wire_json_integrity: "not_checked", sdk_version: "2.3.0", adapter_version: "1",
      protocol_version: "2025-11-25", profile: "isolated-fixture", config_sha256: HASH, case_sha256: HASH,
      server_code_sha256: HASH, server_dependencies_sha256: null, tool_schema_sha256: HASH, server_revision: null, source_tree_sha256: null,
    },
    contract_report: { schema_version: 1, checker_version: "0.1.0", evidence_sha256: HASH, status: "passed", checks: { input: "passed", output: "passed" }, findings: [], findings_truncated: false },
    preflight_findings: [], content_summary: [], elapsed_ms: 20,
  },
  execution: { image_id: `sha256:${HASH}`, source_sha256: HASH, scenario: "pass", seed: 0, policy: "offline-readonly-v1", stdout_bytes: 42, stderr_bytes: 0, frames: 3, error: null, cleanup: "removed", container_exit_code: 0, oom_killed: false },
};
const reportBytes = JSON.stringify(report);
const run = (id = A, status = "succeeded") => ({
  run_id: id, attempt_id: status === "queued" ? null : ATTEMPT, status, version: 3,
  created_at: 1791853200, updated_at: 1791853205, lease_until: null, profile: "isolated-fixture", scenario: "pass",
  config_sha256: HASH, case_sha256: HASH, report_sha256: status === "succeeded" ? createHash("sha256").update(reportBytes).digest("hex") : null, executor_state: null,
});

for (const mutation of ["none", "config", "case", "oom", "cancelled", "wrong-input", "wrong-path", "adapter", "normal"]) test(`独立复现判定：${mutation}`, () => {
  const result = structuredClone(report) as SandboxReport;
  const record = { ...run(), status: "failed", scenario: "tool_error" } as RunView;
  result.execution.scenario = "tool_error";
  result.mcp.adapter_outcome = "tool_error";
  result.mcp.contract_report!.status = "failed";
  result.mcp.contract_report!.checks.output = "skipped";
  result.mcp.contract_report!.findings = [{ code: "tool_error", phase: "result", instance_path: "/result", schema_path: "" }];
  if (mutation === "config") result.mcp.source.config_sha256 = "b".repeat(64);
  if (mutation === "case") result.mcp.source.case_sha256 = "b".repeat(64);
  if (mutation === "oom") result.execution.oom_killed = true;
  if (mutation === "cancelled") record.status = "cancelled";
  if (mutation === "wrong-input") result.mcp.contract_report!.checks.input = "failed";
  if (mutation === "wrong-path") result.mcp.contract_report!.findings[0].instance_path = "/arguments";
  if (mutation === "adapter") result.mcp.adapter_outcome = "protocol_error";
  if (mutation === "normal") {
    const output = reproductionResult(run() as RunView, report as SandboxReport);
    expect(output.title).toBe("正常调用通过"); expect(output.tone).toBe("pass"); return;
  }
  const before = JSON.stringify({record,result});
  const output = reproductionResult(record,result);
  expect(output.title === "已复现工具错误").toBe(mutation === "none");
  expect(JSON.stringify({record,result})).toBe(before);
});

test("结果未知不推断工具是否执行，也不自动重试", () => {
  const result = structuredClone(report) as SandboxReport;
  result.execution.scenario = "timeout";
  result.mcp.adapter_outcome = "outcome_unknown";
  result.mcp.contract_report = null;
  const output = reproductionResult({ ...run(), status: "outcome_unknown", scenario: "timeout" } as RunView, result);
  expect(output).toEqual({ title: "结果未知", detail: "发送后没有收到结果，无法确认工具是否执行；不会自动重试。", tone: "unknown" });
});
