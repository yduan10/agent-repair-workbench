import Link from "next/link";
import { ArrowLeft, ArrowUpRight, Check, ChevronDown, Clock3 } from "lucide-react";
import ThemeControl from "../../components/theme-control";
import { milestones } from "../../lib/milestones";

export default function UpdatesPage() {
  return <div className="updates-page">
    <a className="skip" href="#updates-main">跳至开发记录</a>
    <header className="updates-nav">
      <Link href="/" className="text-link"><ArrowLeft size={16} aria-hidden="true" />产品首页</Link>
      <ThemeControl />
      <Link href="/workbench" className="nav-cta">进入产品<ArrowUpRight size={15} aria-hidden="true" /></Link>
    </header>
    <main id="updates-main" className="updates-main">
      <div className="updates-heading">
        <span className="updates-kicker">Agent 修复台 / Changelog</span>
        <h1>开发记录</h1>
        <p>按开发顺序记录功能新增、问题修复和验收结果。展开每条记录，查看本批改动及当时的实现范围。</p>
      </div>
      <div className="history-note"><Clock3 size={16} aria-hidden="true" /><p>按迭代顺序从新到旧排列。P0 / UI / DOC 是开发任务编号，这些编号不是正式发布版本。<Link href="/docs">查看项目文档与测试说明 →</Link></p></div>
      <div className="milestone-list">
        {milestones.map((entry, index) => <details id={entry.id} className={`milestone ${entry.active ? "milestone-active" : ""}`} key={entry.id} open={index === 0}>
          <summary>
            <span className="milestone-marker" aria-hidden="true">{entry.status === "已完成" ? <Check size={17} /> : <Clock3 size={17} />}</span>
            <span className="milestone-meta"><time dateTime={entry.date}>{entry.date}</time><span>{entry.id}</span></span>
            <span className="milestone-heading"><span className="milestone-status">{entry.status}</span><strong>{entry.title}</strong><span className="milestone-summary">{entry.summary}</span></span>
            <ChevronDown className="milestone-chevron" size={19} aria-hidden="true" />
          </summary>
          <div className="milestone-body"><ul>{entry.changes.map(change => <li key={change}>{change}</li>)}</ul><p>{entry.boundary}</p></div>
        </details>)}
      </div>
      <div className="updates-next"><div><h2>下一项：接通模型协作循环</h2><p>P0-05b：模型网关、受控工具处理、有限循环与分析结果存储。实际补丁及独立回归属于 P0-06。</p></div><Link href="/workspace/connections" className="text-link">查看工具接入进度<ArrowUpRight size={16} aria-hidden="true" /></Link></div>
    </main>
  </div>;
}
