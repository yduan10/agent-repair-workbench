import type { Metadata } from "next";
import SiteFooter, { SiteHeader } from "../../components/project-resources";
import { changelog } from "../../lib/milestones";
import { formatDate } from "../../lib/format";

export const metadata: Metadata = {
  title: "更新记录",
  description: "Agent 修复台每次更新带来的变化，按日期倒序排列。",
};

const weekday = new Intl.DateTimeFormat("zh-CN", { weekday: "long" });

export default function UpdatesPage() {
  return <div className="site">
    <SiteHeader current="updates" />
    <main id="main" className="cl">
      <header className="cl-head">
        <h1>更新记录</h1>
        <p>每次更新带来的变化，新的在前。</p>
      </header>
      {changelog.map(day => {
        const noon = `${day.date}T12:00:00`;
        return <section key={day.date} id={day.date} className="cl-day" aria-labelledby={`${day.date}-title`}>
          <h2 id={`${day.date}-title`}>
            <a href={`#${day.date}`}><time dateTime={day.date}>{formatDate(noon)}</time></a>
            <span>{weekday.format(new Date(noon))}</span>
          </h2>
          <div className="cl-entries">
            {day.entries.map(entry => <article key={entry.slug} id={`${day.date}-${entry.slug}`} className="cl-entry">
              <h3>{entry.title}</h3>
              <ul>{entry.changes.map(change => <li key={change}>{change}</li>)}</ul>
              {entry.limit && <p className="cl-limit"><strong>限制：</strong>{entry.limit}</p>}
            </article>)}
          </div>
        </section>;
      })}
    </main>
    <SiteFooter />
  </div>;
}
