# UI-08 复现页（runs）独立代码评审

2026-10-15。评审者：独立评审代理，未参与 UI-08 实现。范围为复现页的运行列表、运行详情、运行报告、复现启动面板及对应库、样式与测试。结论：**无 Defect P0/P1**；Defect P2 共 2 项，Defect P3 共 8 项，另有 1 项只核对了代码路径的疑似问题。P2 按 `docs/04-quality-gates.md` 规定登记跟踪；它们不阻断 UI-08 done。

## 依据与范围

- 规格 `docs/32-ui-08-product-redesign.md`（第 3 节 URL 状态、第 4 节文案与「内置示例」、第 6 节验收），`AGENTS.md`，`docs/04-quality-gates.md` 缺陷分级。
- 源码：`frontend/components/run-history.tsx`、`run-detail.tsx`、`run-report.tsx`、`reproduction-panel.tsx`，`frontend/lib/runs.ts`、`reproductions.ts`、`reproduction-result.ts`，`frontend/app/styles/runs.css`。基线为 `git show HEAD:<path>` 和 `git diff HEAD`。
- 测试：`tests/runs.spec.ts`、`reproductions.spec.ts`、`reproduction-result-independent.spec.ts`；另外读取了 `runs-live.spec.ts`、`reproductions-live.spec.ts`，核对选择器与新界面一致（未运行 live 测试）。
- 只读评审：除本报告外未修改项目文件；未构建、未启停服务；对 API 只发 GET。

## 运行证据

1. 现有非 live 测试：`PLAYWRIGHT_CHANNEL=chrome npx playwright test tests/runs.spec.ts tests/reproductions.spec.ts tests/reproduction-result-independent.spec.ts`，**39/39 通过**（22.2s）。
2. 独立探针脚本：`scratchpad/runs-review/probe.mjs`，Chrome，连接已运行的 3010 生产前端，数据全部由 `page.route` 模拟。主要结果：

| 编号 | 场景 | 结果 |
|---|---|---|
| T1 | 390px：选 B → 点「返回列表」→ 选 C → 浏览器后退 | URL 为 `?run=B#run-list`，列表与详情仍选中 C（**D1**） |
| T2 | 选 A → 状态筛选 failed → 后退 | URL 无 `status`，下拉框仍为 failed，列表仍被筛选（D3） |
| T3 | CLI 场景 `wrong_type` 失败 / `oom` 内存超限 | 标题分别为「与预期不符」「运行环境出错」（**D2**） |
| T4 | 打开有报告的运行，记录结论标题的变化 | 先出现「调用成功」（说明为「没有可核验的报告」），随后才是「正常调用通过」（D4） |
| T5 | 运行中，模拟标签页隐藏 5 秒 | 隐藏期间 0 次请求，恢复可见后立即继续轮询（符合要求） |
| T6 | 停止确认框打开时浏览器后退 | 对话框关闭，未发出 cancel（符合要求） |
| T7 | 会话存储中有查不到的待确认请求 | 0 次 POST，「开始复现」一直禁用，没有放弃该请求的入口（D6） |
| T8 | 停止请求连接中断 | 失败提示只在 toast 中显示，8 秒后消失；确认后焦点落到 `body`（D5） |

3. 真实 API（只用 GET）：8 条本机记录；`timeout`、`response_lost` 两条 `outcome_unknown` 报告的 `execution.error=null`、`cleanup=removed`，`reproductionResult` 会给出「结果未知」，结论正确。

## 缺陷

### D1 — Defect P2：手机端「返回列表」锚点写入无状态的历史记录，后退后 URL 和选中记录不一致

- 位置：`frontend/components/run-detail.tsx:34`（`<a href="#run-list">`），以及 `run-history.tsx:90-95`（`writeParams` 保留现有 hash）。
- 原因：普通锚点只改 hash，浏览器新建了一条 `history.state === null` 的记录。Next 16 的 `handlePopState`（`node_modules/next/dist/client/components/app-router.js:61-65`）遇到 `state` 为空的记录会直接 return，不更新 `useSearchParams`。
- 复现（T1，已验证）：在 390px 下打开 B，点「返回列表」，再打开 C，然后按浏览器后退。地址栏变为 `?run=B#run-list`，页面仍然选中并显示 C。再后退一次才恢复同步。之后 `#run-list` 会一直留在 URL 里，刷新或分享 `?run=C#run-list` 时页面滚到列表而不是详情。
- 影响：违反规格第 3 节「选中记录写入 URL，可分享、可后退」，用户会以为自己在看 B 的结果。不涉及写操作或判定错误。
- 建议：改成按钮，用 `document.getElementById("run-list")?.scrollIntoView()` 并把焦点移到列表标题，不修改 URL；或者用 `history.replaceState` 写 hash。`writeParams` 写入时清掉 `url.hash`。补一条 390px 下「返回列表 → 选择 → 后退」的 E2E。

### D2 — Defect P2：终端发起的其他 13 种场景总被描述为「与预期不符」或「运行环境出错」

- 位置：`frontend/lib/reproduction-result.ts:10-33`；用于 `run-detail.tsx:29-31`。
- 原因：`reproductionResult` 只认识 `pass` 和 `tool_error` 两种「符合预期」的形态。运行列表明确写着「包括在终端发起的运行」（`run-history.tsx:256`），而 CLI 可运行 17 种场景（`src/agent_workbench/runner/models.py` 中的 `Scenario`）。
- 复现（T3，已验证）：`wrong_type` 场景失败（返回检查不通过，这正是该场景要复现的结果）时，标题为「与预期不符 — 结果和所选场景的预期不同」，色调为 fail。`oom` 场景内存超限（同样是预期结果）时，标题为「运行环境出错 — …处理下方错误后重新运行」。`stdout_flood`、`pid_limit`、`crash_*` 等场景同理。
- 影响：「与预期不符」是对预期作出的断言，但代码并不知道这些场景的预期是什么，属于结论描述不实。不会把失败写成通过（`pass` 结论要求 `scenario === "pass"`），存储的判定也不受影响，因此定为 P2，不是 P1。
- 建议：网页的 4 个场景以外，不作「是否符合预期」的判断，回退到 `statusSentence`，或使用中性措辞，例如「终端运行的场景，网页不判断是否符合预期」。只对 `reproductionScenario` 中的场景给出「与预期不符」。在独立测试中补 `wrong_type` 和 `oom` 用例。

### D3 — Defect P3：搜索词和状态筛选只在挂载时读取 URL，后退/前进后与地址栏不一致

- 位置：`run-history.tsx:63-64`（`useState` 初值读 `q`/`status`），184-186（`replaceState`）。
- 复现（T2，已验证）：选 A（push）→ 筛选 failed（replace 到 `?run=A&status=failed`）→ 后退，URL 变为 `/workspace/tasks`，下拉框仍为 failed，列表仍被筛选，此时刷新会丢失筛选。
- 建议：由 `params.get("q"/"status")` 派生筛选值，输入框可用本地草稿加同步 effect；或者在 `params` 变化时把 URL 中的值同步回状态。

### D4 — Defect P3：首帧把有报告的运行说成「没有可核验的报告」

- 位置：`run-detail.tsx:29-31`，`run-report.tsx:66-70`（`loading` 在 effect 中才设为 true）。
- 复现（T4，已验证）：每次打开有报告的成功运行，结论区先渲染「调用成功／运行已结束，但这条运行没有可核验的报告」，随后才切换为骨架和「正常调用通过」。
- 建议：`pendingReport` 改为 `!result && !!run.report_sha256 && !report.failure`，即在报告尚未得出结论前一律显示骨架；也可以把 `loading` 的初值设为 `!!run.report_sha256`。

### D5 — Defect P3：停止结果无法确认时只有 8 秒 toast，确认后焦点丢失

- 位置：`run-history.tsx:175-178`；`components/ui/confirm-dialog.tsx:19-23`。
- 复现（T8，已验证）：cancel 连接中断后，「无法确认是否已停止…」只出现在 toast，8 秒后消失，页面上不再有任何提示。基线在详情区用 `role=status` 常驻显示同类提示。另外确认后停止按钮立即变为 disabled，原生 `<dialog>` 无法把焦点还给它，焦点落到 `body`，键盘用户回到页面顶部。
- 建议：结果未知时，在活动运行条或详情区常驻显示一行提示，直到下一次读到终态。关闭确认框后把焦点移到运行状态或活动运行条上。

### D6 — Defect P3（基线已存在）：待确认请求查不到时无法放弃，本标签页内永久不能开始新复现

- 位置：`reproduction-panel.tsx:57-67`、`86-99`、`184-188`。
- 复现（T7，已验证）：请求在到达服务前失败，或记录已被清理时，`GET /api/runs/{request_id}` 一直返回 404，「开始复现」一直禁用，只有「查询提交结果」按钮。同一标签页刷新后仍会恢复为该状态。另外 `unknownNotice` 中的「正在查询」在查询完成后仍然保留。
- 说明：不自动重试的约束本身正确，这一项不要求自动处理。
- 建议：增加用户显式操作「放弃这次提交」，先确认、说明风险（不能推断未执行），再清除 sessionStorage。恢复时的文案改为不含「正在」的静态说明。

### D7 — Defect P3：活动运行条 `role="status"` 内含每 30 秒更新的相对时间和按钮

- 位置：`reproduction-panel.tsx:165-176`。
- 影响：`RelativeTime` 每 30 秒更新一次文字（例如从「1 分钟前」变为「2 分钟前」），屏幕阅读器会反复播报整个区域；live region 中也不宜放可操作控件。
- 建议：`role=status` 只套在「正在运行／正在停止…」这段文字上。

### D8 — Defect P3：停止确认文案承诺「会被停止并清理」

- 位置：`run-history.tsx:161`。
- 影响：报告中可能出现 `cleanup=unconfirmed`（页面上会显示「未确认清理」）。确认框把清理说成必然结果，与报告的实际可能性不一致。
- 建议：改为「将请求停止容器并清理；清理结果以运行报告为准。」

### D9 — Defect P3：未写入 URL 的自动选中会在刷新后跳到另一条记录

- 位置：`run-history.tsx:87-88`。
- 影响：URL 中没有 `run` 时，详情跟随 `visible[0]`。用户正在看自动选中的最新记录，点「刷新」后如果出现了新的 CLI 运行，或者输入了搜索词，详情会切换到另一条记录，地址栏也无法分享当前看到的记录。测试中 `not.toHaveURL(/run=/)` 是刻意设计的，因此定为 P3。
- 建议：首次自动选中时用 `replaceState` 写入 `run`，或者在用户主动刷新时保持当前显示的记录。

### D10 — Defect P3：测试覆盖缺口

- 删除了 `reproductions.spec.ts` 中「降低动效时场景选择器 `transitionDuration` 为 0」的断言（全局 `prefers-reduced-motion` 规则仍在 `foundation.css:1261`，实际行为未退化）。
- 缺少 D1、D2、D3、D6 对应的用例。

### S1 — 疑似（只核对了代码路径，未用脚本复现）：提交期间浏览器后退，迟到的接受响应仍会抢走选择

- 位置：`run-history.tsx:100-115`。`selectionVersion` 只在 `select()` 中递增，浏览器后退/前进（popstate 改变 `?run`）和改变自动选中的筛选都不会递增。如果提交期间用户按了后退，迟到的 202 仍会执行 `select(id)` 并 push 新记录。影响有限，估计为 P3。建议在 effect 中观察 `explicit` 的变化并递增 `selectionVersion`。

## 已核对、未发现问题

- **zod 校验未削弱**：`runs.ts`、`reproductions.ts` 相对 HEAD 只改了文案，新增了 `activeStatus`、`runDurationMs`、`pollDelay`；strictObject、上限、去重、事件顺序校验、1 MiB 读取上限、content-type 与严格 UTF-8 解码都保持不变。
- **报告核验**：`loadVerifiedReport` 先计算 SHA-256，并在 schema、`record_id`、`attempt_id` 三项都通过后才返回；下载时 `read(true)` 总是重新拉取并重新核验，保存的是服务端原始字节（`saveDownload(value.bytes)`）；失败时清空已显示的报告并移除「已校验」。切换记录时 `useVerifiedReport` 的 cleanup 会 abort，迟到的下载不会落盘（已有测试覆盖，复跑通过）。
- **请求 ID 去重与恢复**：每次点击生成一个 `crypto.randomUUID()`，`writing` ref 同步防止重入，POST 前先写入 sessionStorage；只有 400/403/409/410/429 视为确定拒绝，5xx、超时、断连和响应关联不符都进入 unknown；unknown 状态下只发 GET 查询，查询结果按场景核对；卸载时 abort 但保留 pending，刷新后恢复且不自动重发。新增的 `!!pending` 禁用条件比基线更严格。
- **停止**：先经过确认框（默认焦点在「取消」）；按 id 的 `stopGuard` 防止重复点击；`cancel_requested` 不当作终态，状态仍以轮询为准；卸载时 abort 未完成的 cancel，此时不再 reload；只有网页执行槽中的运行（`active_run_id`）显示停止按钮，CLI 运行不显示。
- **轮询**：详情只在 queued/running 时轮询，读取出错后停止并说明原因；目录只在有 `active_run_id` 时轮询；`pollDelay` 在标签页隐藏时暂停（T5 验证），abort 时清理计时器和监听器。
- **切换与离页**：详情读取以 `selectedId` 为键进行 abort，`current` 只接受 `run_id` 匹配的数据，不会显示上一条记录的内容（已有测试复跑通过）。
- **Suspense 与 URL**：`useSearchParams` 外层有 `<Suspense>`；`pushState`/`replaceState` 与 Next 16 原生历史集成，行点击使用 push，方向键使用 replace，避免产生大量历史记录；`?run=` 用 UUID 正则过滤，`?status=` 用白名单过滤，`?q=` 截断到 100 字符。
- **只读**：运行列表、详情、报告只发 GET；页面上的写请求只有「开始复现」和「停止」两种，与基线一致，没有新增写请求类型。
- **文案**：页面上没有里程碑编号；启动区注明「内置示例」；「结果未知」统一使用一句说明（不推断工具是否执行，不自动重试）；停止相关文案依次为「停止 → 正在停止… → 已停止」。
- **样式与可访问性**：现有测试中 1440/390 × 浅色/深色的 axe 检查无违规，无横向溢出；时间线中运行状态的动效受全局 reduced-motion 规则约束。
