"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ArrowRight,
  BookOpen,
  Check,
  CheckCheck,
  ChevronRight,
  CircleHelp,
  FileCode2,
  FileJson2,
  GitCompareArrows,
  Layers3,
  LockKeyhole,
  Plug,
  ScanSearch,
  Search,
  X,
} from "lucide-react";
import Sidebar from "./sidebar";
import WorkspaceFooter from "./workspace-footer";
import ModuleProgress from "./module-progress";
import AgentContracts from "./agent-contracts";
import { capabilities } from "../lib/capabilities";
import { modules, ModuleKey } from "../lib/modules";

const stages = [
  { key: "tasks", label: "任务", icon: Layers3 },
  { key: "diagnosis", label: "诊断", icon: ScanSearch },
  { key: "repairs", label: "修复", icon: GitCompareArrows },
  { key: "regression", label: "验证", icon: CheckCheck },
] as const;

export default function ModulePreview({ section }: { section: ModuleKey }) {
  const module = modules[section];
  const [expanded, setExpanded] = useState(false);
  const [filter, setFilter] = useState("");
  const showExample =
    !filter || "lookup 返回类型不一致 本地契约 示例".includes(filter);
  return (
    <div className="shell">
      <a className="skip" href="#main">
        跳至模块内容
      </a>
      <Sidebar />
      <main id="main">
        <header className="topbar">
          <div className="breadcrumb">
            <Layers3 size={16} aria-hidden="true" />
            <span>工作区</span>
            <ChevronRight size={13} aria-hidden="true" />
            <strong>{module.title}</strong>
          </div>
          <span className="preview-status">
            <span />
            {capabilities[section].label}
          </span>
        </header>
        <div className="main-content module-content">
          <section className="intro">
            <div>
              <div className="intro-label">{module.eyebrow}</div>
              <h1>{module.headline}</h1>
              <p>{module.description}</p>
            </div>
          </section>
          <ModuleProgress section={section} />
          {(section === "connections" || section === "diagnosis") && <AgentContracts />}
          <div className="preview-notice">
            <LockKeyhole size={16} aria-hidden="true" />
            <p>
              <strong>完整交互预览</strong>
              <span>
                {module.unlock}。以下内容为合成示例，不代表真实任务或执行结果。
              </span>
            </p>
            <Link href="/workbench">
              使用调用检查 <ArrowRight size={14} aria-hidden="true" />
            </Link>
          </div>
          {section === "connections" ? (
            <div className="connection-layout">
              <section className="module-surface">
                <div className="module-surface-head">
                  <h2>接入方式</h2>
                  <span className="muted-tag">预览</span>
                </div>
                <div className="connector-choice">
                  <span className="connector-icon">
                    <Plug size={26} aria-hidden="true" />
                  </span>
                  <div>
                    <h3>本地 MCP Server</h3>
                    <p>通过 stdio 连接受控进程，读取工具声明。</p>
                  </div>
                  <span className="planned-badge">CLI 已验证</span>
                </div>
                <div className="config-preview">
                  <label htmlFor="connection-name">连接名称（预览）</label>
                  <input
                    id="connection-name"
                    name="connection-name"
                    defaultValue="本地开发工具"
                    autoComplete="off"
                  />
                  <label htmlFor="connection-command">
                    启动程序（预览，不执行）
                  </label>
                  <input
                    id="connection-command"
                    name="connection-command"
                    placeholder="例如 /path/to/python…"
                    spellCheck={false}
                    autoComplete="off"
                  />
                  <label htmlFor="connection-args">参数（预览，不保存）</label>
                  <input
                    id="connection-args"
                    name="connection-args"
                    placeholder="例如 server.py…"
                    spellCheck={false}
                    autoComplete="off"
                  />
                  <button className="primary" onClick={() => setExpanded(true)}>
                    查看连接流程
                  </button>
                </div>
              </section>
              <section className="module-surface connection-explainer">
                <span className="module-round-icon">
                  <FileJson2 size={25} aria-hidden="true" />
                </span>
                <h2>先连接，再观察。</h2>
                <p>
                  协议握手、工具发现、调用与结果关联，会在这里逐步呈现真实状态。
                </p>
                <ol>
                  <li>确认启动程序与权限</li>
                  <li>协商协议并读取工具声明</li>
                  <li>选择工具与调用参数</li>
                  <li>检查返回结果并生成证据</li>
                </ol>
                <span className="planned-note">
                  真实连接需运行状态与 Web 接入完成后开放；当前按钮只展示说明。
                </span>
              </section>
            </div>
          ) : (
            <>
              <div className="module-toolbar">
                <div className="module-tabs">
                  <span className="module-tab active">
                    {section === "memory" ? "项目经验" : "示例记录"}
                  </span>
                  <span className="toolbar-count">1 个合成示例</span>
                </div>
                <label className="module-search">
                  <Search size={15} aria-hidden="true" />
                  <span className="sr-only">筛选示例</span>
                  <input
                    name="filter"
                    placeholder="筛选示例…"
                    value={filter}
                    onChange={(event) => setFilter(event.target.value)}
                    autoComplete="off"
                  />
                </label>
              </div>
              {!showExample ? (
                <div className="module-empty">
                  <Search size={25} aria-hidden="true" />
                  <h2>没有匹配的示例</h2>
                  <p>试试“lookup”，或清空筛选。</p>
                  <button className="download" onClick={() => setFilter("")}>
                    清空筛选
                  </button>
                </div>
              ) : (
                <section className="module-surface example-task">
                  <div className="example-task-header">
                    <span className="example-task-icon">
                      {section === "memory" ? (
                        <BookOpen size={23} aria-hidden="true" />
                      ) : (
                        <FileCode2 size={23} aria-hidden="true" />
                      )}
                    </span>
                    <div>
                      <div className="example-meta">
                        合成示例 <span>工具契约 / lookup</span>
                      </div>
                      <h2>
                        {section === "memory"
                          ? "返回字段应保持约定的数据类型"
                          : "返回结果与工具声明不一致"}
                      </h2>
                    </div>
                    <button
                      className="download"
                      onClick={() => setExpanded(!expanded)}
                      aria-expanded={expanded}
                    >
                      {module.action}
                      <ChevronRight size={14} aria-hidden="true" />
                    </button>
                  </div>
                  {section === "repairs" ? (
                    <Diff />
                  ) : section === "regression" ? (
                    <Regression />
                  ) : section === "memory" ? (
                    <Memory />
                  ) : (
                    <div className="task-stages">
                      {stages.map(({ key, label, icon: Icon }, i) => (
                        <Link
                          href={`/workspace/${key}`}
                          key={key}
                          className={section === key ? "current" : ""}
                        >
                          <span className="stage-node">
                            <Icon size={18} aria-hidden="true" />
                          </span>
                          <div>
                            <strong>{label}</strong>
                            <small>
                              {
                                [
                                  "关联单次调用证据",
                                  "验证问题与假设",
                                  "审阅隔离候选补丁",
                                  "核对冻结验收集",
                                ][i]
                              }
                            </small>
                          </div>
                          {i < 3 && (
                            <ChevronRight
                              className="stage-arrow"
                              size={16}
                              aria-hidden="true"
                            />
                          )}
                        </Link>
                      ))}
                    </div>
                  )}
                  {section === "diagnosis" && (
                    <div className="diagnosis-columns">
                      <div>
                        <span className="example-status">示例中的已知问题</span>
                        <h3>count 的观察值为字符串</h3>
                        <p>示例契约要求 integer；需要核对序列化或包装层。</p>
                      </div>
                      <div>
                        <span className="example-status hypothesis">
                          示例中的待验证假设
                        </span>
                        <h3>返回前发生了字符串转换</h3>
                        <p>需要执行记录验证，不能仅凭类型差异确认根因。</p>
                      </div>
                    </div>
                  )}
                  <div className="example-task-footer">
                    <span>
                      <FingerprintIcon />
                      证据、候选与验收保持关联
                    </span>
                    <span>预览不会调用模型或修改代码</span>
                  </div>
                </section>
              )}
            </>
          )}
          {expanded && (
            <section className="preview-detail" aria-label="示例详情">
              <div className="module-surface-head">
                <h2>
                  {section === "connections" ? "连接前的确认流程" : "示例详情"}
                </h2>
                <button
                  className="close-preview"
                  aria-label="关闭示例详情"
                  onClick={() => setExpanded(false)}
                >
                  <X size={17} aria-hidden="true" />
                </button>
              </div>
              {section === "repairs" ? (
                <p>
                  此补丁是手写演示。未来修复 Agent
                  只能编辑隔离副本中的白名单文件，无法修改固定测试与验收标准。
                </p>
              ) : section === "regression" ? (
                <p>
                  此表为界面预览。真实验收将分别执行原始基线与候选版本，记录相同测试集的结果；新增回归将阻断候选通过。
                </p>
              ) : section === "memory" ? (
                <p>
                  未来经验条目将记录确认人、来源、适用版本及失效条件。未经验证的假设不会自动变成项目事实。
                </p>
              ) : section === "connections" ? (
                <p>
                  先核对允许启动的程序、argv
                  和环境变量，再读取声明。此处输入仅用于界面体验，未启动进程、未保存配置。
                </p>
              ) : (
                <>
                  <p>
                    观察到返回值与声明类型不一致，先通过确定性检查固定证据，再验证可能的原因。
                  </p>
                  <Link className="text-link" href="/workbench">
                    用真实检查器验证这份合成证据{" "}
                    <ArrowRight size={14} aria-hidden="true" />
                  </Link>
                </>
              )}
            </section>
          )}
          <section className="module-next">
            <CircleHelp size={18} aria-hidden="true" />
            <div>
              <h2>功能会怎样解锁？</h2>
              <p>
                真实 MCP CLI、受控执行与运行记录已接通。下一步接入诊断与候选修复，再逐项完善回归对比和项目记忆。当前可使用网页调用检查和任务记录。
              </p>
            </div>
            <Link href="/#capabilities">
              查看产品路线 <ArrowRight size={14} aria-hidden="true" />
            </Link>
          </section>
          <WorkspaceFooter />
        </div>
      </main>
    </div>
  );
}
function FingerprintIcon() {
  return <FileJson2 size={13} aria-hidden="true" />;
}
function Diff() {
  return (
    <div className="diff-preview">
      <div className="diff-filename">
        <FileCode2 size={15} aria-hidden="true" />
        tools/lookup.py <span>手写补丁预览</span>
      </div>
      <div className="diff-columns">
        <div>
          <h3>修改前</h3>
          <pre>
            <code>
              {"def lookup():\n    return {\n"}
              <span className="line-removed">
                {'-       "count": str(count)'}
              </span>
              {"\n    }"}
            </code>
          </pre>
        </div>
        <div>
          <h3>候选修改</h3>
          <pre>
            <code>
              {"def lookup():\n    return {\n"}
              <span className="line-added">{'+       "count": count'}</span>
              {"\n    }"}
            </code>
          </pre>
        </div>
      </div>
    </div>
  );
}
function Regression() {
  return (
    <div className="regression-table-wrap">
      <table className="regression-table">
        <caption className="sr-only">
          合成示例的回归对照，非真实执行结果
        </caption>
        <thead>
          <tr>
            <th>固定验收项</th>
            <th>示例基线</th>
            <th>示例候选</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>返回类型符合声明</td>
            <td>
              <span className="check-state failed">不符合</span>
            </td>
            <td>
              <span className="check-state passed">通过</span>
            </td>
          </tr>
          <tr>
            <td>必填字段完整</td>
            <td>通过</td>
            <td>通过</td>
          </tr>
          <tr>
            <td>错误返回保持一致</td>
            <td>通过</td>
            <td>通过</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
function Memory() {
  return (
    <div className="memory-content">
      <blockquote>
        工具返回的结构化字段必须保持声明类型。展示层的字符串格式化应留在展示层。
      </blockquote>
      <dl>
        <div>
          <dt>示例来源</dt>
          <dd>返回类型不一致 / 合成任务</dd>
        </div>
        <div>
          <dt>适用范围</dt>
          <dd>lookup 工具的结构化输出</dd>
        </div>
        <div>
          <dt>确认状态</dt>
          <dd>演示条目，未写入项目记忆</dd>
        </div>
      </dl>
    </div>
  );
}
