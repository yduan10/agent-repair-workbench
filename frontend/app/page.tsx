import Link from "next/link";
import SiteFooter, { SiteHeader } from "../components/project-resources";
import { PathTrail } from "../components/ui/path-trail";
import { StatusBadge } from "../components/ui/status";
import { CopyButton } from "../components/ui/copy-id";
import { ToastProvider } from "../components/ui/toast";
import { repositoryUrl } from "../lib/project";
import { REPAIR_COMMAND } from "../lib/repairs";
import { documentationUrl } from "../lib/documentation";

/* The hero demo replays one real check from examples/failing.json.
 * Markup is the final state; landing.css builds up to it once on load
 * (only under prefers-reduced-motion: no-preference). */

const checks = [
  { keys: ["tool.input_schema", "call.arguments"], what: "调用参数是否符合参数契约", codes: ["input_schema_violation"] },
  { keys: ["tool.output_schema", "result.structured_content"], what: "返回值是否符合返回契约", codes: ["output_schema_violation", "structured_content_missing"] },
  { keys: ["call.tool_name", "result.call_id"], what: "工具名称和调用 ID 是否对得上", codes: ["tool_name_mismatch", "result_call_mismatch"] },
  { keys: ["result"], what: "是否收到结果，工具是否报错", codes: ["result_missing", "tool_error"] },
];

const scenarios = [
  { name: "正常调用", what: "工具正常返回结果。", tone: "pass", outcome: "调用成功" },
  { name: "工具错误", what: <>工具返回 <code translate="no">isError: true</code>，调用本身完成。</>, tone: "fail", outcome: "调用失败" },
  { name: "超时", what: "工具开始执行，时限内没有返回。", tone: "unknown", outcome: "结果未知" },
  { name: "响应丢失", what: "工具执行了，响应没有送回客户端。", tone: "unknown", outcome: "结果未知" },
] as const;

const containerPolicy = [
  { flag: "--network none", text: "断网" },
  { flag: "--read-only", text: "只读文件系统" },
  { flag: "--user 65532", text: "非 root 用户" },
  { flag: "--cpus 0.5 --memory 128m", text: "CPU 与内存上限" },
  { flag: "--pids-limit 32", text: "进程数上限" },
];

const roles = [
  { name: "诊断", reads: "调用证据、契约和授权源码，可以申请重新检查或复现。", output: "带证据引用的假设；证据不足时明确保留为假设。" },
  { name: "修复建议", reads: "诊断结论和授权范围内的源码。", output: "局部修改建议，不会自动应用到代码。" },
  { name: "验证", reads: "诊断引用的证据和修复建议的元数据。", output: "证据已核对，或指出还缺哪些证据。" },
];

const budget = [
  { value: "12", unit: "次", label: "模型调用" },
  { value: "20", unit: "次", label: "工具调用" },
  { value: "2,000,000", unit: "", label: "token 总量" },
  { value: "600", unit: "秒", label: "分析时长" },
];

const commands = [
  { title: "获取源码", command: `git clone ${repositoryUrl}.git\ncd agent-repair-workbench` },
  { title: "安装依赖", command: "uv sync --frozen" },
  { title: "检查内置示例", command: "uv run --frozen agent-workbench check examples/failing.json" },
];

export default function Home() {
  return <ToastProvider>
    <div className="site">
      <SiteHeader current="home" />
      <main id="main" className="lp">
        <section className="lp-hero" aria-labelledby="hero-title">
          <div className="lp-wrap lp-hero-copy">
            <h1 id="hero-title">找出 Agent 工具调用中不符合契约的字段</h1>
            <p className="lp-hero-lede">Agent 修复台是在你电脑上运行的工作台，面向用 Python 开发 Agent 和 MCP 工具的开发者。它按工具的 JSON Schema 契约检查一次调用的参数和返回值，给出不符合项所在的 JSON Pointer。内置故障场景还可以在离线容器里复现，再交给模型角色分析。</p>
            <div className="lp-hero-side">
              <div className="lp-hero-actions">
                <Link href="/workspace" className="btn btn-primary btn-lg">打开工作台</Link>
                <a href="#start" className="btn btn-lg">安装与启动</a>
              </div>
              <p className="lp-hero-note">目前只支持内置示例和内置场景，还不能接入你自己的工具。</p>
            </div>
          </div>

          <div className="lp-wrap">
            <figure className="lp-demo" aria-labelledby="demo-caption">
              <div className="lp-demo-panes">
                <div className="lp-demo-pane">
                  <div className="lp-demo-head"><span>返回契约</span><code translate="no">tool.output_schema</code></div>
                  <pre className="lp-code" translate="no" aria-label="返回契约 JSON">
                    <span className="ln">{"{"}</span>
                    <span className="ln">{"  "}<span className="k">&quot;type&quot;</span>: <span className="s">&quot;object&quot;</span>,</span>
                    <span className="ln">{"  "}<span className="k">&quot;properties&quot;</span>: {"{"}</span>
                    <span className="ln lp-step-schema">{"    "}<span className="k">&quot;count&quot;</span>: {"{ "}<span className="k">&quot;type&quot;</span>: <span className="s lp-expect">&quot;integer&quot;</span>{" }"}</span>
                    <span className="ln">{"  "}{"},"}</span>
                    <span className="ln">{"  "}<span className="k">&quot;required&quot;</span>: [<span className="s">&quot;count&quot;</span>]</span>
                    <span className="ln">{"}"}</span>
                  </pre>
                </div>
                <div className="lp-demo-pane">
                  <div className="lp-demo-head"><span>调用证据</span><span className="badge" data-variant="outline">内置示例</span></div>
                  <pre className="lp-code" translate="no" aria-label="调用证据中的 result 部分">
                    <span className="ln lp-step-1"><span className="k">&quot;result&quot;</span>: {"{"}</span>
                    <span className="ln">{"  "}<span className="k">&quot;call_id&quot;</span>: <span className="s">&quot;c1&quot;</span>,</span>
                    <span className="ln">{"  "}<span className="k">&quot;is_error&quot;</span>: <span className="s">false</span>,</span>
                    <span className="ln lp-step-2">{"  "}<span className="k">&quot;structured_content&quot;</span>: {"{"}</span>
                    <span className="ln lp-step-3">{"    "}<span className="k">&quot;count&quot;</span>: <span className="lp-actual">&quot;2&quot;</span></span>
                    <span className="ln">{"  "}{"}"}</span>
                    <span className="ln">{"}"}</span>
                  </pre>
                </div>
              </div>
              <div className="lp-verdict">
                <div className="lp-verdict-path">
                  <span className="lp-verdict-label">不符合项</span>
                  <PathTrail pointer="/result/structured_content/count" label="字段路径" />
                </div>
                <dl className="lp-verdict-meta">
                  <div><dt>结论</dt><dd><StatusBadge tone="fail">不通过</StatusBadge></dd></div>
                  <div><dt>规则代码</dt><dd><code translate="no">output_schema_violation</code></dd></div>
                  <div><dt>契约路径</dt><dd><code translate="no">/properties/count/type</code></dd></div>
                </dl>
              </div>
              <figcaption id="demo-caption">内置示例：<code translate="no">lookup</code> 工具的返回契约要求 <code translate="no">count</code> 是整数，这次调用返回了字符串 <code translate="no">&quot;2&quot;</code>。</figcaption>
            </figure>
          </div>
        </section>

        <section className="lp-section" aria-labelledby="check-title">
          <div className="lp-wrap lp-split">
            <header className="lp-section-head">
              <h2 id="check-title">调用检查</h2>
              <p>把工具契约、调用参数和返回结果放进同一份 JSON，这份 JSON 叫作调用证据。检查器逐项核对，在本机离线完成，不调用模型。</p>
              <Link href="/workbench" className="link">打开调用检查</Link>
            </header>
            <div>
              <div className="lp-table-scroll" role="region" aria-label="检查项" tabIndex={0}>
                <table className="lp-table lp-checks">
                  <thead><tr><th scope="col">调用证据中的位置</th><th scope="col">核对内容</th><th scope="col">不符合时的规则代码</th></tr></thead>
                  <tbody>
                    {checks.map(row => <tr key={row.what}>
                      <td><span className="lp-keys">{row.keys.map(key => <code key={key} translate="no">{key}</code>)}</span></td>
                      <td className="lp-check-what">{row.what}</td>
                      <td><span className="lp-keys">{row.codes.map(code => <code key={code} translate="no">{code}</code>)}</span></td>
                    </tr>)}
                  </tbody>
                </table>
              </div>
              <dl className="lp-verdicts">
                <div><dt><StatusBadge tone="pass">通过</StatusBadge></dt><dd>每个检查项都符合契约。</dd></div>
                <div><dt><StatusBadge tone="fail">不通过</StatusBadge></dt><dd>至少一项不符合；报告列出字段路径、契约路径和规则代码。</dd></div>
                <div><dt><StatusBadge tone="unknown">无法判定</StatusBadge></dt><dd>缺少结果、数字可能失真或契约用了不支持的关键字；不算通过。</dd></div>
              </dl>
            </div>
          </div>
        </section>

        <section className="lp-section" aria-labelledby="repro-title">
          <div className="lp-wrap">
            <header className="lp-section-head lp-section-head-wide">
              <h2 id="repro-title">复现</h2>
              <p>四个内置场景各自在一个新的 Docker 容器里发起一次真实的 MCP 调用，记录容器里实际发生了什么。每次运行最长 30 秒，结束后删除容器，并在报告中写明是否已清理。</p>
            </header>
            <div className="lp-repro">
              <div className="lp-table-scroll" role="region" aria-label="内置场景与记录的结果" tabIndex={0}>
                <table className="lp-table lp-scenarios">
                  <thead><tr><th scope="col">场景</th><th scope="col">容器里发生了什么</th><th scope="col">记录的结果</th></tr></thead>
                  <tbody>
                    {scenarios.map(row => <tr key={row.name}>
                      <th scope="row">{row.name}</th>
                      <td>{row.what}</td>
                      <td><StatusBadge tone={row.tone}>{row.outcome}</StatusBadge></td>
                    </tr>)}
                  </tbody>
                </table>
              </div>
              <aside className="lp-unknown" aria-labelledby="unknown-title">
                <h3 id="unknown-title">为什么记为「结果未知」</h3>
                <p>调用已经发出、却没有收到可靠的结果时，工具可能已经执行过，也可能产生了副作用。工作台把这种情况记为 <code translate="no">outcome_unknown</code>：不自动重试，不算成功，也不算失败。停止容器也不能说明工具没有执行。</p>
              </aside>
              <div className="lp-policy">
                <h3>容器限制</h3>
                <ul>
                  {containerPolicy.map(item => <li key={item.flag}><code translate="no">{item.flag}</code><span>{item.text}</span></li>)}
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section className="lp-section" aria-labelledby="analysis-title">
          <div className="lp-wrap">
            <header className="lp-section-head lp-section-head-wide">
              <h2 id="analysis-title">分析</h2>
              <p>诊断、修复建议、验证三个模型角色依次分析一个内置案例。每个角色只能使用授权给它的工具，结论要引用具体证据；最终状态和检查结果由程序判定，模型不能自行宣布。需要配置你自己的模型接口（DeepSeek 兼容）。</p>
            </header>
            <ol className="lp-roles">
              {roles.map(role => <li key={role.name}>
                <h3>{role.name}</h3>
                <dl>
                  <dt>读取</dt><dd>{role.reads}</dd>
                  <dt>输出</dt><dd>{role.output}</dd>
                </dl>
              </li>)}
            </ol>
            <div className="lp-budget">
              <div className="lp-budget-copy">
                <h3>每次分析的默认预算</h3>
                <p>预算记录在本机数据库里。每次调用模型前先占用额度；模型没有返回用量时按上限计入，显示为「用量待确认」。中断的分析不会自动续跑。CLI 可以收紧这些上限。</p>
              </div>
              <dl className="lp-budget-figures">
                {budget.map(item => <div key={item.label}><dt>{item.label}</dt><dd><span className="tabular">{item.value}</span>{item.unit && <small>{item.unit}</small>}</dd></div>)}
              </dl>
            </div>
          </div>
        </section>

        <section className="lp-section" aria-labelledby="repair-title">
          <div className="lp-wrap lp-split lp-split-reverse">
            <header className="lp-section-head">
              <h2 id="repair-title">修复</h2>
              <p>修复建议应用到代码的隔离副本后，成为候选。基线和候选在同一组冻结的检查项下逐项对比，候选要消除原错误、同时不破坏正常路径，才算通过。</p>
              <p>网页可直接开始和停止修复，也可以在终端使用 CLI。支持返回类型错误、计数值偏移两个内置案例；候选留在隔离副本，不会写回你的代码。</p>
              <div className="lp-command">
                <code translate="no">{REPAIR_COMMAND}</code>
                <CopyButton value={REPAIR_COMMAND} label="修复命令" className="btn btn-ghost btn-sm btn-icon" />
              </div>
            </header>
            <figure className="lp-regression" aria-labelledby="regression-caption">
              <div className="lp-regression-head">
                <span>回归结果</span>
                <span className="badge" data-variant="outline">内置示例 <code translate="no">output_mismatch</code></span>
              </div>
              <table className="lp-table">
                <thead><tr><th scope="col">检查项</th><th scope="col">基线</th><th scope="col">候选</th></tr></thead>
                <tbody>
                  <tr><th scope="row">原错误<span>count 返回字符串</span></th><td><StatusBadge tone="fail">不通过</StatusBadge></td><td><StatusBadge tone="pass">通过</StatusBadge></td></tr>
                  <tr><th scope="row">正常路径<span>多次调用、边界输入和非法输入</span></th><td><StatusBadge tone="pass">通过</StatusBadge></td><td><StatusBadge tone="pass">通过</StatusBadge></td></tr>
                </tbody>
              </table>
              <figcaption id="regression-caption">四个结果各在一个新的断网容器里得出。检查项的版本变化后，旧结果自动隐藏。</figcaption>
            </figure>
          </div>
        </section>

        <section className="lp-section lp-local" aria-labelledby="local-title">
          <div className="lp-wrap lp-split">
            <header className="lp-section-head">
              <h2 id="local-title">数据留在本机</h2>
              <p>工作台面向在自己电脑上调试的单个开发者，不是托管服务。</p>
            </header>
            <dl className="lp-facts">
              <div><dt>运行位置</dt><dd>本机服务、网页和复现容器都运行在你的电脑上，本机服务默认只监听 127.0.0.1。</dd></div>
              <div><dt>调用证据</dt><dd>只发给本机服务检查，不保存原文。报告只包含规则代码、字段路径和摘要，不复制参数和返回值。</dd></div>
              <div><dt>模型</dt><dd>只有发起分析时，角色读取的证据、契约和授权源码片段才会发送到你配置的模型接口。不配置模型，检查和复现照常可用。</dd></div>
              <div><dt>记录</dt><dd>运行、分析和修复记录保存在本机的 SQLite 数据库中。</dd></div>
            </dl>
          </div>
        </section>

        <section className="lp-section" id="start" aria-labelledby="start-title">
          <div className="lp-wrap lp-split">
            <header className="lp-section-head">
              <h2 id="start-title">开始使用</h2>
              <p>需要 macOS 或 Linux、Python 3.12 和 <code translate="no">uv</code>。第一次安装依赖需要联网；之后检查离线运行，不需要模型密钥、Node 或 Docker。</p>
              <p>启动网页、配置模型和准备 Docker 镜像，见<Link className="link" href={documentationUrl("27-local-development-guide")}>本地运行指南</Link>。</p>
            </header>
            <div>
              <ol className="lp-steps">
                {commands.map(step => <li key={step.title}>
                  <h3>{step.title}</h3>
                  <div className="lp-command">
                    <pre translate="no"><code>{step.command}</code></pre>
                    <CopyButton value={step.command} label={`「${step.title}」命令`} className="btn btn-ghost btn-sm btn-icon" />
                  </div>
                </li>)}
              </ol>
              <div className="lp-output">
                <p>命令以退出码 <code translate="no">1</code> 结束，表示发现了不符合项。输出的关键部分：</p>
                <pre translate="no" tabIndex={0} aria-label="检查命令的输出示例"><code>{`{
  "status": "failed",
  "checks": { "input": "passed", "output": "failed" },
  "findings": [{
    "code": "output_schema_violation",
    "instance_path": "/result/structured_content/count",
    "schema_path": "/properties/count/type"
  }]
}`}</code></pre>
              </div>
            </div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  </ToastProvider>;
}
