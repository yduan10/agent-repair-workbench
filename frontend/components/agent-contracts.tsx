"use client";
import { useEffect, useState } from "react";
import { ChevronRight, Download, ShieldCheck } from "lucide-react";
import { AgentCatalog, AgentTool, loadAgentContracts, roleIds, roleLabels, toolIds, toolLabels } from "../lib/agent-contracts";
import { Callout } from "./ui/callout";
import { CopyButton } from "./ui/copy-id";
import { SkeletonRows } from "./ui/skeleton";

function saveJSON(value: unknown, name: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** One role or tool row with an expandable JSON Schema viewer below it. */
function ContractItem({ id, label, name, description, refsLabel, refs, title, schema, file, open, onToggle, data }: {
  id: string; label: string; name: string; description: React.ReactNode; refsLabel: string; refs: { key: string; label: string; title?: string }[];
  title: string; schema: unknown; file: string; open: boolean; onToggle: () => void; data: Record<string, string>;
}) {
  const text = open ? JSON.stringify(schema, null, 2) : "";
  const panel = `schema-${id}`;
  return <li className="contract-item" {...data}>
    <div className="contract-row">
      <div className="contract-name"><strong>{label}</strong><code translate="no">{name}</code></div>
      <div className="contract-desc">{description}</div>
      <div className="contract-refs">
        <span className="contract-refs-label" aria-hidden="true">{refsLabel}</span>
        <ul className="chips" aria-label={`${label} · ${refsLabel}`}>
          {refs.map(ref => <li key={ref.key} className="chip" title={ref.title}>{ref.label}</li>)}
        </ul>
      </div>
      <div className="contract-action">
        <button type="button" className="btn btn-ghost btn-sm contract-toggle" aria-expanded={open} aria-controls={panel} aria-label={`查看契约：${title}`} onClick={onToggle}>
          <ChevronRight size={13} aria-hidden="true" />查看契约
        </button>
      </div>
    </div>
    <div id={panel} className="contract-schema" hidden={!open}>
      {open && <>
        <div className="contract-schema-bar">
          <span className="muted small">{title}契约 · JSON Schema</span>
          <span className="contract-schema-actions">
            <CopyButton value={text} label={`${title}契约`} className="btn btn-ghost btn-sm">复制</CopyButton>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => saveJSON(schema, file)}><Download size={13} aria-hidden="true" />下载</button>
          </span>
        </div>
        <pre tabIndex={0} aria-label={`${title}契约`}><code>{text}</code></pre>
      </>}
    </div>
  </li>;
}

/** Roles and tools from the live agent-contracts catalog. Read-only; never runs a tool. */
export default function AgentContracts() {
  const [catalog, setCatalog] = useState<AgentCatalog | null>(null);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  useEffect(() => {
    const controller = new AbortController();
    setError(false); setCatalog(null);
    loadAgentContracts(controller.signal).then(data => {
      if (!controller.signal.aborted) setCatalog(data);
    }).catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [retry]);
  const toggle = (key: string) => setOpen(current => {
    const next = new Set(current);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

  if (error) return <div className="contracts">
    <Callout tone="fail" title="无法读取角色与工具列表" role="alert"
      actions={<button type="button" className="btn btn-sm" onClick={() => setRetry(value => value + 1)}>重试</button>}>
      请确认本机服务已启动，然后重试。
    </Callout>
  </div>;
  if (!catalog) return <div className="contracts pane" aria-busy="true"><SkeletonRows rows={4} label="正在读取角色与工具…" /></div>;

  const callers = (tool: AgentTool) => roleIds.filter(role => catalog.roles.find(item => item.id === role)?.allowed_tools.includes(tool));
  return <div className="contracts">
    <div className="contracts-bar">
      <p className="muted small">目录版本 {catalog.catalog_version} · 数据来自本机服务</p>
      <button type="button" className="btn btn-sm" onClick={() => saveJSON(catalog, "agent-contracts-v3.json")}><Download size={13} aria-hidden="true" />下载完整目录</button>
    </div>

    <div className="pane contracts-group">
      <div className="contracts-group-title">
        <h3>角色<span className="count">{catalog.roles.length}</span></h3>
        <span className="contracts-col" aria-hidden="true">职责与边界</span><span className="contracts-col" aria-hidden="true">可调用的工具</span>
      </div>
      <ul className="contract-list">{roleIds.map(id => {
        const role = catalog.roles.find(item => item.id === id)!;
        return <ContractItem key={id} id={`role-${id}`} data={{ "data-role": id }} label={roleLabels[id].label} name={id}
          description={<><p>{roleLabels[id].duty}</p><p className="contract-boundary"><ShieldCheck size={13} aria-hidden="true" />{roleLabels[id].boundary}</p></>}
          refsLabel="可调用的工具" refs={role.allowed_tools.map(tool => ({ key: tool, label: toolLabels[tool].label, title: tool }))}
          title={`${roleLabels[id].label}角色输出`} schema={role.output_schema} file={`agent-role-${id}-output.schema.json`}
          open={open.has(`role-${id}`)} onToggle={() => toggle(`role-${id}`)} />;
      })}</ul>
    </div>

    <div className="pane contracts-group">
      <div className="contracts-group-title">
        <h3>工具<span className="count">{catalog.tools.length}</span></h3>
        <span className="contracts-col" aria-hidden="true">用途</span><span className="contracts-col" aria-hidden="true">可调用的角色</span>
      </div>
      <ul className="contract-list">{toolIds.map(name => {
        const tool = catalog.tools.find(item => item.name === name)!;
        return <ContractItem key={name} id={`tool-${name}`} data={{ "data-tool": name }} label={toolLabels[name].label} name={name}
          description={<p>{toolLabels[name].purpose}</p>}
          refsLabel="可调用的角色" refs={callers(name).map(role => ({ key: role, label: roleLabels[role].label }))}
          title={`${toolLabels[name].label}请求`} schema={tool.request_schema} file={`agent-tool-${name}-request.schema.json`}
          open={open.has(`tool-${name}`)} onToggle={() => toggle(`tool-${name}`)} />;
      })}</ul>
    </div>
  </div>;
}
