# P1-01 B3 网页操作与事件 API 独立评审

- **审计对象**：相对 `9195df9` 的 B3 网页执行控制、前端契约、代理路由、事件 API 增量；不含另行评审的常驻服务和主库迁移。
- **审计版本**：`9195df9` 之后的工作树；14个生产文件 SHA-256 见末尾冻结清单。
- **技术栈**：Next.js / React / TypeScript / Zod，FastAPI / SQLAlchemy / SQLite。
- **业务场景**：General SaaS（本地可信单用户）。
- **审查严苛度**：Mission-Critical。
- **审计时间**：2026-10-16。
- **独立评审者**：`/root/b3_web_review`；只修改独立测试与本报告，不修改生产代码。
- **依据**：AGENTS、01、03、34、35、39；`auditing-enterprise-code-quality` 十二维审计与 `frontend-design` 界面审查。

## 1. 代码质量评估卡

状态：`in_review → done`。**综合质量得分：100 / 100；本子批结论：Pass**。四处独立确认发现均由实现者修复；完整axe回归新增的链接颜色区分问题也已修复并增量复审。6项 Python 独立测试、6项生产构建 Chrome 独立测试通过；最终组合回归36 passed / 1 skipped。

| P0 阻断 | P1 严重 | P2 主要 | P3 次要 |
| :---: | :---: | :---: | :---: |
| 0 | 0 未关闭 | 0 未关闭 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: no unresolved findings -> 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: Pass — 五项修复均已复核，审计范围无未关闭P0/P1/P2。
NOT ASSESSED: none within the scoped 14 production files
```

范围之外：真实模型修复效果、真实 Docker 完整修复与人工审批属于 B5/B4；常驻服务和迁移属于独立部署评审。本报告不替代上述门禁。本次增量已核对能力状态、模块说明、迭代历史、文档目录和首页；主服务切换由部署独立报告验收。

## 2. 生产事故风险推演

### 场景一：历史通过被当成当前有效

候选原来通过，之后源文件或 Oracle 变化。原详情正确撤回通过，但新增控制台直接展示 `receipt.task.outcome=candidate_verified`，会在同页出现“结果已过期”和“回归通过”。影响单次用户修复决策；由独立 UI 检查发现。

修复：原始账本通过仅显示“候选曾通过，需核对当前回归”，最终判定继续使用原有核验详情。

### 场景二：损坏的持久意图被当作不存在

sessionStorage 已有空字符串时，原 `if (raw)` 跳过解析，用户可以创建新请求并覆盖原损坏记录，违反未知请求不得丢弃的约束。影响单标签页的提交恢复。

修复：`raw !== null` 后统一严格解析；空字符串和其他损坏数据阻止提交，保留原值。

## 3. 详细审计明细

### P0 — 阻断性缺陷

none。

### P1 — 严重缺陷

#### B3-W01：历史原始 outcome 不得呈现为当前回归通过 `[confirmed, fixed]`

- 位置：`frontend/components/repairs/run-controls.tsx:153`，控制台 heading。
- 维度：架构与边界、数据语义。
- 原因和故障路径见场景一。
- 最小修复：对 `candidate_verified` 单独使用历史措辞；不改变原始持久结果。
- 验证：独立浏览器用例 `recorded candidate pass is not presented as current verification`；现有详情核验路径保留。

#### B3-W03：空字符串 pending 必须作为损坏记录拒绝 `[confirmed, fixed]`

- 位置：`frontend/components/repairs/run-controls.tsx:49–56`，初始化 sessionStorage。
- 维度：容错、事务恢复。
- 最小修复：`if (raw)` → `if (raw !== null)`。
- 验证：独立浏览器用例 `an empty stored value is corruption and must not be overwritten`。

### P2 — 主要缺陷

#### B3-W02：迟到响应可倒退已确认状态 `[confirmed, fixed]`

- 位置：`frontend/lib/repair-runs.ts:80–83` / `frontend/components/repairs/run-controls.tsx:77,116,127`，receipt 合并与三个写入点。
- 维度：并发、可观测性。
- 路径：取消 POST 已确认，但更早的 GET 返回 `cancel_requested=false`；或先 GET 到 finished，再收到初始202的 ready。原代码直接 setReceipt，页面恢复旧状态。
- 修复：`mergeReceipt` 同任务 revision 取较新值，取消标志 OR、active 标志 AND；事件 revision 同样不倒退。
- 验证：独立延迟 GET 浏览器用例与迟到202合并用例。

#### B3-W04：T04 事件标签错误 `[confirmed, fixed]`

- 位置：`frontend/components/repairs/run-controls.tsx:17`，tools.T04。
- 维度：可观测性与产品语义。
- 实际映射：`repair_runtime/tools.py` 中 `check_contract → T04`；原“查询指标口径”错误。
- 修复：改为“检查调用契约”；其他 T01–T07 映射核对一致。

#### B3-W05：环境链接不能只靠颜色与正文区分 `[confirmed, fixed]`

- 位置：`frontend/app/styles/repairs.css:718`，`.rp-launch p .link`。
- 维度：可访问性、产品可发现性。
- 证据：实现者扩展执行原修复页全页axe回归，8个布局案例触发仅颜色区分链接问题。
- 最小修复：只为操作区正文内链接增加下划线与3px偏移；未改变按钮/焦点/全局主题。
- 复核：检查最终CSS增量；最终 `b3-final-browser.log` 中8个浅深/移动布局axe案例全部通过，独立6项浏览器同次复跑也通过。

### P3 — 次要缺陷

none。

## 4. 维度覆盖声明

| # | 维度 | 未关闭发现 | 备注 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | UI 不产生权限/预算，receipt 与当前候选核验分离 |
| 2 | SOLID 与现代设计 | 0 | API契约、执行控件、原diff阅读各自维护 |
| 3 | 并发、异步与资源安全 | 0 | 写锁、AbortSignal、单调合并、共享读取槽 |
| 4 | 容错与防御性编程 | 0 | pending未知保留、损坏存储阻止写、无自动POST |
| 5 | 性能、伸缩性与计算效率 | 0 | 顺序poll、隐藏标签暂停、有界重试、256事件上限 |
| 6 | 安全与数据合规 | 0 | 严格DTO、固定案例、事件白名单、无原始参数或claim |
| 7 | 可观测性与运维友好度 | 0 | 状态与用量可读；T04文案已修复 |
| 8 | 类型安全与契约表达 | 0 | Zod绑定request/task/case/mode和事件连续序列 |
| 9 | 可测试性与死代码 | 0 | 独立临时库与故障注入；浏览器网络延迟反例 |
| 10 | 工程规范与一致性 | 0 | 沿用UI-08色彩、按钮、表单、控制台，无新装饰语言 |
| 11 | 数据与事务完整性 | 0 | _saved/_read完整审计后同事务投影，不修改账本 |
| 12 | 依赖与供应链治理 | 0 | 此子批未新增依赖 |

## 5. 整改清单

| ID | 严重级 | 负责人 | 截止 | 状态 |
|---|---|---|---|---|
| B3-W01 | P1 | `/root` | B3验收前 | closed，独立浏览器复审通过 |
| B3-W02 | P2 | `/root` | B3验收前 | closed，独立浏览器复审通过 |
| B3-W03 | P1 | `/root` | B3验收前 | closed，独立浏览器复审通过 |
| B3-W04 | P2 | `/root` | B3验收前 | closed，映射复核通过 |
| B3-W05 | P2 | `/root` | B3验收前 | closed，8项axe布局复跑通过 |

## 6. 架构防腐与长效治理建议

1. 保留延迟GET/POST独立回归；每次扩展状态字段明确是否单调，避免重新引入响应顺序问题。成本为现有自动化用例维护。
2. 继续区分“账本记录结果”和“当前证据核验”；新增任何通过徽标都必须说明依据。成本为新增显示字段的评审检查。
3. 白名单事件投影必须先执行完整账本审计；保留重签语义篡改测试，避免以后只验证哈希。成本为六项现有独立测试。

## 7. 审计声明与证据

已执行：

```text
uv run --frozen pytest tests/test_b3_web_review.py -q
...... [100%]
uv run --frozen ruff check tests/test_b3_web_review.py
All checks passed!
npx tsc --noEmit
exit 0
```

六项 Python 独立测试：白名单完整只读、缺失事件、哈希损坏、重签后的语义篡改、共享读取容量、HTTP参数/no-store。使用真实临时 SQLite 和确定性模型替身；无真实模型调用、无真实容器、无主库读写。

浏览器用例文件：`frontend/tests/b3-web-review.spec.ts`。执行：

```text
AWB_API_PORT=8040 AWB_STATE_DIR=<repo>/artifacts/b3-review-state PLAYWRIGHT_CHANNEL=chrome npx playwright test tests/b3-web-review.spec.ts
6 passed (7.1s)
```

原始日志：`artifacts/b3-web-independent.log` / `artifacts/b3-python-independent.log`（忽略产物，不入库）。6项浏览器测试包括历史通过中性化、迟到 GET 不撤销取消、空串存储损坏、404刷新只读且保留ID、迟到202不撤销终态、390/1440两种宽度和浅/深主题键盘操作。

截图：`artifacts/b3-review-{390,1440}-{light,dark}.png`。人工检查390深色与1440浅色截图：主操作可见，焦点清晰、无横向溢出，预算折叠，事件沿用既有220px滚动区；新增区域没有暴露长ID/hash。截图中的详情404来自独立mock刻意不提供候选历史，不能作为真实运行失败。最终构建的截图已显示“网页可用”，模块说明已同步网页执行；环境/活动修复链接有明确下划线，运行状态与停止按钮仍清晰。

无风险豁免。此报告只覆盖上述 B3 子批；不替代部署子批评审或B5真实效果验收。

### 最终增量复审（2026-10-16）

- 原9文件中除CSS两行链接修复外，其余8个生产文件SHA均未变化。
- 新增核对5个UI文案/入口文件：`capabilities.ts`、`modules.ts`、`milestones.ts`、`documentation.ts`、`app/page.tsx`。能力改为网页可用；两个内置案例与开始/停止表述准确，保留人工接受/下载尚未开放、隔离副本不写回的边界；历史更新记录未覆盖。
- 核对docs39交付记录：测试分组不相加，替身与真实模型/容器效果明确分开，B4/B5与父任务未提前关闭。文档的最后状态推进由父任务完成全部门禁后填写。
- 阅读最终组合日志 `artifacts/b3-final-browser.log`：**36 passed / 1 skipped (21.4s)**；包含本评审6项反例与原页面8项完整axe布局。跳过项是显式真实案例API门禁，未计通过。
- 人工重新检查最终390深色截图：网页可用与模块说明已更新，链接下划线可见，焦点与无溢出保持。生产构建日志 `artifacts/b3-build-final.log` 正常完成。
- 本子批仍为 **Pass**，无未关闭Defect P0/P1/P2，无风险豁免。

### 已审计生产文件 SHA-256

以下文件之后发生修改需增量复审：

| 文件 | SHA-256 |
|---|---|
| `frontend/lib/repair-runs.ts` | `6a09614a94e2ba1507f657c85aa3cfef397e9e0abaa6f9ca7931c5f1b6a13938` |
| `frontend/components/repairs/run-controls.tsx` | `d67465ceec6d6971dcc2711446198a1df905648817d956bef602a4de5865a176` |
| `frontend/components/repair-workspace.tsx` | `cf0177095d4b9b8df2e6682c050e2296b8e69fd64b165eaba054342382fae5dd` |
| `frontend/next.config.ts` | `d901f6d4d4c1da69b016fab7c41b968005f1338eb4218b378e7aa8d8e8183269` |
| `frontend/lib/repairs.ts` | `c309b617b166141958e16567d04836236cd42e15b15cb6883f8a5b32bada3a80` |
| `frontend/app/styles/repairs.css` | `dcbef3e8c0db9b9e0384e68308f07e2e4e08982f553080cc468807f42a3787d2` |
| `src/agent_workbench/web_repairs/api.py` | `de451f9efe67d6f68fee7944c6046c0c74369d4bf6fc1391f2d5435ba5940d53` |
| `src/agent_workbench/web_repairs/service.py` | `81bcc8aef9cacd686be0d8f1abec203a188a92077620fd4a31e777b44b5e1992` |
| `src/agent_workbench/web_repairs/store.py` | `4bc68ef7563d829842cdc199ab7c10628025848896a08b94a72302372f2fc835` |
| `frontend/lib/capabilities.ts` | `0dba7edfcbeca8ab3e945374ff3a6d33769f7e9342e16d8cc963e3e726ddb436` |
| `frontend/lib/modules.ts` | `f84dc1db7362db95b27ecd49ff5f2980da06ede06ebef39c067b0c541a23ecb3` |
| `frontend/lib/milestones.ts` | `6a2405a23c5525aa2239ded56909345bba5c1b2ea566d63bec2adf553e941a2d` |
| `frontend/lib/documentation.ts` | `7d1f039455655b8ff5fb509a3e5d75ceba007551724c29623fc0ced9dcfb6a9b` |
| `frontend/app/page.tsx` | `ad6d1bf18db92a40c1f59a086ea39f1bc866ad870a50ccb8631bc4aab1ed352d` |
