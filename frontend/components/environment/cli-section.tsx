import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { Callout } from "../ui/callout";
import { Command, EnvSection } from "./section";
import { commands, docs } from "./commands";

const examples = [
  { name: "mcp-check", command: commands.mcpCheck, text: "通过 stdio 启动内置示例 MCP 服务，检查一次工具调用。不需要 Docker，适合先确认环境能跑通。" },
  { name: "sandbox-check", command: commands.sandboxCheck, text: "在断网的隔离容器里运行同一个调用，结果写入运行记录。需要先准备复现环境。" },
];

export function CliSection() {
  return <EnvSection id="cli" title="命令行" description="网页上的检查和复现也可以在终端运行。在项目根目录执行。"
    actions={<Link className="btn btn-ghost btn-sm" href={docs.mcp}>命令行说明<ArrowUpRight size={13} aria-hidden="true" /></Link>}>
    <div className="pane env-pane">
      {examples.map(example => <div className="env-cli-item" key={example.name}>
        <div className="env-cli-head"><code translate="no">{example.name}</code><p className="muted">{example.text}</p></div>
        <Command value={example.command} label={`${example.name} 命令`} />
      </div>)}
    </div>
    <Callout>接入自己的 MCP 服务尚未开放；目前只能运行内置示例。</Callout>
  </EnvSection>;
}
