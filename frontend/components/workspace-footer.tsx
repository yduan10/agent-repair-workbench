"use client";

import Link from "next/link";
import { repositoryUrl } from "../lib/project";

export default function WorkspaceFooter({ beforeNavigate }: { beforeNavigate?: () => boolean }) {
  const guard = (event: { preventDefault: () => void }) => {
    if (beforeNavigate && !beforeNavigate()) event.preventDefault();
  };
  return (
    <section className="page-footer workspace-footer" aria-label="产品信息">
      <span>Agent 修复台</span>
      <nav aria-label="产品信息链接">
        <Link href="/" onNavigate={guard}>产品介绍</Link>
        <Link href="/docs" onNavigate={guard}>项目文档</Link>
        <Link href="/updates" onNavigate={guard}>开发记录</Link>
        <a href={repositoryUrl} target="_blank" rel="noopener noreferrer">GitHub 源码 ↗</a>
      </nav>
    </section>
  );
}
