"use client";
import { useEffect, useRef, useState } from "react";
import { Download, FileJson2, ShieldCheck } from "lucide-react";
import { AgentCatalog, AgentRole, loadAgentContracts, roleIds } from "../lib/agent-contracts";

const roles = {
  diagnosis: { label: "诊断", description: "从调用证据追查问题，证据不足时保留假设。", boundary: "可申请检查和复现，不能修改代码。" },
  repair: { label: "修复", description: "围绕已定位的问题，提出限定文件范围内的候选修改。", boundary: "只能提出建议，不能应用补丁或改动验收规则。" },
  verification: { label: "验证", description: "核对证据与建议，说明仍需验证的部分。", boundary: "可申请检查和复现，不能自行宣布候选通过。" },
};
const tools = {
  read_evidence: { label: "读取调用证据", detail: "指定任务的摘要、检查项与事件" },
  read_contract: { label: "读取工具契约", detail: "固定版本的输入与输出约束" },
  read_source: { label: "读取源码片段", detail: "授权快照与文件，单次最多 200 行" },
  check_contract: { label: "申请契约检查", detail: "使用程序检查原始案例" },
  request_reproduction: { label: "申请受控复现", detail: "只允许审核过的案例与配置" },
};

export default function AgentContracts() {
  const [catalog, setCatalog] = useState<AgentCatalog | null>(null);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  const [role, setRole] = useState<AgentRole>("diagnosis");
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  useEffect(() => {
    const controller = new AbortController();
    setError(false); setCatalog(null);
    loadAgentContracts(controller.signal).then(data => {
      if (!controller.signal.aborted) setCatalog(data);
    }).catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [retry]);
  const selected = catalog?.roles.find(item => item.id === role);
  function download() {
    if (!catalog) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(catalog, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url; link.download = "agent-contracts-v2.json"; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <section className="agent-contracts" aria-labelledby="agent-contracts-title">
    <div className="contracts-heading">
      <div><h2 id="agent-contracts-title">协作接口</h2><p>查看各角色的职责、权限与实际数据约定。</p></div>
      <span className="contracts-status"><FileJson2 size={15} aria-hidden="true" />CLI 可运行 · 网页只读</span>
    </div>
    {error ? <div className="contracts-empty" role="alert"><p>暂时无法读取接口目录，请确认本地 API 已启动后重试。</p><button className="secondary-button" onClick={() => setRetry(value => value + 1)}>重试读取</button></div>
      : !catalog ? <p className="contracts-empty" role="status">正在读取本地接口目录…</p>
      : <>
        <div className="contracts-tabs" role="tablist" aria-label="协作角色">
          {roleIds.map((id, index) => <button key={id} ref={el => { buttons.current[index] = el; }}
            id={`role-tab-${id}`} role="tab" aria-selected={role === id} aria-controls="role-contract-panel"
            tabIndex={role === id ? 0 : -1} onClick={() => setRole(id)}
            onKeyDown={event => {
              let next = index;
              if (event.key === "ArrowRight") next = (index + 1) % 3;
              else if (event.key === "ArrowLeft") next = (index + 2) % 3;
              else if (event.key === "Home") next = 0;
              else if (event.key === "End") next = 2;
              else return;
              event.preventDefault(); setRole(roleIds[next]); buttons.current[next]?.focus();
            }}>{roles[id].label}角色</button>)}
        </div>
        <div id="role-contract-panel" role="tabpanel" aria-labelledby={`role-tab-${role}`} className="contracts-panel" tabIndex={0}>
          <div className="contract-role-copy"><h3>{roles[role].description}</h3><p><ShieldCheck size={16} aria-hidden="true" />{roles[role].boundary}</p></div>
          <ul className="contract-tool-list">{selected?.allowed_tools.map(name => <li key={name}><details>
            <summary><span><strong>{tools[name].label}</strong><small>{tools[name].detail}</small></span><code>{name}</code></summary>
            <pre tabIndex={0} aria-label={`${tools[name].label}请求格式`}><code>{JSON.stringify(catalog.tools.find(tool => tool.name === name)?.request_schema, null, 2)}</code></pre>
          </details></li>)}</ul>
          <details className="role-output" key={role}><summary>查看{roles[role].label}角色输出格式</summary><pre tabIndex={0} aria-label="角色输出格式"><code>{JSON.stringify(selected?.output_schema, null, 2)}</code></pre></details>
        </div>
        <div className="contracts-bottom"><p>来自本地服务的可执行契约。这里不会调用模型、运行工具或发送源码。</p><button onClick={download}><Download size={15} aria-hidden="true" />下载接口约定</button></div>
      </>}
  </section>;
}
