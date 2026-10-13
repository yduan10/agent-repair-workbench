"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import ThemeControl from "./theme-control";
import { capabilities, CapabilityKey } from "../lib/capabilities";
import {
  BookOpen,
  Braces,
  Check,
  CheckCheck,
  FolderOpen,
  GitCompareArrows,
  Layers3,
  Plug,
  ScanSearch,
} from "lucide-react";

const navigation: { href: string; label: string; icon: typeof Layers3; capability: CapabilityKey }[] = [
  { capability: "tasks", href: "/workspace/tasks", label: "任务总览", icon: Layers3 },
  { capability: "checks", href: "/workbench", label: "调用检查", icon: Braces },
  { capability: "diagnosis", href: "/workspace/diagnosis", label: "诊断分析", icon: ScanSearch },
  { capability: "repairs", href: "/workspace/repairs", label: "候选修复", icon: GitCompareArrows },
  { capability: "regression", href: "/workspace/regression", label: "回归验证", icon: CheckCheck },
  { capability: "memory", href: "/workspace/memory", label: "项目记忆", icon: BookOpen },
  { capability: "connections", href: "/workspace/connections", label: "工具接入", icon: Plug },
];

export default function Sidebar({
  beforeNavigate,
}: {
  beforeNavigate?: () => boolean;
}) {
  const guard = (event: { preventDefault: () => void }) => {
    if (beforeNavigate && !beforeNavigate()) event.preventDefault();
  };
  const pathname = usePathname();
  return (
    <aside className="sidebar product-sidebar">
      <Link
        onNavigate={guard}
        className="brand"
        href="/"
        aria-label="Agent 修复台产品首页"
      >
        <span className="brand-mark" aria-hidden="true">
          <Braces size={25} />
          <Check size={10} />
        </span>
        <span>
          Agent<span className="brand-second">修复台</span>
        </span>
      </Link>
      <div className="sidebar-appearance"><ThemeControl /></div>
      <div className="workspace-switch">
        <span className="workspace-icon">
          <FolderOpen size={17} aria-hidden="true" />
        </span>
        <div>
          本地工作区<small>个人开发环境</small>
        </div>
        <span className="local-dot" />
      </div>
      <nav aria-label="产品模块">
        {navigation.map(({ href, label, icon: Icon, capability }) => (
          <Link
            onNavigate={guard}
            className={`nav-link ${pathname === href ? "active" : ""}`}
            href={href}
            key={href}
            aria-current={pathname === href ? "page" : undefined}
          >
            <Icon size={17} aria-hidden="true" />
            {label}
            <span className={`nav-capability ${capabilities[capability].tone}`}>
              {capabilities[capability].label}
            </span>
          </Link>
        ))}
      </nav>

    </aside>
  );
}
