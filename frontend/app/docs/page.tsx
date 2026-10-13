import Link from "next/link";
import { ArrowLeft, ArrowUpRight, BookOpen } from "lucide-react";
import ThemeControl from "../../components/theme-control";
import { repositoryUrl } from "../../lib/project";
import { documentationEntries, documentationUrl } from "../../lib/documentation";



export default function DocsPage() {
  return <div className="docs-page">
    <a className="skip" href="#docs-main">跳至项目文档</a>
    <header className="updates-nav">
      <Link href="/" className="text-link"><ArrowLeft size={16} aria-hidden="true" />产品首页</Link>
      <ThemeControl />
      <Link href="/workbench" className="nav-cta">打开调用检查<ArrowUpRight size={15} aria-hidden="true" /></Link>
    </header>
    <main id="docs-main" className="docs-main">
      <div className="docs-heading"><span className="section-note">Agent 修复台 / Documentation</span><h1>项目文档</h1><p>为 Python Agent 与 MCP 工具开发者提供调用检查、受控复现和修复验收。先从一个失败调用开始。</p></div>
      <nav className="docs-toc" aria-label="文档章节"><a href="#quickstart">快速上手</a><a href="#agent-testing">怎么测试 Agent</a><a href="#engineering-docs">工程文档</a><a href={repositoryUrl} target="_blank" rel="noopener noreferrer">GitHub 源码 ↗</a></nav>
      <section id="quickstart" className="docs-section">
        <h2>第一次使用：三步查看检查结果</h2>
        <ol className="docs-steps">
          <li><strong>打开调用检查</strong><p>选择「结果类型不符」示例，或导入符合格式的调用 JSON。此操作无需模型密钥。</p><Link href="/workbench" className="text-link">进入调用检查 →</Link></li>
          <li><strong>点击「运行检查」</strong><p>示例的 count 声明为整数，记录却是字符串。预期看到「发现不符合项」及字段路径，而不是模型生成的解释。</p></li>
          <li><strong>对照正常与缺失结果</strong><p>正常调用应通过；缺失结果应报告 result_missing。下载报告核对范围与证据指纹。</p></li>
        </ol>
        <p className="docs-note">任务总览可运行四种审核过的合成场景，查询真实状态、请求停止并核验报告；需先准备本机数据库、Docker 与固定镜像。已有 CLI 记录同样可查，首次启动可能为空。工具接入页提供接口目录，自定义执行和模型修复尚未接通。</p>
      </section>
      <section id="agent-testing" className="docs-section">
        <h2>Agent 怎么测，当前测到了哪一步？</h2>
        <p>分开报告确定性程序测试和真实模型表现。一次模型接口连通，不等于完成诊断或修复验收。</p>
        <div className="docs-table-scroll" tabIndex={0} role="region" aria-label="Agent 测试层级，可横向滚动"><table className="docs-table"><thead><tr><th>层级</th><th>输入与判定</th><th>当前状态</th></tr></thead><tbody>
          <tr><td>角色契约与权限</td><td>构造非法 JSON、越权工具、伪造结论、预算越界；宿主必须拒绝。</td><td>已实现并测试</td></tr>
          <tr><td>诊断 Agent</td><td>固定故障、源码和可读取证据；核对引用与复现，缺证据保留假设。</td><td>P0-05b 待接通</td></tr>
          <tr><td>修复 Agent</td><td>仅改白名单文件；原始失败用例恢复，修改隐藏验收立即拒绝。</td><td>P0-06 待实现</td></tr>
          <tr><td>验证 Agent 与验收器</td><td>独立比较基线/候选，修好新用例却破坏旧行为必须失败。</td><td>P0-06 待实现</td></tr>
          <tr><td>模型对照实验</td><td>相同模型、工具、案例和总预算，多次运行单 Agent / 多角色，分报修复率、回归率、成本。</td><td>尚未开展</td></tr>
        </tbody></table></div>
        <h3>现在可执行的测试</h3><p>在项目根目录运行；第一组不需要模型或 Docker，只验证已经实现的契约、权限与状态规则。</p>
        <pre className="docs-code" tabIndex={0} role="region" aria-label="测试命令，可横向滚动"><code>{`uv sync --frozen
uv run --frozen pytest src/agent_workbench/agents tests/agents tests/tools

# 全部不依赖容器和公开案例准备的回归
uv run --frozen pytest -m 'not docker and not public_case'

# 构建后执行浏览器验收（包括真实本机 API）
cd frontend
npm ci
npm run build
npx playwright install chromium
npm run test:e2e`}</code></pre>
        <p className="docs-note">容器和公开历史故障须先按 README 审核、准备，之后使用 AWB_DOCKER_TESTS=1 / AWB_PUBLIC_CASE=1 显式执行。跳过项不计通过。</p>
        <Link className="text-link" href="/docs/17-agent-tools-testing-plan">查看逐项验收用例与预期结果 <ArrowUpRight size={16} aria-hidden="true" /></Link>
      </section>
      <section id="engineering-docs" className="docs-section"><h2>工程文档</h2><p>在本站阅读完整文档；文档与代码一起维护，支持章节导航和浅深色主题。</p><div className="docs-links">{documentationEntries.map(({title, slug, summary}) => <Link key={slug} href={documentationUrl(slug)}><BookOpen size={20} aria-hidden="true" /><div><h3>{title}</h3><p>{summary}</p></div><ArrowUpRight size={16} aria-hidden="true" /></Link>)}</div></section>
    </main>
    <footer className="product-footer"><span>Agent 修复台</span><Link href="/updates">开发记录</Link><a href={repositoryUrl} target="_blank" rel="noopener noreferrer">GitHub 源码 ↗</a></footer>
  </div>;
}
