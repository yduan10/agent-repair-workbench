/** UI-08: map record states to the verdict tone used by StatusBadge / StatusDot. */
import type { Tone } from "../components/ui/status";
import type { RunView } from "./runs";
import type { AnalysisSummary } from "./analyses";
import { outcomes as repairOutcomes, type RepairTask } from "./repairs";

export function runTone(status: RunView["status"]): Tone {
  return ({ succeeded: "pass", failed: "fail", outcome_unknown: "unknown", cancelled: "neutral", queued: "running", running: "running" } as const)[status];
}
export function analysisTone(summary: AnalysisSummary): Tone {
  const outcome = summary.state.outcome;
  if (!outcome) return "running";
  return ({ check_complete: "pass", diagnosis_complete: "pass", proposal_only: "accent", inconclusive: "unknown", cancelled: "neutral", failed: "fail", budget_exceeded: "unknown", outcome_unknown: "unknown" } as const)[outcome];
}
/**
 * List and overview summaries carry only the recorded outcome, never the current comparison verification.
 * A recorded pass is therefore shown as "记录为通过" in a neutral tone; only a loaded, re-verified detail may say "回归通过".
 */
export function repairSummary(task: RepairTask): { tone: Tone; label: string } {
  const outcome = task.recorded_outcome;
  if (!outcome) return { tone: "running", label: "进行中" };
  if (outcome === "candidate_verified") return { tone: "neutral", label: "记录为通过" };
  return { tone: ({ inconclusive: "unknown", failed: "fail", cancelled: "neutral", budget_exceeded: "unknown", outcome_unknown: "unknown" } as const)[outcome], label: repairOutcomes[outcome] };
}
