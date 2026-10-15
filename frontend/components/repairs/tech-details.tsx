"use client";
import Link from "next/link";
import { CopyId } from "../ui/copy-id";
import { formatDateTime, formatNumber } from "../../lib/format";
import { comparisonOutcomes, outcomes, type Candidate, type Comparison, type RepairDetail, type RepairDiff } from "../../lib/repairs";

const Hash = ({ value, label }: { value: string; label: string }) => <CopyId value={value} length={16} label={label} />;

/** Collapsed identifiers, digests and budget usage for one repair record. */
export function TechDetails({ detail, candidate, comparison, diff }: {
  detail: RepairDetail; candidate?: Candidate; comparison?: Comparison; diff: RepairDiff | null;
}) {
  const { task } = detail;
  const { usage, budget } = task;
  const known = usage.known_input_tokens + usage.known_output_tokens;
  return <details className="rp-tech">
    <summary>技术详情</summary>
    <div className="rp-tech-grid">
      <section aria-label="标识与摘要">
        <h3>标识与摘要</h3>
        <dl className="meta-list">
          <dt>修复记录 ID</dt><dd><CopyId value={task.task_id} length={36} label="修复记录 ID" /></dd>
          {task.source_analysis_id && <><dt>来源分析</dt><dd><Link className="link mono small" href={`/workspace/diagnosis?analysis=${task.source_analysis_id}`}>{task.source_analysis_id.slice(0, 8)}</Link></dd></>}
          <dt>记录摘要</dt><dd><Hash value={task.sha256} label="记录摘要" /> <span className="subtle small">第 {task.revision} 版</span></dd>
          {candidate && <><dt>候选 ID</dt><dd><CopyId value={candidate.candidate_id} length={36} label="候选 ID" /></dd></>}
          {candidate?.snapshot_sha256 && <><dt>候选快照摘要</dt><dd><Hash value={candidate.snapshot_sha256} label="候选快照摘要" /></dd></>}
          {diff && <><dt>基线快照 ID</dt><dd><CopyId value={diff.diff.baseline.snapshot_id} length={36} label="基线快照 ID" /></dd></>}
          {diff?.diff.candidate.patch_sha256 && <><dt>补丁摘要</dt><dd><Hash value={diff.diff.candidate.patch_sha256} label="补丁摘要" /></dd></>}
          {comparison && <><dt>回归 ID</dt><dd><CopyId value={comparison.comparison_id} length={36} label="回归 ID" /></dd></>}
          {comparison && <><dt>检查项版本</dt><dd><Hash value={comparison.suite_sha256} label="检查项版本" /></dd></>}
          {comparison && <><dt>判定规则摘要</dt><dd><Hash value={comparison.oracle_sha256} label="判定规则摘要" /></dd></>}
        </dl>
      </section>
      <section aria-label="预算与用量">
        <h3>预算与用量</h3>
        <dl className="meta-list tabular">
          <dt>记录时的结果</dt><dd>{task.recorded_outcome ? outcomes[task.recorded_outcome] : "进行中"}{comparison?.recorded_outcome && <span className="subtle">（候选：{comparisonOutcomes[comparison.recorded_outcome]}）</span>}</dd>
          <dt>开始时间</dt><dd>{formatDateTime(task.started_at)}</dd>
          <dt>模型调用</dt><dd>{usage.model_calls} / {budget.model_calls}</dd>
          <dt>工具调用</dt><dd>{usage.tool_calls} / {budget.tool_calls}</dd>
          <dt>候选</dt><dd>{task.candidate_count} / {budget.candidates}</dd>
          <dt>Tokens</dt><dd>{formatNumber(known)} / {formatNumber(budget.total_tokens)} <span className="subtle">（输入 {formatNumber(usage.known_input_tokens)} · 输出 {formatNumber(usage.known_output_tokens)}）</span></dd>
          <dt>用量状态</dt><dd>{usage.usage_complete ? "已确认" : <>用量待确认<span className="subtle">（预留 {formatNumber(usage.reserved_tokens)} 计入预算）</span></>}</dd>
          <dt>单次输出上限</dt><dd>{formatNumber(budget.output_tokens)}</dd>
          <dt>时限</dt><dd>{budget.timeout_seconds} 秒</dd>
          <dt>费用</dt><dd className="subtle">未配置计价</dd>
        </dl>
      </section>
    </div>
  </details>;
}
