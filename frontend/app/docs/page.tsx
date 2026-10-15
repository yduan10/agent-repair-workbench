import type { Metadata } from "next";
import Link from "next/link";
import SiteFooter, { DocsNav, SiteHeader } from "../../components/project-resources";
import { PathTrail } from "../../components/ui/path-trail";
import { repositoryUrl } from "../../lib/project";
import { documentationGroups, documentationUrl } from "../../lib/documentation";

export const metadata: Metadata = {
  title: "文档",
  description: "Agent 修复台的安装、启动和各功能用法，以及开发过程中的工程记录。",
};

export default function DocsPage() {
  return <div className="site">
    <SiteHeader current="docs" />
    <div className="doc-layout doc-layout-index">
      <aside className="doc-sidebar"><DocsNav /></aside>
      <main id="main" className="doc-main">
        <header className="doc-index-head">
          <h1>文档</h1>
          <p>安装、启动和每个功能的用法。开发过程中的规格、交付和评审记录集中放在最后的「工程记录」里。</p>
        </header>
        <details className="doc-mobile-nav">
          <summary>文档目录</summary>
          <DocsNav label="文档目录（移动版）" />
        </details>

        <section id="quickstart" className="doc-index-section" aria-labelledby="quickstart-title">
          <h2 id="quickstart-title">第一次检查</h2>
          <p className="doc-index-lead">网页已经启动时，按下面三步用内置示例走一遍调用检查。还没有启动，先看<Link className="link" href={documentationUrl("27-local-development-guide")}>本地运行指南</Link>。</p>
          <ol className="doc-steps">
            <li>
              <h3>打开调用检查</h3>
              <p>选择「结果类型不符」示例，或者导入你自己的调用证据。这一步不需要模型密钥。</p>
              <Link className="link" href="/workbench">打开调用检查</Link>
            </li>
            <li>
              <h3>运行检查</h3>
              <p>示例的返回契约要求 <code translate="no">count</code> 是整数，返回的却是字符串。预期结论为「不通过」，字段路径是：</p>
              <PathTrail pointer="/result/structured_content/count" label="字段路径" />
            </li>
            <li>
              <h3>对照另外两个示例</h3>
              <p>「正常调用」应为「通过」；「缺失结果」应为「无法判定」，规则代码 <code translate="no">result_missing</code>。下载的报告只包含规则代码、字段路径和摘要。</p>
            </li>
          </ol>
        </section>

        {documentationGroups.map(group => <section key={group.id} id={group.id} className="doc-index-section" data-group={group.id} aria-labelledby={`${group.id}-title`}>
          <h2 id={`${group.id}-title`}>{group.title}</h2>
          <p className="doc-index-lead">{group.description}</p>
          <ul className="doc-index-list">
            {group.entries.map(entry => <li key={entry.slug}>
              <Link href={documentationUrl(entry.slug)}>{entry.title}</Link>
              <p>{entry.summary}</p>
            </li>)}
          </ul>
        </section>)}

        <p className="doc-source-note">文档和代码在同一个仓库中维护，也可以在 <a className="link" href={repositoryUrl} target="_blank" rel="noopener noreferrer">GitHub<span className="sr-only">（新标签页）</span></a> 上阅读原文。</p>
      </main>
    </div>
    <SiteFooter />
  </div>;
}
