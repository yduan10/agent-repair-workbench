import Link from "next/link";
import ThemeSwitch from "./ui/theme-switch";
import { repositoryUrl } from "../lib/project";
import { documentationGroups, documentationUrl } from "../lib/documentation";

/** Header and footer for the public pages (/, /docs, /updates). Workspace pages use the app shell instead. */

type Section = "home" | "docs" | "updates";

function Brand() {
  return <Link href="/" className="site-brand" aria-label="Agent 修复台首页">
    <span className="brand-glyph" aria-hidden="true">{"{}"}</span>
    <span>Agent 修复台</span>
  </Link>;
}

export function SiteHeader({ current, mainId = "main" }: { current: Section; mainId?: string }) {
  return <>
    <a className="skip" href={`#${mainId}`}>跳到主要内容</a>
    <header className="site-header">
      <div className="site-header-inner">
        <Brand />
        <nav className="site-nav" aria-label="网站导航">
          <Link href="/docs" aria-current={current === "docs" ? "page" : undefined}>文档</Link>
          <Link href="/updates" aria-current={current === "updates" ? "page" : undefined}>更新记录</Link>
          <a href={repositoryUrl} target="_blank" rel="noopener noreferrer">GitHub<span className="sr-only">（新标签页）</span></a>
        </nav>
        <div className="site-header-actions">
          <ThemeSwitch />
          <Link href="/workspace" className="btn btn-primary">打开工作台</Link>
        </div>
      </div>
    </header>
  </>;
}

export default function SiteFooter() {
  return <footer className="site-footer">
    <div className="site-footer-inner">
      <div className="site-footer-brand">
        <Brand />
        <p>本地运行的 Agent 工具调用检查与复现工作台。</p>
      </div>
      <nav className="site-footer-nav" aria-label="页脚导航">
        <div>
          <h2>产品</h2>
          <ul>
            <li><Link href="/workspace">工作台总览</Link></li>
            <li><Link href="/workbench">调用检查</Link></li>
            <li><Link href="/workspace/tasks">复现</Link></li>
          </ul>
        </div>
        <div>
          <h2>资料</h2>
          <ul>
            <li><Link href="/docs">文档</Link></li>
            <li><Link href="/updates">更新记录</Link></li>
            <li><a href={repositoryUrl} target="_blank" rel="noopener noreferrer">GitHub<span className="sr-only">（新标签页）</span></a></li>
          </ul>
        </div>
      </nav>
      <p className="site-footer-legal">源码公开，未附开源许可证。第三方依赖遵循各自的许可证。</p>
    </div>
  </footer>;
}

/** Grouped documentation index used by the /docs sidebar and its mobile disclosure. */
export function DocsNav({ current, label = "文档目录" }: { current?: string; label?: string }) {
  return <nav className="doc-nav" aria-label={label}>
    <Link href="/docs" className="doc-nav-home" aria-current={current === undefined ? "page" : undefined}>文档首页</Link>
    {documentationGroups.map(group => <div key={group.id} className="doc-nav-group" data-group={group.id}>
      <h2>{group.title}</h2>
      <ul>
        {group.entries.map(entry => <li key={entry.slug}>
          <Link href={documentationUrl(entry.slug)} aria-current={entry.slug === current ? "page" : undefined}>{entry.title}</Link>
        </li>)}
      </ul>
    </div>)}
  </nav>;
}
