# UI-08 调用检查与修复页（workbench-repairs）独立代码评审

2026-10-15。评审者：独立评审代理，未参与 UI-08 实现。范围是调用检查页（CodeMirror 编辑器、无损格式化、未保存草稿的导航保护）和修复页（差异解析与查看器、回归对照表、版本失效时撤回通过结果），以及对应的库、样式和测试。结论：**Defect P1 1 项**（修复记录列表把历史通过显示成当前通过），Defect P2 1 项，Defect P3 8 项，另有 1 项未能复现的疑似问题。P1 按 `docs/04-quality-gates.md` 须在 UI-08 done 前修复。

## 依据与范围

- 规格 `docs/32-ui-08-product-redesign.md`（第 3 节 URL 状态，第 6 节验收），`AGENTS.md`（能力状态与文案诚实），`docs/04-quality-gates.md`（缺陷分级）。
- 调用检查：`frontend/app/(app)/workbench/page.tsx`，`frontend/components/workbench/*`（`workbench.tsx`、`evidence-editor.tsx`、`codemirror.ts`、`json-tools.ts`、`describe.ts`、`check-result.tsx`），`frontend/lib/report.ts`、`samples.ts`，`frontend/app/styles/workbench.css`；同时读了它依赖的 `components/ui/navigation-guard.tsx` 和 `components/app-shell.tsx`。
- 修复：`frontend/components/repair-workspace.tsx`，`frontend/components/repairs/*`（`parse-diff.ts`、`diff-viewer.tsx`、`regression-table.tsx`、`tech-details.tsx`），`frontend/lib/repairs.ts`，`frontend/app/styles/repairs.css`。
- 测试：`tests/reviewer-ui05.spec.ts`、`tests/product.spec.ts`、`tests/repairs.spec.ts`。
- 基线：`git show HEAD:<path>`、`git diff HEAD`，以及 scratchpad `backup/repairs/` 中 UI-08 之前的 `repair-workspace.tsx`、`repairs.ts`、`repairs.spec.ts`。后端判定顺序对照了 `src/agent_workbench/checker.py`。
- 只读评审：除本报告外没有修改项目文件；没有构建、启停服务；对 API 只发了 GET。浏览器探针中的 `/api/check` 全部用 `page.route` 拦截，没有真正发出。

## 运行证据

1. 现有非 live 测试：`PLAYWRIGHT_CHANNEL=chrome npx playwright test tests/reviewer-ui05.spec.ts tests/product.spec.ts tests/repairs.spec.ts --trace off`，**38/38 通过**（44.2s）。
2. 格式化与语法分析模糊测试：`scratchpad/wbr/fuzz.ts`（`node --experimental-transform-types`，直接导入 `json-tools.ts` 的副本）。随机生成 200,000 份文本，原子值包括超长整数 `123456789012345678901234567890`、`1E+400`、`-0`、`A`、`\ud800` 这类孤立代理转义、`"é😀"`、裸 U+2028、内容为 `"{\"x\": [1,2]}"`、`"}"`、`"// not a comment"`、`"/* x */"` 的字符串；空白中混入 CRLF 和制表符；约三分之一的样本再随机插入或删除字符（逗号、括号、引号、反斜杠、U+0001、U+FEFF、CR 等），十分之一加 BOM。结果 **0 个不一致**：
   - 有没有语法错误的判断与 `JSON.parse`（去掉 BOM 后）完全一致；
   - 157,760 份格式化输出中，键、字符串、数字、字面量按源文本逐字节保持不变，BOM 保留，CRLF 保留，再格式化一次结果不变（幂等）。
   - 另外核对了个别输入：`01`、`1.`、`-`、`[1,]`、`{"a":1,}`、`"\x"`、`"\u12"`、`NaN`、字符串中的制表符、600 层嵌套（在第 513 层报错，不会栈溢出）、`1 2`、重复键 `"a"` 与 `"a"`（作为重复键报出）。
3. 浏览器探针：`scratchpad/wbr/wb-probe.mjs`、`rp-probe.mjs`、`tab-run.mjs`、`self.mjs`、`typing.mjs`、`emoji-run.mjs`。用 Chrome 连接已在运行的 3010 生产前端；修复数据全部来自 `page.route` 模拟。

| 编号 | 场景 | 结果 |
|---|---|---|
| W1 | `?source=custom` 空编辑器中粘贴 `{\r\n  "a": 1\r\n}\r\n` 后运行 | 发出的字节是 LF，状态栏显示 LF。粘贴内容会被统一为文档当前的换行风格，这是有意设计（见「已核对」） |
| W2 | 导入 CRLF 文件，在行尾按 Enter，再粘贴含 LF 的文本 | 新插入的换行都是 CRLF，其余字节不变 |
| W3 | 拦截 CodeMirror chunk，让编辑器停在 textarea 回退状态；导入 CRLF 文件后先运行，再输入一个空格后运行 | 第一次发出原始 CRLF；输入一个字符后整份变成 LF（**D3**） |
| W4 | 390px：输入草稿 → 打开抽屉 → 点「复现」 | 确认框在最上层，焦点在框内；选「留在此页」后抽屉仍打开，焦点回到「复现」链接，URL 不变；选「离开」后跳转，抽屉关闭 |
| W5 | 从总览进入调用检查 → 编辑 → 浏览器后退 → 前进 | 后退不弹框（设计如此），前进后草稿恢复；离开整个文档时触发 `beforeunload` 原生提示 |
| W6 | 运行后点「下载报告」（程序化点击 blob 链接），再点侧栏「更新记录」并选择离开 | 跳到 `/updates`，捕获阶段记下的链接没有被下载链接污染 |
| W7 | 草稿未保存时点侧栏中当前页「调用检查」 | 弹出「离开调用检查？」，选择离开后什么也没发生（**D8**） |
| W8 | `/api/check` 返回 502 HTML、返回 `null` | 分别提示「连接不上本机服务」和「版本不一致」，不崩溃 |
| W9 | 粘贴 200 KB 文本后快速输入 108 个字符，CPU 降速 1×/6×/20× | 三次都没有丢字（S1 未复现） |
| R1 | 列表有 A（当前有效）和 B（记录为通过，但回归结果已因版本变化失效）；默认选中 A | B 行显示绿色「回归通过」，读屏文本为「三角色修复，回归通过」；选中 B 后变为「结果已过期」；切回 A 后 B 又变回「回归通过」（**D1**） |
| R2 | 差异的候选快照与记录不一致 → 点「回归结果」标签 | 「代码差异」标签下标题、详情和列表行都是「结果已过期／无法核对代码差异」；切到「回归结果」后三处都变回「回归通过」（**D2**） |
| R3 | 10 种畸形或恶意补丁：`<img onerror>` 与 `<script>`、hunk 内以 `---`/`+++` 开头的行、行数不符、多文件、`\ No newline`、emoji 单词差异、伪造路径、超大 hunk 头、空补丁、CRLF | 没有页面错误，没有生成 img 或 script 元素，没有弹窗；hunk 内行号正确。路径和统计问题见 D5，代理对拆分见 D6 |
| R4 | `?repair=nonsense`、`?repair=B&candidate=C`、`?task=B&repair=A`、`?tab=regression&repair=B`、`/workspace/regression?repair=B&candidate=C` | 都收敛到规范的 `?task=`（3 次以内导航，没有循环），`candidate` 和 `tab` 保留；旧的 regression 重定向保留查询参数 |
| R5 | `/workspace` → `/workspace/repairs`（自动选中最新记录）→ 后退 | 回到 `/workspace`。自动选中用的是 replace，不会把后退困在本页 |

4. 真实 API（只用 GET）：`/api/repairs?limit=50` 当前返回空列表，所以修复页的结论都来自模拟数据。

## 缺陷

### D1 — Defect P1：修复记录列表（以及总览）把记录时的「回归通过」显示成当前通过

- 位置：`frontend/components/repair-workspace.tsx:45-47`（`summaryStatus`）、`:184`（`rowStatus`：只有当前选中行使用 `taskStatus`）、`:217-224`（行内 sr-only 文本和 `StatusBadge`）；色调来自 `frontend/lib/tones.ts:15-18`（`candidate_verified → "pass"`）。范围外的同类问题：`frontend/components/overview.tsx:39` 的「最近活动」也直接用 `recorded_outcome` 和 `repairTone`。
- 原因：列表接口只返回 task 摘要，不含当前的 comparison 核验。未选中的行直接把 `recorded_outcome` 显示为「回归通过」，并使用 pass 色调。`lib/repairs.ts` 第 1 行的约定是「A historical outcome never substitutes current verification」，详情页 `taskStatus` 也是按这个约定实现的，列表却没有遵守。旧页面的任务下拉框不显示结论，所以这是 UI-08 新引入的问题。
- 复现（R1，已验证）：B 的 comparison 为 `verification: "unavailable"`（`artifact_or_version_mismatch`）。默认选中 A 时，B 行显示绿色「回归通过」；只有点开 B 才变成「结果已过期」；切回 A 后 B 又显示「回归通过」。总览的最近活动同样会把 B 显示为「回归通过」。
- 影响：属于 quality gates 中的「错误报告通过」。用户扫一眼列表或总览，就会把版本已失效的候选当作当前有效的通过；而详情页、测试「历史通过在版本失效后不得显示当前通过」以及技术详情中「记录时的结果」的写法，都在刻意区分这两种状态。
- 建议：列表和总览不要用 pass 色调和「回归通过」表达未核验的历史结果。可以显示为「记录为通过」并使用 neutral 或 accent 色调，sr-only 文本加上「（记录时）」；只有已经读到详情、`taskStatus` 确认当前有效时才显示「回归通过」。如果希望列表直接给出当前状态，需要后端在列表摘要中提供当前核验字段。补一条测试：未选中的失效记录在列表中不得出现「回归通过」，总览同理。

### D2 — Defect P2：差异核对失败后撤回的通过，切到「回归结果」标签就恢复了

- 位置：`repair-workspace.tsx:162-164`（标签不是 `diff` 时 `setDiffState(null)` 并直接返回）、`:181`、`:184`、`:242`（撤回只看当前的 `diffError`）。
- 复现（R2，已验证）：diff 返回的 `candidate.tree_sha256` 与记录的 `snapshot_sha256` 不一致。「代码差异」标签下，标题、列表行和结论都是「结果已过期／无法核对代码差异」，与测试「差异候选版本错配被拒绝，且撤回通过结果」的预期一致。点「回归结果」后，三处都变回「回归通过」。之间没有任何新的证据。
- 影响：同一条记录的状态随标签变化，前端自己检测到的不一致被丢弃。回归核验本身由服务端完成（comparison 为 `verified`），而且旧页面的 regression 分区也不读取差异，所以这一项不是 UI-08 引入的，定为 P2；但它与本页「撤回通过」的设计意图相矛盾。
- 建议：把差异核对失败按 `task_id:candidate_id:sha256` 记下来（例如存入 `withdrawn` 集合），切换标签时不清除，直到刷新记录；或者在回归标签也读取一次差异（只用于核对，不展示）。补一条「代码差异失败 → 切到回归结果仍不显示通过」的测试。

### D3 — Defect P3：textarea 回退状态下输入任何字符，CRLF 都会被统一改成 LF

- 位置：`frontend/components/workbench/evidence-editor.tsx:99-118`（受控 textarea，`onChange={event => onChange(event.target.value)}`）。
- 原因：按 HTML 规范，textarea 的 API value 会把 CRLF 和孤立的 CR 都规范化为 LF。React 把带 CRLF 的值写进 textarea 后，用户输入一个字符，`onChange` 收到的整份文本就都是 LF 了。
- 复现（W3，已验证）：在 CodeMirror chunk 加载失败（或还没加载完）时导入 `{\r\n"a": 1\r\n}`，直接运行时发出原始字节；在行尾输入一个空格后再运行，发出的是 `{\n"a": 1\n} `。
- 影响：只改动空白，不会改变检查结论（JSON 字符串里不能出现裸 CR/LF），摘要按规范化后的 JSON 计算，也不受影响。但这与文件头注释「text sent is exactly what is in the editor」及状态栏「UTF-8 · CRLF」不一致。窗口很短（chunk 加载前或加载失败时），因此定为 P3。`reveal` 的回退分支已经考虑了这种规范化，只是 `onChange` 没有考虑。
- 建议：回退分支中，如果原文本是 CRLF，就把 `event.target.value` 的 `\n` 还原为 `\r\n`；或者在 CodeMirror 就绪前把 textarea 设为只读，仅用于展示。

### D4 — Defect P3：12 秒前端超时和非 JSON 响应都提示「连接不上本机服务」

- 位置：`frontend/components/workbench/workbench.tsx:199`（12 秒 abort）、`:210`（`response.json()`）、`:225-227`。
- 影响：检查器正忙或较慢、请求被前端 abort 时，提示的是「连接不上本机服务」，同时触发一次环境刷新；服务端返回非 JSON 的错误页时也是同样的提示（W8）。代码路径已核对，502 场景已复现。不影响判定。
- 建议：区分 `AbortError`（超时：「检查超过 12 秒仍未返回，请稍后重试」）和 JSON 解析失败（「本机服务返回了无法识别的响应（HTTP n）」），只在网络错误时触发 `requestEnvironmentRefresh()`。

### D5 — Defect P3：差异头部的路径和增删统计取自补丁文本，没有使用已校验的字段

- 位置：`frontend/components/repairs/diff-viewer.tsx:27-32`；`parse-diff.ts:47-48`、`:60-61`。
- 复现（R3，已验证）：
  - 补丁头为 `--- baseline/../../etc/passwd` / `+++ candidate/../../etc/shadow` 时，标题显示「../../etc/passwd → ../../etc/shadow」，旁边仍是「快照已核对」。zod 已把 `diff.path` 限定为 `source/server.py`，但页面没有用它。
  - 多文件补丁中，第二个文件的 `---`/`+++` 头不在 hunk 内，被当作删除行和新增行计数（2/2 被显示为 +3/−3），也没有行号。
- 影响：补丁由本机后端生成，正常情况下不会出现；但标题和统计有可能与已校验的契约不一致。
- 建议：标题始终使用 `diff.diff.path`（已校验）；补丁头的路径与它不一致时，显示一条中性提示或忽略。第一个文件的头之后再出现 `--- `/`+++ ` 时按注释行处理，不计入增删。

### D6 — Defect P3：单词级高亮可能把代理对拆开

- 位置：`parse-diff.ts:94-103`（按 UTF-16 码元比较前缀和后缀）。
- 复现（已验证）：`😀` 改为 `😁` 时，高亮 span 内只有孤立的低位代理（`de00`/`de01`），高位代理落在前一个文本节点中。Chrome 仍能拼出正确的字形（截图正常），但高亮范围没有意义，换一个渲染环境可能显示为替换字符。
- 建议：比较前缀和后缀后，如果边界落在代理对中间，就向外扩展一个码元；或者用 `Array.from` 按码点比较。

### D7 — Defect P3：格式化器源码中直接写入了不可见的 U+FEFF 字面字符

- 位置：`frontend/components/workbench/json-tools.ts:219`（`parts.push("﻿")`，字节为 EF BB BF）。
- 影响：功能正确。但编辑器或格式化工具很可能悄悄去掉这个字符，那样格式化后就会丢失 BOM，而 diff 里几乎看不出变化（目前有 reviewer 测试兜底）。
- 建议：改写为 `"﻿"`。

### D8 — Defect P3：在调用检查页点击侧栏中的「调用检查」也会询问是否离开

- 位置：`workbench.tsx:98-110`；`components/app-shell.tsx:25`（守卫不判断目标是不是当前页）。
- 复现（W7，已验证）：草稿未保存时点击当前页的导航项，会弹出「离开调用检查？」；选择「离开」后 URL 和内容都不变。
- 建议：在守卫中忽略目标路径与当前 `pathname + search` 相同的情况（`lastLink` 已经记下了目标），或者在 Sidebar 中让当前页链接跳过守卫。

### D9 — Defect P3：语法提示中 `-Infinity` 的说明不准确

- 位置：`json-tools.ts:136-148`（`-` 先进入数字分支）。
- 影响：`NaN`、`Infinity` 会提示「JSON 不支持 NaN 或 Infinity」，`-Infinity` 却提示「数字格式无效」，用户不容易看出原因。
- 建议：在数字分支失败时，检查 `-Infinity` 前缀并给出相同的说明。

### D10 — Defect P3：测试覆盖缺口

- 缺少 D1（列表或总览中未选中的失效记录不得显示「回归通过」）和 D2（切换标签后撤回状态保持）的用例。
- 缺少 390px 抽屉中「取消保留抽屉和草稿，离开后关闭抽屉」的用例。W4 已手工验证行为正确，补测试可以防止回退。
- 缺少 textarea 回退状态（CodeMirror chunk 加载失败）的字节保真用例（D3）。
- 差异解析没有针对畸形补丁的单元测试或 E2E 用例（R3 的这些输入可以直接用作测试数据）。

### S1 — 疑似（未复现）：`replace(value)` 在被动 effect 中执行，理论上可能用过期的值覆盖更新的输入

- 位置：`evidence-editor.tsx:65`。
- 推演：CodeMirror 的输入通过 `updateListener → onChange → setSource` 更新父组件状态，再在 effect 中执行 `replace(value)`。如果某次提交的被动 effect 推迟到下一次 CodeMirror 事务之后才执行，它持有的旧 `value` 与 `sliceDoc()` 不同，就会把文档改回旧值，丢掉一次输入。React 对离散事件通常会同步执行被动 effect，W9 在 1×、6×、20× CPU 降速下都没有复现，因此只记为疑似问题。
- 建议（低成本加固）：在编辑器内部记下最近一次通过 `onChange` 发出的文本，只有当 `value` 既不等于当前文档、也不等于这次发出的文本时，才执行 `replace`；也就是只响应真正来自外部的替换（示例、导入、格式化）。

## 已核对、未发现问题

- **发给 /api/check 的字节**：`run()` 直接发送 `sourceRef.current`，不做解析或重新序列化；next.config 的 rewrite 原样转发请求体。导入文件使用 `TextDecoder("utf-8", { fatal: true, ignoreBOM: true })`，BOM 会保留，非 UTF-8 文件会被拒绝。CodeMirror 文档使用显式的 `lineSeparator`，`sliceDoc()` 返回的就是原文；CRLF 文档中按 Enter 插入 CRLF（W2）；孤立的 CR 作为可见字符保留。BOM、CRLF、`9007199254740993.10`、`1E400`、`-0.0`、`é\/`、重复键都在现有测试中逐字节断言并已复跑。粘贴时会统一为文档当前的换行风格（W1），这是 `clipboardInputFilter` 的有意设计，只影响空白，不改变结论，摘要也不受影响，因此不记为缺陷。
- **格式化无损**：见运行证据 2。另外，有语法错误时禁止格式化；重复键和 BOM 不会阻止格式化，并原样保留；格式化后文本未变时什么也不做；结尾换行保留。
- **定位与提示**：linter 使用 LF 拼接的文本，因此偏移量就是 CodeMirror 的位置；状态栏和不符合项使用原文偏移，`reveal` 在 CRLF 文档中会换算偏移（textarea 回退分支也会换算）。`resolvePointer` 能正确处理 `~0`/`~1`、空键和前导零索引（不匹配）。编辑后报告会被清空，不会把旧结果对应到新文本上。
- **判定展示**：`checkScope` 与 `checker.py::_check` 的执行顺序一致：`tool_name_mismatch` 最先追加，不会被截断；`result_call_mismatch` 先于 `tool_error`；截断时「调用关联」退回「未检查」，没有被高估为「通过」。`reportSchema` 相对 HEAD 没有放宽；三个内置示例的结论（不通过、通过、无法判定）与说明一致。
- **忙碌锁**：检查期间编辑器只读，示例、导入、格式化和拖放都被禁用；Mod-Enter 会检查 `locked`；卸载时 abort 正在进行的请求。
- **导航保护**：取消后草稿和字节都保持不变（现有测试已复跑，W4）；抽屉中的确认框和焦点表现正确（W4）；浏览器后退和前进不弹框，但草稿保存在标签页内存中，回来时恢复（W5），与提示文案「编辑内容会暂存在本标签页」一致；离开文档时有 `beforeunload` 提示；捕获阶段记录链接的做法不会被程序化点击污染（W6）。Tab 键没有绑定缩进，因此不会困住键盘焦点。
- **修复页校验**：`lib/repairs.ts` 相对 UI-08 之前的版本，zod 部分只改了标签文案，并把差异错配拆成单独的 `diffMismatch` 提示。strictObject、上限、关联 refine、`accepted: false`、diff 的 `tree_sha256` 与 `snapshot_sha256` 核对都保持不变。
- **切换与迟到响应**：详情和差异都按记录 abort；`current` 只接受 `task_id` 匹配的数据；差异按 `task:candidate:sha` 加键，并再次核对 task 和 candidate（现有测试「切换记录取消迟到详情与差异」已复跑）。版本失效时详情区撤回通过结果（现有测试已复跑）。
- **URL**：`useSearchParams` 外层有 Suspense；`?repair=` 统一改写为 `?task=`，无效 ID 回退到最新记录；改写和自动选中使用 replace，没有循环（R4、R5）；陌生的 `candidate` 会明确提示已回退。
- **补丁渲染安全**：全部作为 React 文本节点渲染，没有 `dangerouslySetInnerHTML`；10 种畸形补丁都没有触发异常或生成元素；hunk 内以 `---`/`+++` 开头的删除或新增行能正确识别并编号；`\ No newline` 不占行号；CRLF 补丁只在显示时去掉行尾 CR，「复制补丁」复制的仍是原文。
- **只读与文案**：修复页只发 GET（现有测试断言 0 次写请求）；能力标记为「网页只读」；页面写明「修复在终端运行，网页只读取结果」「人工接受尚未开放；通过不代表已写回项目」；运行中的记录只提示手动刷新，没有无限轮询；页面上没有里程碑编号。
- **布局与可访问性**：现有测试覆盖 320/390/1280/1440 宽度、浅色和深色，axe 无违规，无横向溢出；差异区和回归表是可聚焦的滚动区域，回归表有 caption、列组表头和行表头；结果区有 `aria-busy` 和 `role=status` 播报。
