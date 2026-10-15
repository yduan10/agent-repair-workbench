import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { Command, CopyCode, EnvSection, SettingRow } from "./section";
import { commands, defaultStateDir, docs } from "./commands";

const maintenance = [
  { command: commands.runsInit, text: "创建记录库；已有记录库时先备份，再用它升级到当前版本。" },
  { command: commands.runsList, text: "列出运行记录。只读，不会创建记录库。" },
  { command: commands.runsReconcile, text: "核对本机服务中断时未结束的运行。无法确认的结果标为未知，不会重试。" },
  { command: commands.runsPrune, text: "预览 30 天前可以清理的记录；加 --apply 才会删除。" },
];

export function DataSection() {
  return <EnvSection id="data" title="本机数据" description="运行和分析记录保存在本机 SQLite 数据库中，不保存原始调用参数和结果。"
    actions={<Link className="btn btn-ghost btn-sm" href={docs.records}>记录与恢复说明<ArrowUpRight size={13} aria-hidden="true" /></Link>}>
    <div className="pane env-pane">
      <SettingRow label="记录目录">
        <p><CopyCode value={defaultStateDir} label="记录目录" /><span className="muted small env-inline-note">默认，相对项目根目录</span></p>
      </SettingRow>
      <SettingRow label="更换目录">
        <p><CopyCode value="AWB_STATE_DIR" label="变量名 AWB_STATE_DIR" /></p>
        <p className="muted">命令行和本机服务要设置为同一个目录，才能看到相同的记录。</p>
      </SettingRow>
      <SettingRow label="维护命令">
        <p className="muted">在项目根目录运行。</p>
        <ul className="env-commands">{maintenance.map(item => <li key={item.command}>
          <p className="muted small">{item.text}</p>
          <Command value={item.command} />
        </li>)}</ul>
      </SettingRow>
    </div>
  </EnvSection>;
}
