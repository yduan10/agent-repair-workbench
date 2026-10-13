import Link from "next/link";
import { ArrowUpRight, CheckCircle2 } from "lucide-react";
import { capabilities, CapabilityKey } from "../lib/capabilities";

export default function ModuleProgress({ section }: { section: CapabilityKey }) {
  const capability = capabilities[section];
  return (
    <section className="module-progress" aria-label="真实能力进度">
      <div className="progress-heading">
        <h2>当前能力与进度</h2>
        <Link href={`/updates#${capability.milestone}`} className="text-link">
          查看验收记录 <ArrowUpRight size={14} aria-hidden="true" />
        </Link>
      </div>
      <dl className="progress-facts">
        <div><dt><CheckCircle2 size={16} aria-hidden="true" />已完成的基础</dt><dd>{capability.completed}</dd></div>
        <div><dt>现在怎么用</dt><dd>{capability.access}</dd></div>
        <div><dt>下一步</dt><dd>{capability.next}</dd></div>
      </dl>
      {section === "connections" && (
        <details className="cli-instructions">
          <summary>使用已完成的 CLI 功能</summary>
          <p>在 agent-workbench 项目根目录运行。MCP 示例使用已审核配置；容器示例还需本机 Docker 和明确准备的镜像。</p>
          <h3>真实 MCP 调用与检查</h3>
          <pre><code>uv run --frozen agent-workbench mcp-check --server-config examples/mcp/pass-server.json --case examples/mcp/lookup-case.json</code></pre>
          <h3>受控容器执行</h3>
          <p>本机已有固定基础镜像后，先显式构建项目镜像；运行器不会自动拉取镜像。</p>
          <pre><code>{"uv run --frozen python containers/p0_03/prepare.py\nuv run --frozen agent-workbench sandbox-check --server-config examples/sandbox/pass-server.json --case examples/mcp/lookup-case.json"}</code></pre>
          <p>这些命令运行项目的合成验收示例，不代表任意工具或仓库都已支持。</p>
        </details>
      )}
      <div className="progress-footnote">
        <span>开发能力快照 · 2026-10-13 · 非实时任务状态</span>
        <Link href="/workbench" className="text-link">打开调用检查 <ArrowUpRight size={14} aria-hidden="true" /></Link>
      </div>
    </section>
  );
}
