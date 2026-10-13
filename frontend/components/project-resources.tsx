import Link from "next/link";
import { ArrowUpRight, BookOpen, Code2 } from "lucide-react";
import { repositoryUrl } from "../lib/project";

export default function ProjectResources() {
  return <section className="project-resources" aria-label="文档与源码">
    <Link href="/docs" className="resource-card">
      <BookOpen size={25} aria-hidden="true" />
      <div><h2>项目文档</h2><p>从本地启动到 Agent 测试，查看架构、工具边界和迭代计划。</p><span>阅读文档 <ArrowUpRight size={16} aria-hidden="true" /></span></div>
    </Link>
    <a href={repositoryUrl} target="_blank" rel="noopener noreferrer" className="resource-card">
      <Code2 size={25} aria-hidden="true" />
      <div><h2>GitHub 源码</h2><p>浏览代码、测试用例和独立评审记录，克隆项目在本机运行。</p><span>访问源码仓库（新标签页）<ArrowUpRight size={16} aria-hidden="true" /></span></div>
    </a>
  </section>;
}
