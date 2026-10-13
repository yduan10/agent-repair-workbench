import { capabilities } from "../lib/capabilities";
import Link from "next/link";
import ThemeControl from "../components/theme-control";
import ProjectResources from "../components/project-resources";
import {
  ArrowRight,
  ArrowUpRight,
  Braces,
  Check,
  CheckCheck,
  ChevronRight,
  Code2,
  FileJson2,
  Fingerprint,
  GitCompareArrows,
  Layers3,
  ShieldCheck,
} from "lucide-react";

export default function ProductHome() {
  return (
    <div className="product-page">
      <a className="skip" href="#product-main">
        跳至产品介绍
      </a>
      <header className="product-nav">
        <Link className="brand" href="/" aria-label="Agent 修复台首页">
          <span className="brand-mark" aria-hidden="true">
            <Braces size={25} />
            <Check size={10} />
          </span>
          <span>Agent<span className="brand-second">修复台</span></span>
        </Link>
        <nav aria-label="产品导航">
          <a href="#start">功能入口</a>
          <a href="#capabilities">开发进度</a>
          <Link href="/docs">项目文档</Link>
          <Link href="/updates">开发记录</Link>
        </nav>
        <ThemeControl />
        <Link href="/workbench" className="nav-cta">
          打开调用检查 <ArrowUpRight size={15} aria-hidden="true" />
        </Link>
      </header>
      <main id="product-main">
        <section className="product-hero">
          <div className="hero-copy">
            <span className="preview-label">
              <span />
              Agent / MCP 开发者工具 · 本地运行
            </span>
            <h1>
              <span className="hero-line"><span>定位工具调用失败，</span></span>
              <span className="hero-line"><span>核验每一次修复。</span></span>
            </h1>
            <p>
              Agent 修复台面向 Python Agent 与 MCP 工具开发者。导入调用记录，检查参数和返回结果，定位不符合工具声明的字段；后续由诊断、修复、验证角色协作，提出并核验局部补丁。
            </p>
            <div className="hero-actions">
              <Link className="hero-primary" href="/workbench">
                体验调用检查 <ArrowRight size={17} aria-hidden="true" />
              </Link>
              <Link className="hero-secondary" href="/workbench?source=custom">
                导入我的证据 <UploadIcon />
              </Link>
            </div>
            <div className="hero-footnote">
              <ShieldCheck size={14} aria-hidden="true" />
              <span>现在可用：调用检查、运行记录、接口目录。模型修复开发中。</span>
            </div>
          </div>
          <div
            className="product-scene"
            aria-label="合成案例：返回结果与工具声明不一致"
          >
            <div className="scene-topline">
              <span className="scene-case">
                <span />
                案例预览
              </span>
              <span>合成数据</span>
            </div>
            <div className="case-window">
              <div className="case-window-bar">
                <div className="window-dots" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </div>
                <span>lookup / 一次工具调用</span>
                <FileJson2 size={15} aria-hidden="true" />
              </div>
              <div className="case-code">
                <div className="case-code-label">
                  <span>工具声明</span>
                  <span>output_schema</span>
                </div>
                <code>
                  <span className="code-dim">{"{"}</span>
                  <br />
                  &nbsp; <span className="code-key">
                    &quot;count&quot;
                  </span>: {"{"}
                  <br />
                  &nbsp;&nbsp;&nbsp;{" "}
                  <span className="code-key">&quot;type&quot;</span>:{" "}
                  <span className="code-value">&quot;integer&quot;</span>
                  <br />
                  &nbsp; {"}"}
                  <br />
                  <span className="code-dim">{"}"}</span>
                </code>
                <div className="case-code-divider" />
                <div className="case-code-label">
                  <span>实际记录</span>
                  <span>structured_content</span>
                </div>
                <code>
                  {"{"} <span className="code-key">&quot;count&quot;</span>:{" "}
                  <span className="code-error">&quot;2&quot;</span> {"}"}
                  <span className="inline-issue">应为整数，记录为字符串</span>
                </code>
              </div>
              <div className="case-bottom">
                <span>
                  <Fingerprint size={13} aria-hidden="true" />
                  按证据定位
                </span>
                <span>不凭猜测通过</span>
              </div>
            </div>
            <div className="evidence-float">
              <span className="evidence-float-icon">
                <GitCompareArrows size={20} aria-hidden="true" />
              </span>
              <div>
                <strong>差异，可以落到具体位置。</strong>
                <code>/result/structured_content/count</code>
              </div>
              <CheckCheck size={17} aria-hidden="true" />
            </div>
            <div className="scene-caption">
              <span className="caption-rule" />
              声明、观察、依据，始终关联在一起
            </div>
          </div>
        </section>

        <section id="start" className="start-section" aria-labelledby="start-heading">
          <div className="start-heading"><span className="section-note">从这里开始</span><h2 id="start-heading">按你要做的事，直接进入。</h2><p>首次使用先打开调用检查，内置示例无需配置模型。</p></div>
          <div className="start-grid">
            <Link href="/workbench" className="start-card"><Braces aria-hidden="true" /><span className="start-badge">网页可用</span><h3>检查一次失败调用</h3><p>选择示例或导入 JSON，查看不符合项、字段路径并下载报告。</p><span className="start-action">打开调用检查 <ArrowUpRight size={16} aria-hidden="true" /></span></Link>
            <Link href="/workspace/tasks" className="start-card"><Layers3 aria-hidden="true" /><span className="start-badge">受控复现</span><h3>运行一次工具复现</h3><p>选择四种固定故障场景，在本机执行并核验报告；也可查看已有 CLI 记录。</p><span className="start-action">打开任务总览 <ArrowUpRight size={16} aria-hidden="true" /></span></Link>
            <Link href="/workspace/connections" className="start-card"><Code2 aria-hidden="true" /><span className="start-badge">目录可用 · 自定义接入待开发</span><h3>了解工具与 Agent 接口</h3><p>查看三种角色的权限和 JSON Schema，按文档使用受控 MCP CLI。</p><span className="start-action">打开工具接入 <ArrowUpRight size={16} aria-hidden="true" /></span></Link>
          </div>
        </section>

        <section id="how-it-works" className="product-section">
          <div className="section-intro">
            <div>
              <span className="section-note">从证据开始</span>
              <h2>
                一次调用，怎样检查？
              </h2>
            </div>
            <p>
              调试 Agent
              时，工具声明、调用参数与返回结果常常散在不同位置。把一次调用放在一起，先确认哪一步没有满足约定。
            </p>
          </div>
          <div className="journey-grid">
            <article>
              <span className="journey-step">01</span>
              <FileJson2 size={26} aria-hidden="true" />
              <h3>放入一次调用</h3>
              <p>
                导入 JSON
                证据，保留原始参数、返回结果和工具声明。也可以先用合成案例体验。
              </p>
              <Link href="/workbench?source=custom">
                导入证据 <ChevronRight size={14} aria-hidden="true" />
              </Link>
            </article>
            <article>
              <span className="journey-step">02</span>
              <Layers3 size={26} aria-hidden="true" />
              <h3>核对，而后判断</h3>
              <p>
                检查字段类型、必填项与关联关系。规则不支持或信息缺失时，明确说明无法判断。
              </p>
              <Link href="/workbench">
                运行一次检查 <ChevronRight size={14} aria-hidden="true" />
              </Link>
            </article>
            <article>
              <span className="journey-step">03</span>
              <GitCompareArrows size={26} aria-hidden="true" />
              <h3>带着依据继续修复</h3>
              <p>
                按问题路径定位，下载含检查范围与证据指纹的报告，留作后续修改的对照。
              </p>
              <a href="#trust">
                了解验证方式 <ChevronRight size={14} aria-hidden="true" />
              </a>
            </article>
          </div>
        </section>

        <section id="capabilities" className="capability-section">
          <div className="capability-copy">
            <span className="section-note">一条完整的产品路线</span>
            <h2>
              从检查工具调用，
              <br />
              走向有验收的 Agent 修复。
            </h2>
            <p>
              诊断、修复、验证各自承担明确职责。我们先建立可依赖的检查依据，再让
              Agent 在权限与预算内推进任务。
            </p>
            <Link href="/workbench" className="hero-primary">
              使用当前版本 <ArrowRight size={16} aria-hidden="true" />
            </Link>
          </div>
          <ol className="capability-list">
            <li className="available">
              <span className="capability-number">
                <Check size={16} aria-hidden="true" />
              </span>
              <div>
                <h3>
                  证据导入与契约检查 <b>{capabilities.checks.label}</b>
                </h3>
                <p>参数、返回结果、关联关系与可下载报告</p>
              </div>
            </li>
            <li>
              <span className="capability-number">2</span>
              <div>
                <h3>
                  真实 MCP 与受控执行 <b>{capabilities.connections.label}</b>
                </h3>
                <p>握手、真实调用、容器隔离与故障回收已验收；任务页可运行固定场景</p>
              </div>
            </li>
            <li>
              <span className="capability-number">3</span>
              <div>
                <h3>
                  运行记录 <b>{capabilities.tasks.label}</b>
                </h3>
                <p>固定场景网页发起、请求停止与校验报告；不接受任意命令</p>
                <Link href="/workspace/tasks" className="text-link">查看运行记录</Link>
              </div>
            </li>
            <li>
              <span className="capability-number">4</span>
              <div>
                <h3>
                  诊断与局部修复 <b>{capabilities.diagnosis.label}</b>
                </h3>
                <p>分角色协作，限定权限、上下文与执行预算</p>
              </div>
            </li>
            <li>
              <span className="capability-number">5</span>
              <div>
                <h3>
                  独立回归与项目记忆 <b>{capabilities.regression.label}</b>
                </h3>
                <p>冻结验收规则，只沉淀经确认的项目经验</p>
              </div>
            </li>
          </ol>
        </section>

        <section id="trust" className="product-section trust-section">
          <div>
            <span className="section-note">信任来自可验证的细节</span>
            <h2>
              通过、失败、无法判定。
              <br />
              每一种状态都有明确含义。
            </h2>
          </div>
          <div className="trust-details">
            <p>
              <strong>原始证据直接检查</strong>
              <span>
                保留重复键和数字原貌；不会先让浏览器转换数据，再假装它来自原始调用。
              </span>
            </p>
            <p>
              <strong>失败不会被包装成成功</strong>
              <span>
                测试覆盖格式错误、缺失结果、精度丢失和服务异常；网页结果与 CLI
                对照。
              </span>
            </p>
            <p>
              <strong>控制数据去向</strong>
              <span>
                证据仅发送至本机服务，不保存原始记录。报告由你主动下载，分享前可核对字段路径。
              </span>
            </p>
          </div>
        </section>
        <ProjectResources />
        <section className="closing-cta">
          <div>
            <h2>先从你手上的那次调用开始。</h2>
            <p>几步查看结果，让后续调试有据可依。</p>
          </div>
          <Link className="hero-primary" href="/workbench?source=custom">
            打开调用检查 <ArrowRight size={17} aria-hidden="true" />
          </Link>
        </section>
      </main>
      <footer className="product-footer">
        <span>
          Agent 修复台 <small>开发中</small>
        </span>
        <span>本地优先，有据可查。</span>
        <Link href="/docs">项目文档</Link>
        <Link href="/updates">开发记录</Link>
        <a href="#product-main">回到顶部 ↑</a>
      </footer>
    </div>
  );
}

function UploadIcon() {
  return <ArrowUpRight size={16} aria-hidden="true" />;
}
