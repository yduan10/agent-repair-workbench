# UI-08 分析页（analysis）独立代码评审

2026-10-15。评审者：独立评审代理，未参与 UI-08 实现。范围为分析页的发起面板、执行控制台、分析记录与详情、证据阅读器及对应库、样式与测试。结论：**无 Defect P0/P1**；Defect P2 共 2 项，Defect P3 共 9 项（其中 3 项是 UI-08 之前就有的逻辑，本次文案或交互让问题更明显）。P2 按 `docs/04-quality-gates.md` 登记跟踪，不阻断 UI-08 done。

## 依据与范围

- 规格 `docs/32-ui-08-product-redesign.md`（第 3 节 URL 状态，第 4 节文案、术语表「用量待确认」，第 6 节「后台标签页暂停轮询」「不夸大网页能力」），`AGENTS.md`，`docs/04-quality-gates.md` 缺陷分级。
- 源码：`frontend/components/analysis-history.tsx`、`analysis-console.tsx`、`analysis-detail.tsx`、`analysis-evidence.tsx`、`execution-terminal.tsx`，`frontend/lib/analyses.ts`、`analysis-runs.ts`、`analysis-evidence.ts`，`frontend/app/styles/analysis.css`。为看清 env 轮询器与发起面板的接缝，另读了 `frontend/lib/environment.ts`、`lib/runs.ts`（不在本范围，只作根因引用）和后端 `src/agent_workbench/web_analyses/service.py`、`fencing.py`、`store.py`。
- 基线：`analysis-console.tsx`、`analysis-runs.ts`、`execution-terminal.tsx` 等在 HEAD 中不存在（UI-08 之前未提交）。用 `artifacts/console-review-sha256.json` 的摘要核对后，确认 `<review-workspaces>/p006-ui/frontend/` 中的副本就是 P1-01b 控制台评审签收的版本，以它为基线做 diff。
- 测试：读取并运行 `tests/analyses.spec.ts`、`console-evidence.spec.ts`、`console-review.spec.ts`、`evidence-independent.spec.ts`，同时与基线测试逐行比对。
- 只读评审：除本报告外未修改项目文件；未构建、未启停服务；对真实 API 只发 GET。注意：现有 `analyses.spec.ts` 的截图用例会写 `artifacts/ui08-analysis-*.png`（忽略目录），这是该测试原有行为。

## 运行证据

1. 现有非 live 测试：`PLAYWRIGHT_CHANNEL=chrome npx playwright test tests/analyses.spec.ts tests/console-evidence.spec.ts tests/console-review.spec.ts tests/evidence-independent.spec.ts --trace off`，**40/40 通过**（34.1s）。
2. 独立探针脚本放在 `scratchpad/an-review/`（Chrome，连接已运行的 3010 生产前端，分析接口全部由 `page.route` 模拟）：

| 编号 | 脚本 | 场景 | 结果 |
|---|---|---|---|
| T1 | `stale-catalog.mjs` | env 首次读到 busy → 发起面板自查得到 available → 下一次 env 读取遇到 429 | 发起面板退回「已有分析在运行…查看当前分析」，「开始分析」禁用；之后 8 秒内 0 次自查，服务端一直是 available（**AN-01**） |
| T2 | `contention.mjs`（真实 8030，只用 GET） | 同时发两次 `GET /api/analysis-runs/catalog`，重复 20 次 | 19/20 次其中一个返回 429。两个读取方同时读取时，几乎必然有一个拿到 429 |
| T3 | `pending-404.mjs` | 会话存储里的待确认请求在服务端查不到（原 POST 没到达服务端） | 同时显示「正在查询（不会重新运行）」、终端「正在查询提交结果…」以及详情「记录或报告已不存在，请刷新列表」；点击「查询提交结果」后发出 POST，并按新分析开始执行（**AN-02**）；`?analysis=` 深链被改写（AN-05） |
| T4 | `hidden-and-pending.mjs` | 运行中把标签页设为隐藏 6 秒 | 详情 0 次读取，目录 0 次读取；恢复可见后立即各读一次（符合要求） |
| T5 | 同上 | 运行中切换到另一条已结束记录，原分析随后结束 | 会话存储仍保留待确认请求，「开始分析」和两个下拉框一直禁用，说明栏只显示「只检查契约，不调用模型。」（AN-03） |
| T6 | `bad-pending.mjs` | 会话存储里的待确认值无法解析（例如案例已下线），刷新两次 | 一直提示「浏览器禁用了会话存储」，「开始分析」禁用（AN-04） |
| T7 | `visible-race.mjs` | 模拟服务端锁语义：运行在隐藏期间结束，然后恢复可见 | 8 次中有两次读取拿到 429，最终状态正确。说明可见切换时 env 与发起面板确实会同时读取；T1 的错误状态需要 env 的 429 晚于发起面板最后一次成功读取 |

## 缺陷

### AN-01 — Defect P2：复用 env 轮询器的目录时，env 遇到 429 会用旧值覆盖发起面板的新结果，且发起面板之后不会再自查纠正

- 位置：`frontend/components/analysis-console.tsx:76-80`（`env.checkedAt > catalogAt.current` 时 `setCatalog(env.analysis)`）、`:101-102`（只有初次且 env 已有值时跳过自查）；根因在 `frontend/lib/environment.ts:88-95`：目录读取失败（包括 429）时保留 `previous.analysis`，但 `checkedAt` 仍更新为 `Date.now()`。
- 机制：服务端目录 GET 会短暂占用 `analysis-web-owner.lock`（`web_analyses/service.py:85-120`）。执行槽空闲时，两个读取方同时读取，后到的一方返回 429（T2：19/20）。env 遇到 429 后保留旧 `analysis`，同时把 `checkedAt` 改成当前时间。同步 effect 只比较时间戳，于是把这个旧值当成更新的数据写回 `catalog`。发起面板的本地循环只在 `slot.status !== "available"` 时运行，此时已经停止，effect 的依赖也没有变化，所以不会重新读取。
- 复现（T1，已验证）：env 上一次读到 busy(X)，发起面板随后读到 available。env 下一次读取遇到 429 后，面板显示「已有分析在运行，同一时间只能运行一个。查看当前分析」（链接指向已结束的 X），「开始分析」禁用。8 秒内面板没有任何自查。要等 env 下一次成功读取（15 秒周期）才会恢复，如果 env 持续遇到 429 就一直不恢复。反方向也会出错：运行中的任务可能因为 env 的旧 available 值暂时失去「停止」按钮，因为 `stoppable` 依赖 `catalog.slot.task_id`。
- 影响：显示错误状态，暂时阻止发起新分析。服务端有锁和 429 兜底，不会重复执行，也不会越权写入。属于 UI-08「复用 env 首次结果以避免锁冲突」引入的竞态。
- 建议：同步 effect 只在 `env.analysis` 的**对象引用变化**时采用（env 遇到 429 时引用不变），依赖改为 `[env.analysis]`。或者让 env 单独暴露 `analysisCheckedAt`，只在目录读取成功时更新。env 报告非 available 时，重新启动本地 2 秒轮询（或依赖 env 的 15 秒周期，但要在文案里接受这段滞后）。补一条 E2E：env 429 不得覆盖面板更新的结果。

### AN-02 — Defect P2：「查询提交结果」实际会重新 POST，原请求没到达服务端时会新建并开始分析；同时界面出现三种互相矛盾的状态

- 位置：`frontend/components/analysis-console.tsx:209-211`（按钮「查询提交结果」，说明「用同一个请求 ID 查询，不会新建分析。」）、`:146`（「请点「查询提交结果」，不要重新提交。」）、`:68`（「正在查询（不会重新运行）」）、`:224`（终端标题「正在查询提交结果…」）；404 文案来自 `lib/runs.ts:88`。
- 机制：`submit(pending)` 会用同一个 request_id 再次 `POST /api/analysis-runs`。服务端 `_serve` 先查 `existing`：已存在就返回 reused；**不存在就获取锁、admit 并执行**（`service.py:131-181`）。所以只有原请求已被接收时，「不会新建分析」才成立。如果原 POST 根本没到达服务端（最需要用户判断的情况），点击「查询」就会真正开始一次分析，并消耗模型预算。基线文案是「确认本次提交（不会新建任务）」，至少还能看出这是一次提交；新文案把写操作说成了只读查询。
- 复现（T3，已验证）：待确认请求在服务端为 404。页面同时显示「无法确认上次提交是否已开始，正在查询（不会重新运行）」，但实际只查了一次就停了；终端显示运行色徽标「正在查询提交结果…」，并且一直不变；详情区显示「记录或报告已不存在，请刷新列表。」。点击「查询提交结果」后发出 1 次 POST，并按新分析开始执行（toast「分析已开始。」）。
- 影响：文案夸大了按钮的只读性（AGENTS.md 诚实要求、规格 §4 第 2/5 条）。用户可能在已经不想运行时触发一次模型调用。没有自动重试，去重语义仍由服务端保证，所以不是 P1。
- 建议：按钮改为「用同一 ID 重新提交」或「确认提交（不会重复运行）」，说明写清楚「如果上次没有送达，这次会开始分析；如果已送达，只会找回原分析」。如果需要真正的只读查询，用 `GET /api/analyses/{id}`。404 时把待确认状态改为「服务端没有这次提交的记录」，终端不要显示进行中徽标，详情区不要显示「已不存在，请刷新列表」。参考复现页 UI-08-runs D6，可以提供显式的「放弃这次提交」。

### AN-03 — Defect P3（UI-08 前已有）：待确认请求只在「正在查看该分析」时清除；切换到其他记录后，发起面板一直禁用且不说明原因

- 位置：`analysis-console.tsx:106-116`（只在 `detail.summary.task_id === pending.request_id` 且已结束时清除）、`:188`、`:195/199`（`!!pending` 禁用）。
- 复现（T5，已验证）：开始分析，查看另一条记录，原分析在后台结束。会话存储仍保留请求，「开始分析」和两个下拉框都禁用，原因栏只显示意图提示。重新选中原分析或刷新页面（挂载时会强制选中）后才会恢复。
- 建议：pending 存在且没有选中它时，在原因栏写「上一次提交的分析还没确认结束」并给出「查看」按钮。或者在列表或目录轮询看到该 ID 已结束时清除 pending。

### AN-04 — Defect P3（逻辑已有，文案为新）：会话存储中的待确认值无法解析时，提示「浏览器禁用了会话存储」，发起面板在整个标签页会话期间不可用

- 位置：`analysis-console.tsx:61-71`。解析失败和存储被禁用落在同一个 `catch` 里。
- 复现（T6，已验证）：写入 `case_name: "retired_case"`，刷新两次后仍提示「浏览器禁用了会话存储，网页无法提交分析。请允许本站使用存储后刷新」。刷新不能解决，只能关闭标签页。将来案例枚举变化时就会遇到。
- 建议：区分「存储不可用」和「值无法识别」。后一种情况说明「上次提交的记录无法识别，已忽略」，并在确认存储可写后移除这个值。

### AN-05 — Defect P3：挂载时的恢复逻辑用 pushState 覆盖用户打开的 `?analysis=` 深链

- 位置：`analysis-console.tsx:67` 调用 `selectAnalysis(id)`，默认使用 `pushState`（`analysis-history.tsx:59-66`）。
- 复现（T3，已验证）：带待确认请求打开 `?analysis=<A>`，地址立即变为 `?analysis=<请求 ID>`，浏览器后退才回到 A。从侧栏回到分析页也会多出一条历史记录。
- 建议：恢复时用 `{ replace: true }`；URL 已明确指定其他记录时只显示待确认提示，不切换选择。

### AN-06 — Defect P3：提交被拒绝时的原因文案可能不符合实际

- 位置：`analysis-console.tsx:142-146`。
- 问题 1：全新 POST 返回 429 时一律显示「已有一个分析在运行」。服务端在 `_serve` 获取锁失败时同样会返回 `analysis_busy`/429，而锁也可能只是被 env 或面板的目录 GET 短暂占用（T2 证明两次 GET 同时到达时几乎必有 429）。此时没有任何分析在运行。这里清除 pending 是安全的，因为请求没被 admit，问题只在文案。
- 问题 2：503（例如 `store_unavailable`、`INPUT_BOUND_UNVERIFIED`）进入不确定分支，文案写成「连接中断」，但服务端其实已经回应。
- 建议：429 改为「服务正忙或已有分析在运行，请稍后再试」，并立即刷新目录让原因栏给出准确状态。不确定分支按是否收到 HTTP 状态区分「连接中断」和「服务暂时无法处理（HTTP 503）」。

### AN-07 — Defect P3（逻辑已有）：`recovery_required` 时目录每 2 秒轮询一次，没有上限，并经常与 env 读取冲突

- 位置：`analysis-console.tsx:91`（`slot.status !== "available"` 都按 2 秒轮询）。
- 问题：`recovery_required` 需要用户在终端运行 reconcile，可能持续很久。页面可见期间每 2 秒都会获取一次服务端锁，和 env 的 15 秒读取碰撞后，会弹出红色 `role="alert"`「服务正忙，1 秒后重试…」（`:95`、`:181`），也正好触发 AN-01 的条件。隐藏时会暂停（T4），所以不是无界资源问题。
- 建议：只在 `busy` 时用 2 秒轮询；`recovery_required` 交给 env 的 15 秒周期或使用指数退避。429 重试期间的提示不要用 alert 和失败色。

### AN-08 — Defect P3：运行期间每次摘要版本变化都会重新读取证据，打开的证据阅读器每约 2 秒闪回骨架屏

- 位置：`analysis-evidence.tsx:32-49`（依赖 `detail.sha256`，每次先 `setItems([])`、`setLoading(true)`）。
- 问题（已核对代码路径）：运行中每次轮询都会产生新的 sha256，即使 `evidence_refs` 没变，也会重新 `GET /evidence`，而该接口要做服务端核验。阅读器内容被替换，焦点如果在 `<pre>` 代码块里会丢到 `body`。关联性校验没有问题。
- 建议：改用 `evidence_refs` 的 ID+哈希序列作为键；引用没变时保留已校验的条目，不再重新读取。重新读取时保留旧内容，不清空。

### AN-09 — Defect P3：状态播报有缺口

- `analysis-console.tsx:208` 的 `role="status"` 提示只在有内容时才插入 DOM。新插入的 live region 在多种读屏器上不会播报，基线里这是常驻节点。比如 429 拒绝提交时，读屏用户可能听不到原因。
- `execution-terminal.tsx:32-37` 中，分析结束、停止成功都只改变徽标，没有任何播报；只有开始时有 toast。
- 建议：提示节点常驻、内容按需变化；终端标题的状态徽标放进常驻的 `aria-live="polite"` 容器。

### AN-10 — Defect P3：术语与小屏信息

- 同一意图有两种叫法：下拉框和原因栏使用目录标签「仅检查契约」（`web_analyses/catalog.py`、`lib/analysis-runs.ts:47`），记录行、终端标题、详情徽标使用「检查契约」（`lib/analyses.ts:15`）。check_only 运行中时，记录行显示「检查契约」，旁边的阶段徽标也是「检查契约」（`phaseLabels.checking`）。这不符合规格 §4「一个概念一个词」。
- `analysis.css:845-856`：≤640px 时隐藏终端的 `.term-source` 和事件日志的 `.an-log-role`，手机上看不出事件来自哪个角色。
- 建议：统一意图标签（以目录为准或前端统一）；小屏把角色放到消息前缀，不要直接隐藏。

### AN-11 — Defect P3：维护项

- `analysis-detail.tsx:16-19` 导出的 `AnalysisCommand` 已无引用（`grep` 只命中定义处），属于死代码。
- 发起和停止成功后都没有调用 `requestEnvironmentRefresh()`，复现面板和运行列表都会调用。侧栏「分析执行槽」最多滞后 15 秒。修 AN-01 时一起考虑：刷新 env 会增加锁冲突，更适合在 env 状态里直接写入面板刚确认的值。

## 未确认的疑点

- 无。上面各项都已用脚本复现或核对过代码路径。AN-01 在真实服务端发生的频率取决于两个读取请求是否在毫秒级时间窗内重叠（T7 的模拟中最终状态正确），但 T2 证明锁冲突本身在真实 8030 上很容易发生，T1 证明一旦 env 拿到 429 就会进入错误状态。

## 已核对、未发现问题

- **数据契约**：`lib/analyses.ts`、`analysis-runs.ts`、`analysis-evidence.ts` 与基线的差异只有中文标签、错误文案、新增的 `describeEvent`/`errorLabels`/回退标签/`whenVisible`。所有 zod `strictObject`、refine 约束（summary 不变式、事件与摘要引用的 ID+哈希关联、事件数 = revision+1、列表 ID 去重）都没有放宽。
- **关联校验**：`startAnalysis` 仍校验返回的 task_id、summary.task_id、intent 与请求一致；`stopAnalysis` 校验 task_id；`loadAnalysis` 校验 ID；`loadEvidence` 逐项校验 task_id、summary_sha256、数量、顺序、ID 和哈希（`evidence-independent` 5 种错配用例通过）。
- **请求 ID 去重 / 待确认恢复**：先写入 sessionStorage 再 POST；`writing` ref 防止同一帧重复提交（用例通过）；存储失败时不 POST；挂载时只 GET、不自动 POST（用例与 T3 均为 0 次自动 POST）；带 `existing` 的重查遇到 4xx/429 时保留 pending（用例通过）；POST 被中止或超时（`readJSON` 15s）时进入不确定分支并保留 ID。
- **不自动重试未知结果**：全文没有自动 POST；429 重试只针对目录 GET（最多 5 次）和证据 GET（最多 5 次）。
- **停止**：新增确认框，取消时不发请求（用例通过）；确认后再次检查当前任务与 `stopGuard`；`stoppingTask` 按任务 ID 绑定，失败时按任务恢复，保留了 P1-01b C-1 的修复（两个交错用例通过）；文案「停止 → 正在停止… → 已停止」符合规格 §4 第 2 条。
- **切换与卸载**：详情 effect 在切换时中止上一次请求，迟到的结果不会覆盖（用例通过）；`current` 只在 ID 匹配时渲染；卸载时中止全部请求；证据请求随 `AnalysisView` 的 key 重建。
- **后台暂停**：详情与目录轮询都通过 `whenVisible` 在隐藏时挂起（T4：6 秒 0 次请求），清理函数同时撤销计时器和 visibility 监听。
- **用量与费用**：记录行只在 `usage_complete` 时显示 token 数，否则显示「用量待确认」；详情 Token 计量值只计已知用量，预留单独显示并注明「暂计入预算」；`cost_amount` 固定为 null，显示为「未配置单价」，没有编造金额；`model_unknown` 事件写明按预留计入。
- **URL 状态**：`useSearchParams` 外层有 Suspense；非法 `?analysis=` 被忽略；桌面端自动选中最新记录用 replace，不会造成后退循环；后退和刷新保持选择（用例通过）。
- **诚实性**：工作区界面没有里程碑编号（`lib/analyses.ts:12` 只是代码注释）；`synthetic` 标为「内置示例」；修复建议注明不修改代码；CLI 命令（`analyze --case/--intent`、`analyses reconcile`、`runs init`）都与 `src/agent_workbench/cli.py`、`orchestration/cli.py` 一致；文档锚点 `#运行记录与恢复`、`#模型分析与配置` 存在。
- **测试同步**：基线反例只改了选择器和文案，并补了停止确认的两步操作。catalog 429 用例的读取次数从「恰好 3」放宽为 3–5，因为 env 轮询器也会读取，理由成立。原来的接口目录 v3/v2 用例迁到 `agent-contracts.spec.ts`。原来的「`wrong_type` 关联运行按 URL 选中」用例被删除，`runs.spec.ts` 已覆盖 `?run=` 选择。
- **动效**：`.flash` 高亮遵守全局 `prefers-reduced-motion`。

## 跟踪

| ID | 严重级 | 建议负责人 | 状态 |
|---|---|---|---|
| AN-01 | Defect P2 | UI-08 实现者 | 待修复，需补 env 429 不覆盖的 E2E |
| AN-02 | Defect P2 | UI-08 实现者 | 待修复（文案 + 404 状态） |
| AN-03 ~ AN-11 | Defect P3 | UI-08 实现者 | 记录，可在后续迭代处理 |
