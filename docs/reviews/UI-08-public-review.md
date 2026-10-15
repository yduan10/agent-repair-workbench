# UI-08 公开页面独立评审（public）

2026-10-15。评审者：独立 reviewer（未参与实现），只读，除本报告外未修改任何项目文件。范围：落地页、更新记录、站内文档阅读器及其数据源与测试。结论：**有条件通过**，无 Defect P0/P1；2 项 Defect P2 需在 UI-08 标 done 前处理或登记跟踪，6 项 Defect P3。

## 依据与范围

- 规格 [32](../32-ui-08-product-redesign.md)、`AGENTS.md`、[04](../04-quality-gates.md) 缺陷分级；事实核对依据 `README.md`、[03](../03-roadmap.md)、`src/agent_workbench/` 实际代码与 CLI 实际输出。
- 文件：`frontend/app/page.tsx`、`app/updates/page.tsx`、`app/docs/page.tsx`、`app/docs/[...slug]/page.tsx`、`lib/milestones.ts`、`lib/project.ts`、`lib/documentation.ts`、`lib/docs.server.ts`、`components/project-resources.tsx`、`components/document-diagram.tsx`、`app/styles/landing.css`、`app/styles/docs.css`，测试 `document-reader.spec.ts`、`reviewer-document-reader.spec.ts`、`guidance.spec.ts`。对照基线 `git diff HEAD`。
- 环境：已运行的生产前端 3010 与 API 8030；未启动、构建或停止任何服务；未向 API 发写请求（测试中的 `POST /api/check` 为无状态本机检查）。

## 执行的验证

| 项目 | 结果 |
|---|---|
| `PLAYWRIGHT_CHANNEL=chrome npx playwright test` 三个范围内 spec | 18 项通过。首轮 `guidance.spec.ts` light 空状态 1 项因 `/api/check` 返回 429 `checker_busy`（其他评审并发）失败，单独重跑 4/4 通过，见 D8 |
| 自写脚本 `scratchpad/public-check.mjs`：`/`、`/updates`、`/docs`、3 篇文档 × 浅/深 × 1440/390 × reduce/no-preference | 全部 200、无横向溢出；axe WCAG2A/AA/2.1AA 零违规（best-practice 仅 `landmark-unique`，见 D7） |
| 首屏演示动效 | `reduce` 下 `document.getAnimations()` 为空，静态即最终状态；`no-preference` 加载时 12 个动画（lp-walk/land/actual/seg/leaf/rise），2.8 秒后全部结束且停在终态。全部 `backwards` 填充，无布局位移 |
| 跨文档链接 | 遍历 99 篇文档，14 个带片段的站内链接目标 id 全部存在；外链均 `target=_blank rel=noopener noreferrer` 并有读屏提示 |
| 锚点与粘性页头 | `/#start`、`/updates#日期-条目`、`/docs#reference`、文档章节在 1440/390 下标题均落在页头下方 |
| CLI 实测 | `check examples/failing.json` 输出与落地页片段一致、退出 1；`repair --help`、`analyze --help` 与预算默认值逐项核对；`repair --case output_mismatch --mode three_role` 实测失败，见 D1 |

## 缺陷

### D1 — Defect P2：落地页可复制的修复命令在当前代码中无法运行

- 位置：`frontend/app/page.tsx:213-214`。
- 问题：命令为 `uv run --frozen agent-workbench repair --case output_mismatch --mode three_role`。当前 `src/agent_workbench/repair_runtime/cli.py:27-34` 的 `repair` 子命令没有 `--case` 参数，案例在第 67-68 行固定为 `output_mismatch`。
- 复现：在仓库根目录执行该命令，立即输出 `invalid_arguments`，退出码 2（参数解析阶段即失败，无副作用）。用户点复制按钮后粘贴运行必然失败。
- 旁证：前端自身的 `frontend/lib/repairs.ts:435-436` `REPAIR_COMMAND` 为不带 `--case` 的正确写法，两处不一致。`--case`/`counter_offset` 入口的评审记录（`reviews/P0-06-case-entry-review.md`）指向 `agent-sandboxes/p006-heldout` 冻结副本，尚未集成进本仓库。
- 修复建议：落地页改为复用 `REPAIR_COMMAND`（单一来源），或待 `--case` 入口真正合入后再改。补一条测试：从前端导出的所有 CLI 命令字符串逐个跑 `--help` 级参数解析（或 `argparse` 单测），防止文案先于代码。

### D2 — Defect P2：「使用指南」分组中的两篇文档内容与当前产品不符

- 位置：分组定义 `frontend/lib/documentation.ts:12-15`；内容在 `README.md`（`/docs/getting-started`）与 `docs/27-local-development-guide.md`（不在本次文件范围，但由本范围的分组作为「当前用法」呈现，且落地页 `page.tsx` 「开始使用」和 `/docs` 快速上手都把它作为唯一的运行指南链接）。
- 问题：
  - `docs/27` 第 231-235 行给出 3 条 `repair --case …` 命令（包括本仓库代码中不存在的 `counter_offset`），与 D1 同样无法运行。
  - `docs/27` 第 55 行仍写「候选修复、回归、记忆等页面按模块标明待实现或交互预览」「迭代历史」，第 93、238、272 行使用旧页名「任务总览」「回归验证」。
  - `README.md` 第 58-64 行的页面表仍是旧导航「任务总览 / 诊断分析 / 候选修复 / 回归验证 `/workspace/regression` / 工具接入」。新信息架构中 `/workspace/regression` 已只是重定向。
- 影响：「工程记录」分组有「内容停留在写作当时」的提示，「使用指南」没有，用户会把这些过时页名和失效命令当作当前说明。
- 修复建议：在 UI-08 的文档更新批次里，把 README 页面表与 docs/27 的页名、能力描述改成 UI-08 术语与路由，修复命令与 D1 一并处理；或者在内容更新前把这两篇移出「使用指南」。

### D3 — Defect P3：首屏把复现场景和模型分析写成同一条链路

- 位置：`frontend/app/page.tsx:63`，「内置故障场景还可以在离线容器里复现，再交给模型角色分析」。
- 问题：「复现」的四个场景（正常/工具错误/超时/响应丢失）不能交给分析；分析只接受 `output_mismatch`、`passing` 两个案例（`analyze --case` 的 choices）。[26](../26-p0-06-candidate-verification.md) 第 145 行明确说两者「不能自动视为同一修复链路」。
- 建议：改为分别陈述，例如「内置故障场景可以在离线容器里复现；内置案例可以交给模型角色分析。」

### D4 — Defect P3：落地页「修复」没有说明只支持一个固定案例，且整体完成状态仍在验收

- 位置：`frontend/app/page.tsx` 修复区块（约 205-230 行）；`lib/milestones.ts:55-64`。
- 问题：落地页只写「候选在终端用 CLI 生成；网页只读」。没有说明当前只有固定的 `output_mismatch` 一个案例，而 `--case` 写法（D1）又暗示可以选择案例。台账 P0-06 仍是 `in_progress`。更新记录的限制写「只支持内置案例」，复数含义也偏宽。其余能力边界（网页只读、不写回代码）准确。
- 建议：限制句改为「只支持一个内置案例（返回类型错误）」，落地页同样加一句。

### D5 — Defect P3：容器参数和退出码描述与代码有细小出入

- `page.tsx:31` 标为参数的 `--user 65532`，实际是 `--user 65532:65532`（`runner/docker.py:200-201`）。既然以 `<code>` 形式展示参数，应与实际一致。另外 `--cap-drop ALL`、`--security-opt no-new-privileges` 是实际存在、更强的限制，可酌情补上。
- `milestones.ts:148`「2 表示无法完成检查」：实际 `cli.py` 把 `inconclusive` 映射为 2，包括检查正常完成、结论为「无法判定」的情况（如 `result_missing`）。按术语表应写「2 表示无法判定（含无法完成检查）」。
- `page.tsx:24` 场景名「超时」与工作区 `lib/runs.ts:37` 的「调用超时」不一致。

### D6 — Defect P3：文档页元数据与标题一致性

- `app/docs/[...slug]/page.tsx:19` 只设 title，没有 description，所有文档页都继承根描述。
- `getting-started` 的标题渲染为「Agent 修复台 · 文档 · Agent 修复台」（README 一级标题就是产品名），H1 也是「Agent 修复台」，与导航名「项目介绍与快速上手」不一致。「参考」组同样，例如导航「调用检查规则」打开后 H1 和 `<title>` 为「P0-01：离线工具调用契约检查器」。文档允许出现里程碑编号，但导航名和页面标题对不上，影响定位。
- 建议：`documentationEntries` 中登记的文档用登记的 `title`/`summary` 作为 `<title>` 与 description，正文 H1 保留原文。
- 另：`lib/project.ts:3` 的 `repositoryName` 没有任何引用。

### D7 — Defect P3：landmark 重名（axe best-practice）

- 文档页 `aside.doc-sidebar` 与 `aside.doc-toc` 都是无名 complementary；每个表格、代码块都是同名 region（「文档表格，可横向滚动」「代码示例，可横向滚动」），`/docs/27-local-development-guide` 等页出现 `landmark-unique`。不属于 WCAG A/AA，现有门禁不拦。
- 建议：侧栏 `aside` 加 `aria-label="文档目录"`，目录 `aside` 加 `aria-label="本页章节"`（或去掉外层 aside）。代码块和表格 region 的 label 可以带序号或就近标题。

### D8 — Defect P3：`guidance.spec.ts` 空状态用例依赖真实单并发检查器

- 位置：`frontend/tests/guidance.spec.ts:25-34`。
- 问题：用例直接打真实 `/api/check`。检查器单并发，忙时返回 429，本次首轮因此失败（错误上下文中可见「检查器一次只处理一个请求，当前正忙」）。`workers: 1` 时单独运行稳定，但与其他进程共用 8030 时会偶发失败。
- 建议：这个用例只验证空状态与提交流程，改用 `page.route` 固定返回报告，或在遇到 `checker_busy` 时等待重试。

## 未证实 / 观察项

- 文档页新增的「在 GitHub 上查看原文」按 `blob/main/<path>` 生成。本地 `origin/main` 引用（2026-10-14）只含 docs 20-23，`docs/26`～`32` 及多数评审文件当前未跟踪。如果发布前没有推送，这些链接会在 GitHub 上 404。未联网核实远端，仅作提醒。

## 核对无误的内容

- **示例与判定**：首屏演示与 `examples/failing.json` 逐字段一致（`lookup`、`call_id c1`、`count: "2"`）。`instance_path /result/structured_content/count`、`schema_path /properties/count/type`、`output_schema_violation` 与 CLI 实际输出一致，退出码 1 也一致。检查项表中的 7 个规则代码都存在于 `checker.py`，位置对应正确。「无法判定」的三类原因（缺结果、`unsupported_number`、`unsupported_schema`）与代码一致。
- **复现**：四个场景与 `WebScenario` 一致；超时/响应丢失 → `outcome_unknown` 有 Docker 测试佐证；30 秒上限（`run_sandbox total_timeout ≤ 30`）、断网、只读、CPU 0.5、内存 128m、PID 32、结束清理并报告 `cleanup` 都与代码一致；`outcome_unknown` 不重试、不算成功的表述准确。
- **分析**：12 次模型、20 次工具、2,000,000 token、600 秒与 `orchestration/cli.py`、`WEB_BUDGET` 及 `Budget` 上限一致，「CLI 可以收紧」与 `le=` 约束一致。诊断角色可以「申请重新检查或复现」，与 `ROLE_TOOLS` 一致；修复建议角色只读，与代码一致。
- **修复/回归**：四个独立断网容器、版本失配后不再显示旧结果（`verification=unavailable` 时 `slots` 必须为空）、网页只读、不写回，与代码和 `capabilities.ts` 一致。回归示意标了「内置示例 `output_mismatch`」，首屏证据标了「内置示例」，合成数据都有标注。
- **本机与安装**：Python 3.12（`requires-python`）、macOS/Linux、`uv sync --frozen`、仓库地址与 `git remote` 一致；前端与 API 都绑定 127.0.0.1。
- **更新记录**：不出现里程碑编号、评审或测试数量；日期与旧版里程碑日期一致，星期计算正确（10-15 为星期四）；各条可感知变化与 `reproduction-panel`、`run-report`、`analysis-detail`、`environment` 等实际实现吻合。
- **Markdown 安全**：`skipHtml` 丢弃原始 HTML；图片只渲染 alt 文本；`documentLink` 拒绝 `javascript:`/`data:`/`mailto:` 等非 http(s) 协议、绝对路径、协议相对 `//` 与 `../` 越界路径。非文档的仓库引用转为 GitHub 链接。路由只来自 `generateStaticParams` 且 `dynamicParams=false`，遍历请求返回 404（reviewer spec 覆盖）。
- **Mermaid**：只接受 `flowchart` 并排除指令、front-matter、`click`、`@{`、`<` 与 URL。启用 `securityLevel: "strict"` 和 `htmlLabels: false`（无 `foreignObject`），以 data URI `<img>` 呈现（脚本不执行）。渲染串行，取消/版本号防止乱序覆盖，`MutationObserver` 在卸载时断开。主题色取站点令牌，均为十六进制，与 khroma 兼容。
- **文档分组**：三组顺序、未登记文档归入「工程记录」并显示提示、面包屑、`aria-current`、移动版目录与章节、`scroll-margin` 都正确。全部 106 个路由的目录锚点无缺失、无重复 id。
- **元数据**：`/updates`、`/docs` 有独立 title 与 description，文档页 title 走模板，落地页使用根默认。跳转链接 `#main` 在每个公开页都有目标。

## 统计

Defect P0：0；P1：0；P2：2（D1、D2）；P3：6（D3–D8）。
