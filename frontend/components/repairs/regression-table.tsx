import { Check, Minus, X } from "lucide-react";
import { StatusBadge, type Tone } from "../ui/status";
import { cleanupLabels, codeLabels, slotStatusLabels, stepLabels, steps, type Comparison } from "../../lib/repairs";

type Slot = Comparison["slots"][number];
type Step = Slot["steps"][number];
const scenarios = [
  { key: "wrong_type", label: "原错误场景", expect: "基线应复现错误，候选应通过" },
  { key: "pass", label: "正常调用场景", expect: "基线与候选都应通过" },
] as const;
const sides = [{ key: "baseline", label: "基线" }, { key: "candidate", label: "候选" }] as const;

function StepCell({ step }: { step?: Step }) {
  if (!step || step.status === "not_run") return <span className="rp-cell" data-tone="neutral"><Minus size={13} aria-hidden="true" />{step ? codeLabels[step.code] : "尚未执行"}</span>;
  if (step.status === "passed") return <span className="rp-cell" data-tone="pass"><Check size={13} aria-hidden="true" />通过</span>;
  return <span className="rp-cell" data-tone="fail"><X size={13} aria-hidden="true" />{codeLabels[step.code]}</span>;
}
function slotTone(slot?: Slot): Tone {
  if (!slot) return "neutral";
  return ({ passed: "pass", failed: "fail", inconclusive: "unknown", cancelled: "neutral", outcome_unknown: "unknown" } as const)[slot.status];
}
function slotLabel(slot: Slot | undefined, scenario: string, side: string) {
  if (!slot) return "尚未执行";
  if (slot.status === "failed" && scenario === "wrong_type" && side === "baseline") return "已复现错误";
  return slotStatusLabels[slot.status];
}

/** Baseline vs candidate for both scenarios, one row per frozen check. */
export function RegressionTable({ comparison }: { comparison: Comparison }) {
  const slot = (scenario: string, side: string) => comparison.slots.find(item => item.slot === `${side}_${scenario}`);
  const columns = scenarios.flatMap(scenario => sides.map(side => ({ scenario: scenario.key, side: side.key, slot: slot(scenario.key, side.key) })));
  return <div className="table-scroll rp-reg-scroll" tabIndex={0} role="region" aria-label="基线与候选逐项对比">
    <table className="data-table rp-reg-table">
      <caption className="sr-only">回归结果：基线与候选在原错误场景和正常调用场景下的逐项检查</caption>
      <colgroup><col className="rp-reg-rule-col" />{columns.map(column => <col key={`${column.scenario}-${column.side}`} />)}</colgroup>
      <thead>
        <tr>
          <th scope="col" rowSpan={2} className="rp-reg-rule">检查项</th>
          {scenarios.map(scenario => <th key={scenario.key} scope="colgroup" colSpan={2} className="rp-reg-group">
            <span>{scenario.label}</span><span className="rp-reg-expect">{scenario.expect}</span>
          </th>)}
        </tr>
        <tr>{columns.map(column => <th key={`${column.scenario}-${column.side}`} scope="col" className="rp-reg-side" data-first={column.side === "baseline" || undefined}>{column.side === "baseline" ? "基线" : "候选"}</th>)}</tr>
      </thead>
      <tbody className="rp-reg-summary">
        <tr>
          <th scope="row" className="rp-reg-rule">场景结果</th>
          {columns.map(column => <td key={`${column.scenario}-${column.side}`} data-first={column.side === "baseline" || undefined}>
            <StatusBadge tone={slotTone(column.slot)}>{slotLabel(column.slot, column.scenario, column.side)}</StatusBadge>
          </td>)}
        </tr>
      </tbody>
      <tbody>
        {steps.map(name => <tr key={name}>
          <th scope="row" className="rp-reg-rule">{stepLabels[name]}</th>
          {columns.map(column => <td key={`${column.scenario}-${column.side}`} data-first={column.side === "baseline" || undefined}>
            <StepCell step={column.slot?.steps.find(step => step.name === name)} />
          </td>)}
        </tr>)}
      </tbody>
      <tfoot>
        <tr>
          <th scope="row" className="rp-reg-rule">容器清理</th>
          {columns.map(column => <td key={`${column.scenario}-${column.side}`} data-first={column.side === "baseline" || undefined} className="subtle">
            {column.slot ? cleanupLabels[column.slot.cleanup] : "—"}
          </td>)}
        </tr>
      </tfoot>
    </table>
  </div>;
}
