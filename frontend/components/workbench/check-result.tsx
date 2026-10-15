"use client";
import { ArrowDownToLine, CornerDownRight } from "lucide-react";
import { StatusBadge } from "../ui/status";
import { PathTrail } from "../ui/path-trail";
import { CopyId } from "../ui/copy-id";
import { SkeletonRows } from "../ui/skeleton";
import { formatDuration } from "../../lib/format";
import { checkScope, scopeLabels, scopeTones, statusLabels, statusTones, verdictSummary, type Report } from "../../lib/report";
import type { FindingView } from "./describe";

export const scopeIntro = [
  { label: "调用参数", text: "call.arguments 是否符合 input_schema" },
  { label: "返回结果", text: "result.structured_content 是否符合 output_schema" },
  { label: "调用关联", text: "tool_name 与 call_id 是否对应同一次调用" },
];

type Props = {
  report: Report | null;
  busy: boolean;
  elapsed: number | null;
  findings: FindingView[];
  selected: number | null;
  onSelect: (index: number) => void;
  onDownload: () => void;
};

export function CheckResult({ report, busy, elapsed, findings, selected, onSelect, onDownload }: Props) {
  return <section className="pane wb-result" aria-labelledby="result-title" aria-busy={busy}>
    <div className="pane-head">
      <h2 id="result-title">检查结果</h2>
      {report && !busy && <div className="wb-result-actions">
        {elapsed !== null && <span className="subtle small tabular" title="从提交到收到结果的时间">{formatDuration(elapsed)}</span>}
        <button type="button" className="btn btn-sm" onClick={onDownload}><ArrowDownToLine size={13} aria-hidden="true" />下载报告</button>
      </div>}
    </div>
    <div className="wb-result-body">
      {busy ? <SkeletonRows rows={4} label="正在检查…" />
        : !report ? <div className="wb-empty">
          <h3>运行检查后，在这里查看结果</h3>
          <p>先选择内置示例，或粘贴、拖入调用证据，再点击「运行检查」。</p>
          <ul className="wb-empty-list" aria-label="检查的内容">
            {scopeIntro.map(item => <li key={item.label}><strong>{item.label}</strong><span>{item.text}</span></li>)}
          </ul>
        </div>
          : <ReportView report={report} findings={findings} selected={selected} onSelect={onSelect} />}
    </div>
  </section>;
}

function ReportView({ report, findings, selected, onSelect }: { report: Report; findings: FindingView[]; selected: number | null; onSelect: (index: number) => void }) {
  const scope = checkScope(report);
  return <>
    <div className="wb-verdict">
      <h3><StatusBadge tone={statusTones[report.status]}>{statusLabels[report.status]}</StatusBadge></h3>
      <p>{verdictSummary(report)}</p>
    </div>

    <div className="wb-block">
      <h4 className="wb-label">检查范围</h4>
      <dl className="wb-scope">
        {scope.map(row => <div key={row.key}>
          <dt>{row.label}<code translate="no">{row.target}</code></dt>
          <dd>
            <StatusBadge tone={scopeTones[row.status]} variant={row.status === "not_checked" ? "outline" : undefined}>{scopeLabels[row.status]}</StatusBadge>
            {row.note && <span className="wb-scope-note">{row.note}</span>}
          </dd>
        </div>)}
      </dl>
    </div>

    <div className="wb-block">
      <h4 className="wb-label">{report.status === "inconclusive" ? "原因" : "不符合项"}{report.findings.length > 0 && <span className="tabular">{report.findings_truncated ? `前 ${report.findings.length}` : report.findings.length}</span>}</h4>
      {report.findings.length === 0 ? <p className="wb-none">没有不符合项。可下载报告留档。</p>
        : <ol className="wb-findings" data-tone={report.status === "inconclusive" ? "unknown" : "fail"}>
          {report.findings.map((finding, index) => {
            const view = findings[index];
            const body = <>
              <span className="wb-f-head">
                <span className="wb-f-index tabular" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                <span className="wb-f-title">{view.title}</span>
                {view.target && <span className="wb-f-line tabular"><CornerDownRight size={12} aria-hidden="true" />第 {view.target.line} 行</span>}
              </span>
              <span className="wb-f-rule">{view.rule ?? view.hint}</span>
              <span className="wb-f-path">
                {finding.instance_path ? <PathTrail pointer={finding.instance_path} label="字段路径" tone={report.status === "inconclusive" ? "neutral" : "fail"} /> : <span className="subtle small">整份证据</span>}
              </span>
              <span className="wb-f-meta" translate="no">
                {finding.schema_path && <span title="契约中的规则位置">契约 {finding.schema_path}</span>}
                <code>{finding.code}</code>
              </span>
            </>;
            return <li key={`${finding.code}-${index}`}>
              {view.target
                ? <button type="button" className="wb-finding" data-selected={selected === index || undefined} onClick={() => onSelect(index)} aria-describedby="wb-locate-hint">{body}</button>
                : <div className="wb-finding">{body}</div>}
            </li>;
          })}
        </ol>}
      <span id="wb-locate-hint" hidden>在编辑器中定位</span>
      {report.findings_truncated && <p className="subtle small wb-truncated">只显示前 50 项。修正后重新检查可以看到其余项。</p>}
    </div>

    <details className="wb-tech">
      <summary>技术详情</summary>
      <dl className="meta-list">
        <dt>证据摘要（SHA-256）</dt>
        <dd>{report.evidence_sha256 ? <CopyId value={report.evidence_sha256} length={16} label="证据摘要" /> : <span className="subtle">未生成（证据未能解析）</span>}</dd>
        <dt>检查器版本</dt>
        <dd><code translate="no">{report.checker_version}</code></dd>
      </dl>
      <p className="subtle small">摘要按规范化后的 JSON 计算，与缩进和键顺序无关。摘要相同，说明两份报告检查的是同一份证据。分享报告前请注意：字段路径会暴露字段名。</p>
    </details>
  </>;
}
