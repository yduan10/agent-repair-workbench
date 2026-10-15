# UI-08 核心页面修复后独立审计

- **审计对象**：两批定向复审：① `UI-08-workbench-repairs-review.md` D1–D10/S1；② `UI-08-analysis-review.md` AN-01–AN-11。只查对应缺陷修复及直接调用方，不宣称全仓审计。
- **审计版本**：HEAD `802bf70ebb509ac7e5bd7ebb8f189b4070553823` + 2026-10-15 工作树。16 个关键生产文件指纹见本地 `artifacts/ui08-core-followup-sha256.json`。新增独立测试与本报告外未修改生产代码。
- **技术栈**：Next.js / React / TypeScript / CodeMirror / Playwright。
- **业务场景**：General SaaS。
- **审查严苛度**：Mission-Critical。
- **审计时间**：2026-10-15，Asia/Shanghai。

## 1. 代码质量评估卡

- **综合质量得分**：85 / 100（D2-M 修复后；首轮 82 分记录保留在下方）。
- **上线评估结论**：定向代码修复门禁 Pass（P0/P1/P2 均为 0），BOM 导航用例已在生产构建复跑通过。原阻断 D1 与本轮 D2-M 已关闭。
- **审计范围**：分两批只复核已报告缺陷的小范围代码；未重新审计完整后端/模型/沙箱。
- **未评估项**：真实模型运行、真实候选修复与容器回收不属于本次 UI 复审，不以浏览器 mock 代替这些门禁。读屏器实际播报兼容性未做真人/设备验证。

| P0 | P1 | P2 | P3 |
|---|---|---|---|
| 0 | 0 | 0 | 15 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: P3×15 (15) = 15
RAW SCORE: 85
CAP APPLIED: none
FINAL SCORE: 85 / 100
VERDICT: Pass for reviewed UI scope; production-mode BOM test passed
NOT ASSESSED: actual model/sandbox repair; real assistive-technology speech
```

### 运行证据与边界

- `PLAYWRIGHT_CHANNEL=chrome npx playwright test tests/repairs.spec.ts tests/analyses.spec.ts tests/console-evidence.spec.ts tests/console-review.spec.ts tests/evidence-independent.spec.ts tests/ui08-review-fixes.spec.ts --trace off`：**`72 passed (1.1m)`**。包含 D1 列表/总览、D2 标签切换、AN01 429 时间戳与 AN02 404/放弃。analysis/repair 的业务响应由 route mock 提供，不是真实模型验收。
- 新增 `tests/ui08-core-independent.spec.ts`：**`1 failed`**，失败于第 187 行，实测收到 `三角色修复回归通过`，预期保持 `结果已过期`。全部 repair 响应为 mock，无真实写请求。
- `tests/product.spec.ts tests/reviewer-ui05.spec.ts`：首轮 **`1 failed, 17 passed (1.0m)`**，BOM 导航保护用例超时；正在单独复核，不能把这一轮写成通过。这组 product 的 `/api/check` 使用真实服务（无持久任务创建）；模型/修复不执行。
- 未启动/关闭服务、未构建；复用 root 管理的 3010 与 8030。

## 2. 生产事故风险推演

P0/P1：none。D2-M 是局部 UI 判定展示问题，不绕过服务端回归判定、不接受补丁、不写回用户代码，但会使用户误读已撤回的候选状态，必须在本次收尾修复。

## 3. 详细审计明细

### P0 / P1

none。

### P2 — D2-M：切换候选后恢复了已撤回的任务通过状态

- **位置**：`frontend/components/repair-workspace.tsx:47-50`、`:188-194`、`:287-291`。
- **审查维度**：8 类型安全与契约表达；11 数据完整性（展示与证据绑定）。
- **置信度**：confirmed。
- **问题分析**：`diffFailures` 确实保存所有候选错误，但 `taskStatus` 只接收当前候选的 ID；切换到另一个正常读取、尚无回归的候选后，原候选再次参与 `some(verified)`。候选导航则始终给 `candidateVerdict` 传空错误，原候选仍显示绿色。
- **独立复现**：两个 committed 候选；仅候选 1 有 verified 回归，但读取其 diff 返回 SHA 不匹配。初始任务撤回通过；切到没有回归的候选 2 后，候选正文正确写“尚无回归结果”，任务标题和当前列表行却恢复“回归通过”。
- **修复方式**：根据当前 task ID + task SHA 构造所有已失败候选的集合；任务级结论排除集合内的每个候选；候选导航也读取各自错误。刷新/成功重读应仅清理对应 key，不能跨候选借用通过。
- **验证方式**：修复后运行新增独立用例，并扩展验证“另一个候选真的 verified 时仍可显示任务通过”，避免过度撤回。

### 批次 A：调用检查与修复 D1–D10/S1

| 原编号 | 复审结果 | 最新证据 / 最小修法 |
|---|---|---|
| D1 P1 | 已修 | `lib/tones.ts::repairSummary` 为记录通过使用 neutral；列表与 overview 共用；现有独立回归通过 |
| D2 P2 | 标签切换已修，多候选未修 | `diffFailures` 跨标签保存；剩余见 D2-M，不重复计数 |
| D3 P3 | 未修 | `evidence-editor.tsx:113` textarea onChange 仍直接使用规范化值；CRLF 回退编辑需按原文换行方式还原或只读 |
| D4 P3 | 未修 | `workbench.tsx:199,210,225-227` 超时/JSON解码/网络共用断网提示；分别处理 AbortError/HTTP不可解析响应 |
| D5 P3 | 未修 | `diff-viewer.tsx:27-32` 仍优先补丁头路径；`parse-diff.ts:47-61` 第二文件头仍计入增删。标题使用校验后的 fallbackPath，重复头作 note |
| D6 P3 | 未修 | `parse-diff.ts:94-103` UTF-16 边界仍可切开 emoji；按码点比较或扩展代理对边界 |
| D7 P3 | 已修 | `json-tools.ts:222` 现为显式 `"\uFEFF"` |
| D8 P3 | 未修 | `workbench.tsx:98-109` 守卫未排除同 URL；当前页导航不应触发离开确认 |
| D9 P3 | 已修 | `json-tools.ts:139` 在数字分支识别 `-Infinity` |
| D10 P3 | 部分修复 | D1/D2 标签用例已补；textarea fallback、恶意/多文件补丁、390px 草稿取消/离开未全部固化；新增本轮多候选反例 |
| S1 suspected | 不升级、不扣分 | `evidence-editor.tsx:65` 被动 effect replace 仍在；此前降速未复现，本轮无新丢字证据，不当确定缺陷 |

### 批次 B：分析 AN-01–AN-11

| 原编号 | 复审结果 | 最新证据 / 最小修法 |
|---|---|---|
| AN-01 P2 | 已修 | env.analysisAt 仅成功读取推进；console 以请求开始时间比较，429 保留旧时间；AN01 E2E通过 |
| AN-02 P2 | 已修 | 明确“用同一 ID 重新提交”，说明未送达会开始；404 不再显示已运行；放弃仅删除本地跟踪，E2E 无写请求 |
| AN-03 P3 | 未修 | `analysis-console.tsx:120-128` 只有选中 pending 任务才能清除；查看别的记录后按钮禁用却无 pending 原因。显示“查看待确认分析”或单独跟踪 pending 结束 |
| AN-04 P3 | 未修 | `analysis-console.tsx:66-76` 无效存储内容与禁用存储仍合并 catch；区分解析失败与访问失败，显式清理损坏条目 |
| AN-05 P3 | 未修 | `analysis-console.tsx:72` 恢复仍调用默认 push 选择；`analysis-history.tsx:61-69` 可覆盖深链。恢复只在无显式选择时 replace |
| AN-06 P3 | 未修 | `analysis-console.tsx:159-160` 429 一律说已有分析，503一律说连接中断；改为服务忙，按 HTTP/网络分别提示 |
| AN-07 P3 | 部分修复 | `analysis-console.tsx:104,116` recovery 已停止2秒轮询；但 `:109,204` 暂时429仍红色 alert。瞬时重试用中性状态 |
| AN-08 P3 | 未修 | `analysis-evidence.tsx:33-49` summary sha变化仍清空证据并重读；保持旧内容，按引用键缓存但不可丢 summary 关联校验 |
| AN-09 P3 | 未修 | `analysis-console.tsx:230` status节点条件插入；`execution-terminal.tsx:34` 状态无live容器。改常驻播报节点 |
| AN-10 P3 | 未修 | `lib/analyses.ts:15` 检查契约 vs目录仅检查契约；`analysis.css:847-855` 手机隐藏角色。统一名称并以消息前缀保留角色 |
| AN-11 P3 | 未修 | `analysis-detail.tsx:16-19` AnalysisCommand无调用者；start/stop未同步env，侧栏可滞后15s。去掉死代码并在确认结果后同步共享状态 |

## 4. 维度覆盖声明

| # | 维度 | 发现数 | 备注 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | 未新增写请求类型；重新提交已明确语义 |
| 2 | SOLID 与现代设计 | 0 | 定向复审不以风格扣分 |
| 3 | 并发、异步与资源安全 | 3 P3 | AN03/05/07；AN01关闭；S1无新证据 |
| 4 | 容错与防御性编程 | 3 P3 | D4/AN04/AN06 |
| 5 | 性能、伸缩性与计算效率 | 1 P3 | AN08 |
| 6 | 安全与数据合规 | 0 | UI反例响应mock，不外发个人数据 |
| 7 | 可观测性与运维友好度 | 2 P3 | AN09/10 |
| 8 | 类型安全与契约表达 | 1 P2 + 3 P3 | D2-M/D3/D5/D6；strict API验证未放宽 |
| 9 | 可测试性与死代码 | 2 P3 | D10/AN11 |
| 10 | 工程规范与一致性 | 1 P3 | D8 |
| 11 | 数据与事务完整性 | 同D2-M不重复扣分 | 仅UI当前判定绑定 |
| 12 | 依赖与供应链治理 | 0 | 本次修复未引依赖；未重做全依赖漏洞审计 |

## 5. 整改清单

| ID | 严重级 | 负责人 | 截止 | 状态 |
|---|---|---|---|---|
| D2-M | P2 | root 实现者 | UI-08收尾前 | closed，独立失败反例修复后通过 |
| D3/D4/D5/D6/D8/D10 | P3 | UI-08维护者 | 后续界面维护 | tracked，见本报告批次A |
| AN03–AN11 | P3 | UI-08维护者 | 后续界面维护 | tracked，AN07部分修复 |

## 6. 架构防腐与长效治理建议

1. 任务/候选的当前结论共用一个纯函数，输入全部证据撤回状态；增加多候选组合测试，避免组件各自推导。
2. 对 pending 请求单独建恢复状态对象（未知/未送达/运行中/终态/损坏），降低视图选择对任务状态的影响。
3. 将证据引用缓存和当前摘要关联校验分离；界面稳定展示已验证内容，同时显式表示当前验证进行中。

## 7. 审计声明

本报告仅复核两份UI报告的修复。首轮发现如实保留；后续修复追加复验记录，不擦去失败证据。不存在整产品生产可用性背书。没有使用模型调用或合成 UI 数据证明修复准确率；没有更改真实运行库、提交或推送代码。

### 追加复验：D2-M 已关闭

实现者 root 修改任务级判定为全候选失败集合，导航按各候选 key 显示。评审者未参与该生产修改。

- `tests/repairs.spec.ts tests/ui08-core-independent.spec.ts`：**`23 passed (15.3s)`**，包含原 22 项回归和新增失败反例。
- 再新增正对照：候选 1 差异被撤回，但候选 2 有真实形状的 verified comparison，任务仍允许通过。独立文件两项：**`2 passed (2.4s)`**。这些都是 mock 契约测试，不计真实模型任务。
- D2-M 的首轮失败保留，修后不再有未关闭 P0/P1/P2。报告中的 D2-M 位置是失败快照，当前源码摘要另外保存于 `artifacts/ui08-core-followup-final-sha256.json`。
- BOM 用例独立重跑仍超时，trace 精确定位 `product.spec.ts:86`：`<nextjs-portal>` 来自 `data-nextjs-dev-overlay` 拦截“文档”链接；未强制点击、未隐藏浮层，避免绕过真实问题。root 将切生产构建，届时重跑此项。
- 首轮得分 82 → D2-M 关闭后 85，剩余 15 项 P3 均在本报告跟踪；不是要求重新设计已确认的 UI。

### 追加生产模式复验

2026-10-15 root 完成 schema2 协调部署后，生产3010重新执行 product 全7项和 repairs/独立反例，共 **32 passed (29.3s)**。BOM 导航用例 1.8s通过（生产首轮也已通过）；开发浮层造成的两次失败不删除。schema2首次运行仅因旧角色名定位断言失败，测试更新为 task 链接+案例文字后整组通过，见 `UI-08-schema2-integration-review.md`。本报告针对已审计UI范围的剩余动态门禁解除，结论 Pass；整项目真实模型和后端验收仍以各自报告为准。
