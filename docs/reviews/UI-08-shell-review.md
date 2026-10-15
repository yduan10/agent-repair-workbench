# UI-08 外壳与公共组件独立代码评审（shell）

2026-10-15。评审者：独立 reviewer（未参与实现），只读，仅写本报告。范围为 UI-08 的工作区外壳、路由与重定向、总览、环境状态、环境与接入页、通用 UI 组件、格式化与能力目录。结论：**有条件通过**：无 Defect P0/P1；有 5 项 Defect P2、10 项 Defect P3。P2 需要按门禁登记跟踪 ID、负责人和迭代；建议在 UI-08 标 done 前修复 D1–D3，因为这三项都属于用户可直接看到的错误状态或无障碍缺陷。

## 依据与范围

- 规格 `docs/32-ui-08-product-redesign.md`；规则 `AGENTS.md`（前端能力同步门禁）、`docs/04-quality-gates.md`（缺陷等级）；`frontend/AGENTS.md`：已按 Next 16.4 本地文档 `node_modules/next/dist/docs` 核对 `error.js` 的接口。
- 基线 `HEAD 802bf70`，用 `git diff HEAD` 审增量；已删除的旧外壳文件（sidebar、theme-control、module-preview/progress、workspace-footer、旧 capabilities/modules）对照 scratchpad `backup/`。
- 审查文件（SHA-256 前 12 位）：

| 文件 | sha256 |
|---|---|
| app/layout.tsx | 4f378ace354b |
| app/(app)/layout.tsx | db4904168612 |
| app/(app)/error.tsx | d3b890d8b3bb |
| app/not-found.tsx | b1c11e41102b |
| app/(app)/workspace/page.tsx | a1e169ec75b0 |
| app/(app)/workspace/[section]/page.tsx | 9a8bcb264f65 |
| next.config.ts | 96f4faed1505 |
| components/app-shell.tsx | f63b270d8b9d |
| components/environment-status.tsx | 86f9e7c43cf4 |
| components/overview.tsx | 137f130f5ed0 |
| components/capability-badge.tsx | cead99a5e402 |
| components/ui/confirm-dialog.tsx | ad2eb63de64b |
| components/ui/toast.tsx | 2fdbeb8b81ec |
| components/ui/theme-switch.tsx | 73e0b82092f3 |
| components/ui/navigation-guard.tsx | 9b79f5fc9064 |
| components/ui/relative-time.tsx | a89630b46489 |
| components/ui/path-trail.tsx | a82328b279ab |
| components/ui/callout · copy-id · empty-state · environment-context · kbd | d7910d358a72 · 96fb44a54532 · 0a7b4dc0f265 · 9a36488d3bb4 · 144c70921f04 |
| components/ui/page-header · skeleton · status · tabs | 2c54a7683b81 · 23e08617b5fd · 226de947af1b · 54deefb63f6b |
| components/connections-console.tsx | 6663652f78fd |
| components/environment/status-section.tsx | 1b52878c8f20 |
| components/environment/model-section.tsx | a5aa7605902a |
| components/environment/cli-section · data-section · section · commands | 6b013c5f3aac · 7c38d0cec7c1 · 67bda58b03d2 · 92340a912217 |
| components/agent-contracts.tsx | 7be2edf2b720 |
| lib/environment.ts | 70c72fc5b7e3 |
| lib/format.ts | 4f0817c46da4 |
| lib/tones.ts / capabilities.ts / modules.ts / agent-contracts.ts | 1049eb6ec1e2 / 429224629395 / 0657b35f15fe / 562bfafb57ad |
| app/styles/foundation.css / overview.css / environment.css | 4c0c57070b15 / 547d4336bd3d / 01101933c712 |
| tests/progress.spec.ts / appearance.spec.ts / agent-contracts.spec.ts | c3a8d3f93bc6 / fec4298f1f1a / 00ad46c98fab |

- 运行环境：使用已运行的生产前端 3010 和 API 8030。确认 `.next/BUILD_ID`（14:36:39）晚于范围内所有源文件，因此测到的是当前源码的构建。没有构建、启停服务，也没有向 API 发写请求。
- 证据脚本放在 scratchpad：`shell-probe.mjs`、`shell-probe2.mjs` … `shell-probe6.mjs`，以及截图 `pop-1440x1000.png`、`pop-390x844.png`。

## 缺陷

### D1：Defect P2：分析目录读取失败时，环境状态显示绿色「环境就绪」，模型和分析执行槽两行直接消失

- 位置：`frontend/lib/environment.ts:42-52`（`summarize` 中 `if (analysis) {…}` 没有 else 分支）；`:88-96`（读取失败时沿用上次的值，界面没有任何过期提示）。
- 问题：复现目录读取失败时会显示「无法读取」，分析目录失败时却什么都不显示。`overallTone` 只看剩下的两项，于是得出 `pass`。侧栏触发器、总览「本机环境」和弹出层因此一致显示「环境就绪」，模型未配置、执行槽「需要恢复」等状态都看不到。如果首次读取成功、之后一直失败（例如版本不一致导致 zod 校验失败，或持续 429），页面会一直沿用旧值（例如「正在分析」），同时「检查于 刚刚」照常更新，看起来像是新数据。
- 复现：
  1. mock `/api/analysis-runs/catalog` 返回 500：侧栏显示「环境就绪」，总览只有「本机服务」「复现环境」两项（`shell-probe.mjs` 的 `envAnalysisFail`）。同一时刻「环境与接入」的模型区显示「无法读取」，两处互相矛盾。
  2. 不用 mock 也能自然复现：真实 API 对并发的分析目录读取返回 429（6 个并发请求中 5 个是 429，见 curl 实测）。截图 `pop-390x844.png` 是一次真实首屏加载，模型未配置，弹出层却只有两行，显示「环境就绪」。
- 修复建议：`analysis` 为 null 且 API 在线时，补一行 `{ key: "model", tone: "unknown", summary: "无法读取" }`，与复现目录的处理对称。对沿用旧值的情况，记录每个目录各自的成功时间；连续失败超过 1–2 个轮询周期就降级为「无法读取」，或在界面标注「上次读取于…」。补一个 E2E：分析目录返回 500 时，触发器不能是 `pass`。

### D2：Defect P2：侧栏环境弹出层被侧栏的 overflow 裁切，「重新检查」按钮和说明文字被截断

- 位置：`frontend/app/styles/foundation.css:374-388`（`.side-nav { overflow-y: auto }`，计算后 `overflow-x` 也是 auto）；`:562-573`（`.env-pop { position: absolute; width: 300px }`）；`:1256`（手机宽度改为 `min(300px, 86vw-20px)`）。
- 问题：弹出层是侧栏内的绝对定位元素，宽 300px，而侧栏只有 232px（手机抽屉 280px）。实测 `nav.scrollWidth=310 > clientWidth=231/279`：弹出层右侧被裁掉，侧栏出现横向滚动。
- 复现：`shell-probe4.mjs` 在 1440×1000、1440×560、390×844 下都满足 `pop.right=310 > nav.right`。截图 `pop-1440x1000.png` 中「重新检查」只露出半个图标，模型说明被截断；`pop-390x844.png` 中「重新检查」被截断。
- 修复建议：弹出层宽度不要超过侧栏（如 `width: calc(var(--sidebar-w) - 20px)`），或改用 `position: fixed` / popover API 把它放到顶层，并补充布局断言（弹出层的右边界不超出侧栏或视口）。

### D3：Defect P2：手机抽屉导航的焦点管理缺失：关闭时链接仍在 Tab 顺序里（不可见），打开后无法正向 Tab 进入，Esc 后焦点留在屏幕外

- 位置：`frontend/components/app-shell.tsx:22-77`；`foundation.css:1210-1221`（关闭只靠 `transform: translateX(-100%)`，没有 `visibility:hidden`/`inert`）。
- 复现（`shell-probe.mjs`，390×844）：
  1. 抽屉关闭时，从页面顶部按 Tab：跳过链接之后的 13 次 Tab 依次落在屏幕外的品牌链接、6 个导航链接、环境状态按钮、文档、更新记录和 3 个主题按钮上（`x=-270`、`visible:false`）。键盘用户在约 13 步内看不到焦点（WCAG 2.4.7，以及 2.2 的 2.4.11）。
  2. 打开抽屉后焦点仍在「关闭导航」按钮上。这个按钮在 DOM 中位于侧栏之后，所以正向 Tab 直接进入遮罩下的主内容（「重新检查」「查看处理方法」…），抽屉内容只能反向 Tab 到达。背景也没有设 inert。
  3. 焦点在抽屉链接上时按 Esc，抽屉滑出，焦点仍停在 `x=-270` 的「复现」链接上。
- 修复建议：在 ≤900px 且抽屉关闭时给 `aside` 加 `inert`（或 `visibility:hidden` 并配合 transition 延迟）。打开时把焦点移到第一个导航链接，背景 `.app-main` 设 `inert`。按 Esc 或点击遮罩关闭时，把焦点还给切换按钮。这三点都补到 `progress.spec.ts` 的手机用例里。

### D4：Defect P2：总览「最近活动」在部分数据源失败时显示空状态「还没有记录 / 运行第一次复现」，失败的数据源被静默省略

- 位置：`frontend/components/overview.tsx:34-41, 77-79`。
- 问题：只有三个数据源全部失败时才显示错误（`every(rejected)`）。只要有一个成功，就把成功的结果当作完整列表；如果这一个恰好为空，就显示「还没有记录」，并引导用户「运行第一次复现」。
- 复现：mock `/api/runs` 和 `/api/repairs` 返回 500，`/api/analyses` 返回空列表，总览显示「还没有记录 … 运行第一次复现」（`shell-probe.mjs` 的 `overviewPartial`）。本机实际有十余条复现记录，这是错误的状态，并给出了错误的下一步。同样，复现列表失败但分析列表有记录时，复现记录会悄悄消失。
- 修复建议：记录每个数据源的失败情况。只要有任一来源失败，就在表格上方加一行 `Callout tone="unknown"`，例如「复现记录暂时无法读取」，并提供重试；有来源失败时不显示「还没有记录」这个空状态。

### D5：Defect P2：确认对话框在路由变化后仍然打开，确认后执行的是已离开页面的操作

- 位置：`frontend/components/ui/confirm-dialog.tsx:9-39`（Provider 位于常驻外壳，不监听路由变化）。
- 复现（`shell-probe6.mjs`）：/workspace → 调用检查，编辑后点侧栏「复现」，弹出「离开调用检查？」；这时浏览器后退到 /workspace，对话框仍是 `open`，标题仍为「离开调用检查？」，而页面已经是「总览」。此时点「离开」，会执行已卸载的 workbench 中的 `router.push("/workspace/tasks")`。
- 影响：运行记录页的「停止这次复现？」使用同一个 Provider。`run-history.tsx:161-166` 在 `await confirm` 之后不检查组件是否仍挂载，就新建 controller 并发出 `cancelReproduction` POST。用户后退离开后，在其他页面上看到一个没写明是哪条运行的「停止运行」对话框；确认后，仍会从已卸载的页面发出停止写请求。分析页的 `analysis-console.tsx:153` 检查了 `alive.current`，没有这个问题。这个路径由代码阅读推得，对话框会跨路由保持打开已实测确认。
- 修复建议：在 `ConfirmProvider` 中用 `usePathname()` 监听路由，变化时 `close(false)`。另外建议运行记录页在 confirm 返回后检查挂载状态（该文件不在本评审范围，转交 runs 评审）。

### D6：Defect P3：复现执行槽占用时，环境状态的跳转和文案与实际不符

- 位置：`lib/environment.ts:38-40`；`components/environment/status-section.tsx:27-29, 54`；后端 `src/agent_workbench/web_runs/catalog.py:51-99`。
- 问题：后端在有活动运行时返回 `ready:false, reason:"runner_busy"`，并跳过 Docker/镜像检查（`prepared()` 没有执行）。因此 `ready && busy` 这个分支永远走不到：总览上的「查看进行中的任务」实际跳到 `/workspace/connections#status`，而不是 `active_run_id` 对应的运行（`shell-probe.mjs` 的 `busyLinks`）。环境与接入页把 busy 当作 `runnerReady`，显示「就绪」和「Docker 与固定执行镜像已就绪，可以运行复现」，但这时并没有核验 Docker/镜像，而且由于执行槽被占用，此刻也不能开始复现。
- 修复建议：`runner_busy` 时把 href 指向 `/workspace/tasks?run=${active_run_id}`。环境与接入页在 busy 时显示「正在运行一项复现，结束后可开始新的复现」，不要声称镜像已就绪。

### D7：Defect P3：焦点在环境弹出层内时按 Esc，焦点丢到 body

- 位置：`components/environment-status.tsx:16-22`。复现：打开弹出层，Tab 到「处理方法」，按 Esc，`activeElement` 变为 BODY（`shell-probe2.mjs` 的 `popEscInside`）。
- 建议：按 Esc 关闭时，如果焦点在弹出层内，就 `triggerRef.focus()`。

### D8：Defect P3：环境弹出层里的链接绕过 NavigationGuard

- 位置：`components/environment-status.tsx:34`（`Link onClick` 没有走 `useAllowNavigation`）。复现：调用检查有未保存编辑时，点弹出层的「处理方法」会直接跳到 `/workspace/connections#model`，不弹确认（`popLinkFromDirty`）。草稿保存在 workbench 模块级 `tabDraft` 中，切换路由不会丢，所以只是行为不一致。
- 建议：与侧栏链接一样接入 `guard`。

### D9：Defect P3：错误页使用 `reset`，且没有 `global-error`

- 位置：`app/(app)/error.tsx:4,12`。Next 16.4 文档（`03-file-conventions/error.md` 第 117–157 行）说明多数情况应使用 `retry()`（会重新获取并重新渲染），`reset()` 只做重新渲染。另外 `error.tsx` 不覆盖同段的 `layout.tsx`，`AppShell` 及其各个 Provider、根布局、落地页和文档页抛出的异常都会落到 Next 默认页，没有品牌化。
- 建议：改用 `retry`，并新增 `app/global-error.tsx`（自带 html/body 和主题脚本）。

### D10：Defect P3：界面写死 API 端口 8030

- 位置：`lib/environment.ts:34`、`components/environment/commands.ts:5,25`。`next.config.ts` 支持 `AWB_API_PORT`，换端口启动时，环境与接入页仍显示「地址 127.0.0.1:8030」，启动命令也会把用户引向错误端口。
- 建议：构建时通过 `NEXT_PUBLIC_` 注入端口，或者文案中不写具体端口。

### D11：Defect P3：`formatDuration` 进位错误

- 位置：`lib/format.ts:52-55`。实测：59.6s 显示「60 秒」，119.6s 显示「1 分 60 秒」，3599.7s 显示「59 分 60 秒」，9.96s 显示「10.0 秒」。共有 18 处调用。
- 建议：先按整秒取整，再拆分分和秒。

### D12：Defect P3：`theme-color` 只跟随系统，不跟随手动选择的主题

- 位置：`app/layout.tsx:20-25`。实测：系统为浅色、手动选深色时，meta 仍按系统取 `#f6f7f8`，手机浏览器地址栏和页面颜色不一致。
- 建议：在 `apply()` 中同步更新 `meta[name=theme-color]`。

### D13：Defect P3：「环境与接入」标为「网页可用」，与同样只能查看的「修复」标为「网页只读」口径不一致

- 位置：`lib/capabilities.ts:19-20`。两个页面都只能查看和复制，都不发写请求；后者标「网页只读」，前者标「网页可用」，而它的同名能力「接入」（自定义工具接入）仍待开发。AGENTS.md 要求「不得把只读…能力标成网页可用」。徽标旁边已有一句说明，不构成误导性的夸大，但四种状态的口径应当统一。
- 建议：改为 `web_readonly`，或在 docs/32 中写明「设置类页面以查看为完整能力」的判定口径。

### D14：Defect P3：文案与可访问名称的细节

- `CapabilityBadge` 放在 `<h1>` 内，并带有 sr-only 的完整说明（`capability-badge.tsx:6-8`、`page-header.tsx:17`）。标题的可访问名称因此变成「复现网页可用：运行四种内置故障场景；暂不支持…」，读屏的标题列表会很嘈杂。建议把徽标移出 h1，或在 h1 中只保留状态词。
- `model-section.tsx:18` 写的是「「仅检查」分析」，API 和分析页的意图名称是「仅检查契约」，与术语表不统一。

### D15：Defect P3：`PathTrail` 在没有角色的 `span` 上使用 `aria-label`

- 位置：`components/ui/path-trail.tsx:9`。ARIA 1.2 禁止给 generic 角色命名，部分读屏会忽略这个属性，只逐段读文本（分隔符设了 aria-hidden，读出来是「properties args name」，听不出层级）。axe 在元素有文本时只把它列为需要人工复核，所以现有的 axe 用例没有报出来。
- 建议：加 `role="img"` 或 `role="group"`，或者改用 sr-only 文本给出完整的 pointer。

## 未证实 / 观察（不计入缺陷）

- 总览每次进入都读取 `/api/analyses?limit=50`（上限 16 MiB），却只展示 10 条。数据量大时会拖慢首屏，未测量。
- 每个可见标签页每 15 秒调用一次 `/api/reproductions/catalog`，后端每次都执行 `docker image inspect`（最多 8 秒）。隐藏的标签页会暂停，多个可见标签页会叠加。目前没有发现泄漏。
- 抽屉打开时 Esc 的监听挂在 window 上：如果同时打开了确认对话框，按 Esc 会同时关闭两者。影响很小。

## 已检查且未发现问题

- **重定向**：`/workspace/regression?task=abc` 返回 307 到 `/workspace/repairs?task=abc&tab=regression`（查询参数保留）；`/workspace/memory` 返回 307 到 `/workspace`；带尾斜杠的地址先 308 再跳转。都是非永久重定向，不会被浏览器长期缓存。旧版 6 个 section 的地址都有去处。
- **404**：`/workspace/foo`、`/workspace/tasks/x`、`/nope` 都返回 404，页面标题为「页面不存在 · Agent 修复台」，只有一个 `<main>`，不嵌套在外壳里；`dynamicParams=false` 生效。
- **标题**：9 个路由的 `<title>` 互不相同，使用模板「%s · Agent 修复台」。
- **轮询**：用 `page.clock` 实测，可见时 46 秒内请求 3 次 health；标签页隐藏后 61 秒内 0 次；恢复可见时立即检查一次。新的检查会 abort 上一次未完成的请求，卸载时清理 interval、监听器和 controller。
- **没有写请求**：在所有探针（总览、环境与接入、弹出层、抽屉、mock 场景）和现有用例中，非 GET 请求都为 0（确认对话框被取消的情况除外，那时本来就没有发出写请求）。环境与接入页只读，不执行工具，不调用模型，不读取密钥。
- **zod 与目录**：`agent-contracts` 的 strictObject 加 refine（角色、工具唯一，版本 3，`web_runtime_available: true`）与 curl 得到的后端实际响应一致；128 KiB 读取上限、fatal UTF-8 解码、超时和 abort 都在。`environment.ts` 的 health 解析只接受 `status:"ok"`，版本字符串截断到 64 个字符。分析目录的 slot 校验保证 busy 或 recovery 时一定有 task_id。
- **确认对话框**：打开后焦点在「留在此页」，Esc 返回 false，焦点回到触发链接；连续两次 Esc 也不会卡在没有结果的状态（`shell-probe2.mjs`）。手机端从抽屉触发离开确认后，抽屉会关闭并完成导航。
- **主题**：首次绘制前就写入 `data-theme`；localStorage 不可用时仍能切换；「跟随系统」能实时响应；ThemeSwitch 用 `useSyncExternalStore` 处理服务端快照，没有水合警告。
- **文档锚点**：环境状态和环境与接入页引用的 5 个 `/docs/27-local-development-guide#…` 锚点都存在。
- **useSearchParams**：三个工作区页面都包了 Suspense。`RelativeTime` 只在当前元素上 suppressHydrationWarning，并由 30 秒共享定时器刷新，没有订阅者时自动清除。
- **能力文案**：范围内的产品文件里没有里程碑编号、评审或验收记录；只用四种状态；修复为「网页只读」；分析说明写明「修复建议不会自动应用」；CLI 段写明「接入自己的 MCP 服务尚未开放」。
- **现有用例**：`PLAYWRIGHT_CHANNEL=chrome npx playwright test tests/progress.spec.ts tests/appearance.spec.ts tests/agent-contracts.spec.ts --trace off` 结果为 22 passed（49.0s）。其中包括浅色、深色 × 1440/390 的全站 axe 零违规，且无横向溢出。
- **测试改动**：被删除的旧断言都对应已经移除的界面（里程碑进度、组合框主题、标签页式目录）；「无写请求」「提前开放标记拒绝展示」这类安全断言都保留了。

## 结论

| 级别 | 数量 | 项 |
|---|---:|---|
| Defect P0 | 0 | — |
| Defect P1 | 0 | — |
| Defect P2 | 5 | D1–D5 |
| Defect P3 | 10 | D6–D15 |

D1–D4 都是这次 UI-08 外壳新增功能（环境状态、总览、抽屉）中真实可触发的错误状态或无障碍缺陷，现有 E2E 都没有覆盖。修复后请附上「发现 ID → 修改 → 验证」的映射，提交复审。
