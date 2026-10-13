import type { Metadata } from "next";
import { isValidElement, type ReactNode } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArrowLeft, ArrowUpRight, BookOpen } from "lucide-react";
import ThemeControl from "../../../components/theme-control";
import DocumentDiagram from "../../../components/document-diagram";
import { documentationEntries, documentationUrl } from "../../../lib/documentation";
import { documentLink, documentSections, projectDocuments } from "../../../lib/docs.server";
import { repositoryUrl } from "../../../lib/project";

type Props = { params: Promise<{ slug: string[] }> };
export const dynamicParams = false;
export function generateStaticParams() { return projectDocuments().map(doc => ({ slug: doc.slug.split("/") })); }
export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const doc = projectDocuments().find(item => item.slug === slug.join("/"));
  return { title: doc ? `${doc.title} · Agent 修复台文档` : "未找到文档" };
}

export default async function DocumentPage({ params }: Props) {
  const { slug } = await params;
  const doc = projectDocuments().find(item => item.slug === slug.join("/"));
  if (!doc) notFound();
  const sections = documentSections(doc.content);
  const body = doc.content.replace(/^#\s+.+$/m, "");
  const headingId = (line?: number) => sections.find(section => section.line === line)?.id;
  const current = documentationEntries.findIndex(entry => entry.slug === doc.slug);
  const next = current >= 0 ? documentationEntries[current + 1] : undefined;
  return <div className="document-page">
    <a className="skip" href="#document-main">跳至文档正文</a>
    <header className="document-header"><Link href="/" className="text-link"><ArrowLeft size={16} aria-hidden="true" />Agent 修复台</Link><Link href="/docs" className="document-header-label"><BookOpen size={17} aria-hidden="true" />项目文档</Link><ThemeControl /><Link href="/workbench" className="nav-cta">打开调用检查<ArrowUpRight size={15} aria-hidden="true" /></Link></header>
    <div className="document-layout">
      <aside className="document-sidebar"><nav aria-label="工程文档导航"><Link href="/docs">文档首页</Link>{documentationEntries.map(entry => <Link key={entry.slug} href={documentationUrl(entry.slug)} aria-current={entry.slug === doc.slug ? "page" : undefined}>{entry.title}</Link>)}</nav><div className="document-source"><span>开发中的项目</span><p>实现状态以迭代计划为准，历史评审保留当时的范围。</p><a href={repositoryUrl} target="_blank" rel="noopener noreferrer">GitHub 源码 ↗</a></div></aside>
      <main id="document-main" className="document-content">
        <div className="document-breadcrumb"><Link href="/docs">项目文档</Link><span aria-hidden="true">/</span><span>{doc.source.startsWith("docs/reviews/") ? "独立评审" : "工程参考"}</span></div>
        <h1>{doc.title}</h1>
        <details className="document-mobile-toc"><summary>本页章节</summary><nav aria-label="本页章节（移动版）">{sections.map(section => <a key={section.id} href={`#${section.id}`}>{section.title}</a>)}</nav></details>
        <article className="markdown-document">
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
              : <pre tabIndex={0} role="region" aria-label="代码示例，可横向滚动">{children}</pre>,
            table: ({ children }) => <div className="markdown-table" tabIndex={0} role="region" aria-label="文档表格，可横向滚动"><table>{children}</table></div>,
            img: ({ alt }) => <span>{alt}</span>,
          }}>{body}</Markdown>
        </article>
        {next && <Link href={documentationUrl(next.slug)} className="document-next"><span>继续阅读</span><strong>{next.title}<ArrowUpRight size={18} aria-hidden="true" /></strong></Link>}
      </main>
      <aside className="document-toc"><span>本页章节</span><nav aria-label="本页章节">{sections.map(section => <a className={section.depth === 3 ? "toc-child" : undefined} href={`#${section.id}`} key={section.id}>{section.title}</a>)}</nav></aside>
    </div>
    <footer className="product-footer"><Link href="/docs">文档首页</Link><Link href="/updates">开发记录</Link><a href={repositoryUrl} target="_blank" rel="noopener noreferrer">GitHub 源码 ↗</a></footer>
  </div>;
}
