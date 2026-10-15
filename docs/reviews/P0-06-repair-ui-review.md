# P0-06 候选与回归前端独立评审

- **审计对象**：候选修复、回归验证只读页面；13 个冻结文件，清单见下。
- **实现者**：`/root/final_review`；**独立评审者**：`/root/web_analysis_service`。评审者没有修改被评审生产代码。
- **审计版本**：`p006-ui` sandbox 工作树，SHA-256 按本文锁定。
- **技术栈**：Next.js / React / TypeScript / Zod，Playwright + axe。
- **业务场景 / 严苛度**：General SaaS / Mission-Critical。
- **审计日期**：2026-10-14。
- **方法**：frontend-design、企业代码质量审计，以及 [Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md) 的可访问性、状态、主题与交互检查。

## 1. 代码质量评估卡

- **综合质量得分**：100 / 100，表示本批已核范围内无未关闭发现，不是全产品质量评分。
- **上线评估结论**：**Pass**。允许按冻结清单集成；主前端仍须构建、重启并检查入口。此结论不替代 P0-06 模型效果及整体交付验收。
- **审计范围**：13 文件；约 1,600 行新增核心页面、契约及测试，加少量路由、局部 CSS 和进度文案改动。未重审未改的全站 CSS。
- **未评估项**：本批范围内 none。模型推理、Docker 恢复、数据库实现由各自批次评审，本报告只验证其公开只读契约与页面呈现。

| 未关闭 Defect P0 | 未关闭 Defect P1 | 未关闭 Defect P2 | 未关闭 Defect P3 |
| --- | --- | --- | --- |
| 0 | 0 | 0 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 无未关闭发现 → 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: Pass
NOT ASSESSED: none within the scoped UI changes
```

### 独立实跑证据

1. `npm run typecheck`：`tsc --noEmit`，exit 0；在 sandbox/frontend 执行。
2. `node artifacts/p006-ui-review/review.cjs`：最终 **15 pass、1 not_applicable**。
   - 8 个真实只读 API 组合：候选差异 / 逐项回归 × 390 / 1440 × 浅色 / 深色；实际差异与 API 原文逐字比对、8 次 axe 主内容检查、页面无横向溢出、可见键盘焦点及 Enter 展开、无 API 写请求。
   - 7 个合成边界/交互探针：404、超过 512 KiB、`accepted=true`、跨任务详情、未知用量与费用、候选 2 跨页定位、迟到详情不得覆盖新任务。
   - 最后一项“真实历史失效”在新 state 没有失效记录，明确记 `not_applicable`，不计通过。
3. 新 state 之前的独立一轮：**16 pass**，包括 8 个合成主题/布局组合、上述边界及真实历史失效的负向验证；结果留在 `synthetic-and-invalidated-results.json`。这些结果与最终轮次有重叠，不能相加宣传测试数量。
4. 实现者提供的 18 个 UI/mock/旧状态断言及 build 通过结果作为补充；不是上述独立测试的替代。

真实访问范围：`127.0.0.1:8035` 的明确授权临时库只读 API，经浏览器路由转发 GET；没有访问主库、没有调用网关、没有更改模型产物。预览端口 3018。

独立证据：`artifacts/p006-ui-review/{review.cjs,results.json,synthetic-and-invalidated-results.json,reviewed-files.json}`，以及 8 张主题/尺寸截图和 `real-invalidated.png`。这些是本地验收产物，不应公开上传原始运行资料。

### 版本失效窗口的处理

验收中，旧 API 的两条历史 `candidate_verified` 记录变成 `verification=unavailable`。协调者确认集成 recovery CLI 改变了 oracle 安全文件指纹；本次没有弱化检查或改写历史。独立浏览器确认旧记录撤销当前“冻结规则通过”、隐藏规则表并显示版本失效提示。

随后在冻结版本上重新运行模型并重启临时 API，新记录的当前核验通过；最终 8 个真实正向主题/尺寸组合全部通过。旧数据失效是正确的保守行为，不是 UI 缺陷。

## 2. 生产事故风险推演

未关闭 P0/P1：none。

已实证的主要防线：

- 先选择任务 A、随后选择 B，A 的迟到详情被取消并忽略；页面维持 B 的标识与结果。
- 服务端返回历史通过而当前版本失效时，页面不拿保存时结果冒充当前通过。
- 响应为 404、超限、跨任务或包含非法接受状态时，不显示差异/通过结论，不暴露服务端原始正文。

## 3. 详细审计明细

### Defect P0 / P1

none。

### Defect P2：已修复并复审关闭

#### UI-01：候选 2 跨页时丢失选择上下文

- **位置**：`frontend/components/repair-workspace.tsx:135–151,189–208`。
- **维度 / 置信度**：并发状态与用户交互，confirmed。
- **原问题**：跨“修改内容 / 回归验证”的链接只带任务 ID，目标页默认首候选，用户选候选 2 后会被切回候选 1。
- **修复**：链接携带 `candidate`；按当前任务候选集合严格匹配；选择同步 URL；陌生候选明确提示回退；点击当前候选不清空既有差异。
- **复审**：独立两候选数据中选第 2 项，跨到回归页后仍为第 2 项且对应核验结论正确；作者额外双向导航与陌生候选测试通过。

#### UI-02：能力目录仍称隔离候选未实现

- **位置**：`frontend/lib/capabilities.ts:16,22`。
- **维度 / 置信度**：工程一致性，confirmed。
- **原问题**：任务/诊断页面的下一步文案会让用户误以为所有候选应用仍待开发，与新增 CLI 隔离候选和网页阅读不一致。
- **修复**：明确固定审核案例可通过 CLI 生成隔离候选并在页面核对；网页发起修复与审批后续实现；诊断建议不自动应用。
- **复审**：按最终 SHA 读取源文件并核对接口权限。两句文案在最终预览 build 后更新；主项目集成构建需包含这两句，未将旧构建当成已经显示新文案。

#### UI-03：更新当前里程碑时覆盖已有开发记录

- **位置**：`frontend/lib/milestones.ts:18–22`。
- **维度 / 置信度**：历史完整性，confirmed。
- **原问题**：新增 CLI/网页接入条目曾替换原 README 完善记录。
- **修复**：保留 README 条目，另追加本轮接入；既有完成里程碑保留。
- **复审**：最终清单与源文件一致；未将 P0-06 写成完成或暗示已有普遍修复率。

### Defect P3

none。

### UI 与阅读体验

- **信息层级**：任务选择器、候选切换、当前结论、实际差异/逐条规则依次排列。没有将长 UUID/SHA 当主内容，技术标识与预算默认折叠。
- **差异**：真实 unified diff 带上下文与增删行，文本方式渲染；能看清修复把字符串计数改回数值，而非只看到任务成功状态。
- **回归**：原错误与正常路径分别呈现，基线/候选逐行对齐；手机上下堆叠，桌面并排。状态有文字和勾号，不只靠红绿色。
- **边界说明**：候选通过仍明确未接受、未写回项目；费用显示未知，未结算预留不冒充实际消耗。
- **动效与交互**：使用短状态淡入并尊重 reduced-motion；原生选择器和按钮可键盘操作，焦点可见。八组实际截图已检查，未发现裁切或主体横向滚动。
- **操作边界**：本批是只读审阅；没有伪造“应用/执行/接受”按钮。如何生成记录放在可展开说明中，有实际 CLI 命令和站内文档入口。

## 4. 维度覆盖声明

| # | 维度 | 未关闭发现 | 依据 |
| --- | --- | --- | --- |
| 1 | 架构与边界 | 0 | DTO、加载逻辑、页面分离；GET-only，不接收网页任意命令 |
| 2 | SOLID 与现代设计 | 0 | 候选内容、规则表、任务选择职责可辨认；无新增泛化平台 |
| 3 | 并发、异步与资源安全 | 0 | AbortController 与身份再校验；独立迟到详情/候选切换验证 |
| 4 | 容错与防御性编程 | 0 | 404、失效、格式错配、超限有明确错误与刷新入口 |
| 5 | 性能与计算效率 | 0 | 最多 50 任务、2 候选、4 槽位、8 规则；响应 512 KiB 硬限制 |
| 6 | 安全与数据合规 | 0 | 无 raw HTML；错误正文不回显；无写请求或浏览器模型密钥 |
| 7 | 可观测性与运维友好度 | 0 | 当前核验/保存时结论区分，未知费用与预算可展开核查 |
| 8 | 类型安全与契约表达 | 0 | strictObject、关联与必要通过条件校验；独立 TS 通过 |
| 9 | 可测试性 | 0 | 页面路由注入可做反例，亦用真实 API 逐字比较差异 |
| 10 | 工程规范与一致性 | 0 | 能力目录与真实入口同步，站内文档链接，主题 token 复用 |
| 11 | 数据与事务完整性 | 0 | 当前读取不得覆盖历史；页面无写事务；任务/候选/快照绑定 |
| 12 | 依赖与供应链治理 | 0 | 未增加 package/lock 依赖；使用现有锁定工具链 |

## 5. 整改清单

| ID | 严重级 | 负责人 | 截止 | 状态 |
| --- | --- | --- | --- | --- |
| UI-01 | Defect P2 | `/root/final_review` | 集成前 | closed |
| UI-02 | Defect P2 | `/root/final_review` | 集成前 | closed |
| UI-03 | Defect P2 | `/root/final_review` | 集成前 | closed |

无风险豁免或延期项。

## 6. 架构防腐与长效治理建议

1. 保留两候选跨页与迟到详情测试，新增候选选择/筛选时一起运行；成本为既有浏览器小门禁，避免视图错配。
2. 固定实验代码后再运行最终真实模型验收；oracle 安全文件变化应使历史结果失效并重测，不能为演示修改核验条件。
3. 能力和开发记录更新时检查“已有历史条目保留”及“CLI/网页权限不同”两点；无需新建平行状态来源。

## 7. 审计声明与冻结清单

本报告只对以下内容 SHA 生效。集成可作路径映射，不得整目录覆盖其他 agent 的改动。之后功能/契约变化需增量复审；纯状态关闭或测试证据补充应与实际验收一致。

| frontend 相对路径 | SHA-256 |
| --- | --- |
| `lib/repairs.ts` | `9a69bb9e42777dc6766b86e8b45b766e60896bce5fb0f40aebf70ebfdafd34d3` |
| `components/repair-workspace.tsx` | `081dc464bf5439bd8114c5f63cc74e9443e9c8851b9de8ac7cf30532387411fa` |
| `app/workspace/[section]/page.tsx` | `9a568c3812844fd618198630d86d158e4d748908d57184c371e8e3f866ef9b1d` |
| `app/globals.css` | `a7825136225ea8029d141dc6e4d2efdb13798d7cd6b67eac43ac9ea0c6506fe0` |
| `next.config.ts` | `6dcb4cfdb92a5e10abccc04b485cc7e2f75d42f71f9ddcc7dcea4e84eec99dce` |
| `lib/modules.ts` | `694b69d966e466e272a724a06e6eea5ff7918f2989a9243cb0e45dcd2fec7775` |
| `lib/capabilities.ts` | `d4e694b026076e30e922bc3958ee9895314424b43fca792025d7255cbaac9611` |
| `lib/milestones.ts` | `aa6efbe2b085dd08940e10c3a92c9aac039c69cea26449123811de58e06cc98f` |
| `tests/repairs.spec.ts` | `50e5652416f6208b40ed00ecd995793ac8baf6be48a3b9579e4acd14aa49a153` |
| `playwright.repairs.config.ts` | `fbe3d9334425c015bc9a811a2c253fde4b6a7a03d47613131787b89e74857419` |
| `tests/repairs-live.spec.ts` | `8f2c9a74cff2cdf98327f131abe679391ba5a172040349a5fb73fdc7106226b6` |
| `tests/product.spec.ts` | `4a41f0cc62fef096b94c5f528a8d89ff00e69ac23d397e55ea44bbaf6935bb18` |
| `tests/progress.spec.ts` | `cdd54252c0d63bee1d771c67b279075c49a27e79af97195bfa0c428ee03642ee` |

未评估的本批实质范围：none。无豁免。没有将只读页面交付解释为网页修复执行、人工接受或任意外部项目支持。
