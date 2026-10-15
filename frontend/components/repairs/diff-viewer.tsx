"use client";
import { useMemo } from "react";
import { FileCode2, ShieldCheck } from "lucide-react";
import { CopyButton } from "../ui/copy-id";
import { parseUnifiedDiff, type DiffLine } from "./parse-diff";

function StatBar({ additions, deletions }: { additions: number; deletions: number }) {
  const total = additions + deletions;
  const adds = total === 0 ? 0 : Math.round((additions / total) * 5);
  const dels = total === 0 ? 0 : Math.min(5 - adds, Math.max(deletions > 0 ? 1 : 0, Math.round((deletions / total) * 5)));
  return <span className="rp-statbar" aria-hidden="true">
    {Array.from({ length: 5 }, (_, i) => <span key={i} data-kind={i < adds ? "add" : i < adds + dels ? "del" : undefined} />)}
  </span>;
}

function Code({ line }: { line: DiffLine }) {
  const sign = line.text.slice(0, 1);
  const body = line.text.slice(1);
  if (!line.word) return <><span className="rp-sign">{sign}</span>{body}</>;
  const [start, end] = line.word;
  return <><span className="rp-sign">{sign}</span>{body.slice(0, start)}<span className="rp-word">{body.slice(start, end)}</span>{body.slice(end)}</>;
}

/** Unified diff with old/new gutters, hunk headers and intra-line highlights. */
export function DiffViewer({ patch, fallbackPath, verified }: { patch: string; fallbackPath: string; verified?: boolean }) {
  const parsed = useMemo(() => parseUnifiedDiff(patch), [patch]);
  const path = parsed.newPath ?? parsed.oldPath ?? fallbackPath;
  const renamed = parsed.oldPath && parsed.newPath && parsed.oldPath !== parsed.newPath;
  return <section className="rp-diff" aria-label={`代码差异 ${path}`}>
    <header className="rp-diff-head">
      <FileCode2 size={15} aria-hidden="true" />
      <span className="rp-diff-path" translate="no" title={path}>{renamed ? `${parsed.oldPath} → ${parsed.newPath}` : path}</span>
      <span className="rp-diff-stat tabular">
        <span className="rp-add-count">+{parsed.additions}</span>
        <span className="rp-del-count">−{parsed.deletions}</span>
        <span className="sr-only">：新增 {parsed.additions} 行，删除 {parsed.deletions} 行</span>
        <StatBar additions={parsed.additions} deletions={parsed.deletions} />
      </span>
      <span className="rp-diff-tools">
        {verified && <span className="rp-diff-verified" title="差异来自与记录摘要一致的基线和候选快照"><ShieldCheck size={13} aria-hidden="true" />快照已核对</span>}
        <CopyButton value={patch} label="补丁" className="btn btn-sm btn-ghost">复制补丁</CopyButton>
      </span>
    </header>
    {parsed.rows.length === 0 ? <p className="rp-diff-empty">候选与基线没有文本差异。</p>
      : <div className="rp-diff-scroll" tabIndex={0} role="region" aria-label={`${path} 的差异内容`}>
        <table className="rp-diff-table">
          <colgroup><col className="rp-ln-col" /><col className="rp-ln-col" /><col /></colgroup>
          <tbody>{parsed.rows.map((row, index) => row.kind === "hunk" || row.kind === "note"
            ? <tr key={index} data-kind={row.kind} data-diff-row="">
              <td className="rp-ln" colSpan={2} aria-hidden="true" />
              <td className="rp-diff-code">{row.text}</td>
            </tr>
            : <tr key={index} data-kind={row.kind} data-diff-row="">
              <td className="rp-ln" data-ln={row.oldLine ?? undefined} aria-hidden="true" />
              <td className="rp-ln" data-ln={row.newLine ?? undefined} aria-hidden="true" />
              <td className="rp-diff-code"><Code line={row} /></td>
            </tr>)}
          </tbody>
        </table>
      </div>}
  </section>;
}
