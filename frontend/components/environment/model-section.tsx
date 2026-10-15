"use client";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { useEnvironmentStatus } from "../ui/environment-context";
import { StatusBadge } from "../ui/status";
import { Skeleton } from "../ui/skeleton";
import { modelReasonMessage } from "../../lib/environment";
import { CopyCode, EnvSection, SettingRow } from "./section";
import { docs, modelVariables } from "./commands";

export function ModelSection() {
  const env = useEnvironmentStatus();
  const model = env.analysis?.model;
  const status = env.checkedAt === null ? null
    : !env.api.ok ? { tone: "neutral" as const, label: "未知", text: "连接本机服务后显示。" }
    : !model ? { tone: "unknown" as const, label: "无法读取", text: "分析目录读取失败。确认本机服务与网页版本一致后重新检查。" }
    : model.configured ? { tone: "pass" as const, label: "已配置", text: "可以发起需要模型的分析。" }
    : { tone: "unknown" as const, label: model.reason === "MODEL_CONFIGURATION_INVALID" ? "配置无效" : "未配置", text: `${modelReasonMessage(model.reason)}调用检查、复现和「仅检查契约」分析不需要模型。` };

  return <EnvSection id="model" title="模型" description="分析使用你自己授权的兼容接口。网页只显示是否已配置，不读取或显示密钥。"
    actions={<Link className="btn btn-ghost btn-sm" href={docs.model}>配置说明<ArrowUpRight size={13} aria-hidden="true" /></Link>}>
    <div className="pane env-pane">
      <SettingRow label="状态" aside={status && <StatusBadge tone={status.tone}>{status.label}</StatusBadge>}>
        {status ? <p className="muted">{status.text}</p> : <Skeleton width="60%" height={13} />}
      </SettingRow>
      <SettingRow label="环境变量">
        <p className="muted">{model?.configured
          ? "更换模型时，修改下面的变量后重启本机服务。"
          : "模型在启动本机服务时通过环境变量配置：在同一终端设置下面的变量，再启动或重启本机服务。"}</p>
        <table className="env-vars">
          <caption className="sr-only">模型环境变量</caption>
          <thead className="sr-only"><tr><th scope="col">变量名</th><th scope="col">用途</th></tr></thead>
          <tbody>{modelVariables.map(variable => <tr key={variable.name}>
            <th scope="row"><CopyCode value={variable.name} label={`变量名 ${variable.name}`} /></th>
            <td>{variable.purpose}</td>
          </tr>)}</tbody>
        </table>
      </SettingRow>
    </div>
  </EnvSection>;
}
