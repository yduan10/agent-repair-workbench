import type { Metadata } from "next";
import { isValidElement, type ReactNode } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import SiteFooter, { DocsNav, SiteHeader } from "../../../components/project-resources";
import DocumentDiagram from "../../../components/document-diagram";
import { documentationEntries, documentationGroupOf, documentationUrl } from "../../../lib/documentation";
import { documentLink, documentSections, projectDocuments } from "../../../lib/docs.server";
import { sourceDocument } from "../../../lib/project";

type Props = { params: Promise<{ slug: string[] }> };
export const dynamicParams = false;
export function generateStaticParams() { return projectDocuments().map(doc => ({ slug: doc.slug.split("/") })); }
export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const doc = projectDocuments().find(item => item.slug === slug.join("/"));
  return { title: doc ? `${doc.title} · 文档` : "未找到文档" };
}

export default async function DocumentPage({ params }: Props) {
  const { slug } = await params;
  const doc = projectDocuments().find(item => item.slug === slug.join("/"));
  if (!doc) notFound();
  const sections = documentSections(doc.content);
  const body = doc.content.replace(/^#\s+.+$/m, "");
  const headingId = (line?: number) => sections.find(section => section.line === line)?.id;
  const group = documentationGroupOf(doc.slug);
  const current = documentationEntries.findIndex(entry => entry.slug === doc.slug);
  const next = current >= 0 ? documentationEntries[current + 1] : undefined;
  const toc = (label: string) => <nav aria-label={label}>
    {sections.map(section => <a className={section.depth === 3 ? "doc-toc-child" : undefined} href={`#${section.id}`} key={section.id}>{section.title}</a>)}
  </nav>;
  return <div className="site">
    <SiteHeader current="docs" />
    <div className="doc-layout">
      <aside className="doc-sidebar"><DocsNav current={doc.slug} /></aside>
      <main id="main" className="doc-main">
        <nav className="doc-breadcrumb" aria-label="当前位置">
          <Link href="/docs">文档</Link><span aria-hidden="true">/</span><Link href={`/docs#${group.id}`}>{group.title}</Link>
        </nav>
        <h1 className="doc-title">{doc.title}</h1>
        {group.id === "records" && <p className="doc-record-note">工程记录：内容停留在写作当时，当前功能以<Link className="link" href="/updates">更新记录</Link>为准。</p>}
        <div className="doc-mobile">
          <details className="doc-mobile-nav"><summary>文档目录</summary><DocsNav current={doc.slug} label="文档目录（移动版）" /></details>
          {sections.length > 0 && <details className="doc-mobile-toc"><summary>本页章节</summary>{toc("本页章节（移动版）")}</details>}
        </div>
        <article className="doc-prose">
          <Markdown remarkPlugins={[remarkGfm]} skipHtml components={{
            h1: ({ children }) => <h2>{children}</h2>,
            h2: ({ children, node }) => <h2 id={headingId(node?.position?.start.line)}>{children}</h2>,
            h3: ({ children, node }) => <h3 id={headingId(node?.position?.start.line)}>{children}</h3>,
            a: ({ children, href }) => {
              const destination = documentLink(href ?? "", doc.source);
              if (!destination) return <span>{children}</span>;
              return destination.startsWith("http") ? <a href={destination} target="_blank" rel="noopener noreferrer">{children}<span className="sr-only">（外部链接，新标签页）</span></a> : <Link href={destination}>{children}</Link>;
            },
            pre: ({ children }) => isValidElement<{ className?: string; children?: ReactNode }>(children) && children.props.className === "language-mermaid"
              ? <DocumentDiagram source={String(children.props.children ?? "")} />
              : <pre tabIndex={0} role="region" aria-label="代码示例，可横向滚动" translate="no">{children}</pre>,
            table: ({ children }) => <div className="doc-table" tabIndex={0} role="region" aria-label="文档表格，可横向滚动"><table>{children}</table></div>,
            img: ({ alt }) => <span>{alt}</span>,
          }}>{body}</Markdown>
        </article>
        <footer className="doc-foot">
          {next && <Link href={documentationUrl(next.slug)} className="doc-next"><span>下一篇</span><strong>{next.title}</strong></Link>}
          <a className="doc-source" href={sourceDocument(doc.source)} target="_blank" rel="noopener noreferrer">在 GitHub 上查看原文<span className="sr-only">（新标签页）</span></a>
        </footer>
      </main>
      {sections.length > 0 && <aside className="doc-toc"><p className="doc-toc-label" aria-hidden="true">本页章节</p>{toc("本页章节")}</aside>}
    </div>
    <SiteFooter />
  </div>;
}
