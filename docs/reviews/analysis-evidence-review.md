# 企业代码质量审计报告：可读证据与复现结论

- **审计对象**：可读证据只读 API、前端证据阅读器；追加独立小批次复现结论说明。
- **审计版本**：2026-10-14 工作树，具体 SHA-256 见文末；实施者 root / evidence-reader，独立评审者 evidence_review_resume。
- **技术栈**：Python / FastAPI / Pydantic / SQLite、React / Next.js / TypeScript / Zod / Playwright。
- **业务场景**：General SaaS（当前部署边界为可信本地单用户）。
- **审查严苛度**：Mission-Critical。
- **审计时间**：2026-10-14，Asia/Shanghai。

## 1. 代码质量评估卡

- **综合质量得分**：**100 / 100**，限本次实际评审范围，非整个产品质量分。
- **上线评估结论**：**Pass**。初审 1 项 Defect P2 已由实现者修复，独立键盘反例复审通过。
- **审计范围**：批次 A 为 `analysis_store/evidence.py`、`api.py` 的 evidence GET 增量、`analysis-evidence.ts`、`analysis-evidence.tsx`、`analysis-detail.tsx` 证据接入和 `.evidence-*` CSS；批次 B 为 `reproduction-result.ts`、`run-report.tsx` 和 `run-detail.tsx` 的复现说明增量及 CSS。两个批次各低于 2000 行。未将这些文件内已有全产品功能重新签收。
- **未评估项**：范围内 none。真实模型效果、网页启动/停止服务、主库升级和生产构建发布均在范围外，不能依据本报告标记它们完成。

| P0 阻断 | P1 严重 | P2 主要 | P3 次要 |
|---|---|---|---|
| 0 | 0 | 0 未关闭（1 已修复） | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 当前未关闭缺陷 0 → 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: Pass — 范围内无未关闭 P0/P1/P2
NOT ASSESSED: none within scope
```

### 本轮实际验证

1. `uv run --frozen pytest tests/test_analysis_evidence.py tests/test_analysis_evidence_review.py -q`：14 项通过。使用临时 SQLite、真实资源核验与 FastAPI TestClient；未写主库、未调用模型/Docker。
2. `PW_PORT=3012 PLAYWRIGHT_CHANNEL=chrome npx playwright test tests/evidence-independent.spec.ts --output=../artifacts/evidence-review-final`：`8 passed (9.9s)`。独立键盘回焦、390px 浅/深源码与 schema 及不可用内容展示、5 种错配拒绝。6 次证据区域 axe 零违规，无页面横向溢出。HTTP 由 mock 提供，不能算真实网页后端接通。
3. `PW_PORT=3012 PLAYWRIGHT_CHANNEL=chrome npx playwright test tests/reproduction-result-independent.spec.ts tests/runs.spec.ts -g '独立复现判定|复现结论区分' --output=../artifacts/reproduction-review`：`15 passed (6.2s)`，包括新增 9 项独立判定反例和既有 6 项页面用例。
4. Ruff：`All checks passed!`；mypy：`Success: no issues found in 2 source files`（evidence.py/api.py）；`npm run typecheck` 退出 0。
5. 截图保存在忽略产物 `artifacts/evidence-review-{light,dark}-{source,contract,unavailable}.png`；人工实际查看浅色 contract 与深色 source，未发现遮挡、整页横向滚动或长哈希主导页面。完整 schema 在窄屏改为上下排列，技术摘要默认折叠。

## 2. 生产事故风险推演

无 P0/P1。已验证的防线：

- 保存引用或资源版本不同：后端明确返回 unavailable，前端 task ID / summary SHA / 引用 ID 与 SHA / 数量或范围不一致时拒绝展示正文，不能把新版资源解释为历史证据。
- 用户退出证据 GET：已启动的核验 worker 继续持有 checker 槽，第二个请求返回 429；关闭等待 worker，不因 HTTP 取消提前释放并发上限。
- 预设 tool_error 遇到执行环境失败或不完整报告：不显示“预设工具故障已复现”。报告实际调用状态仍保留失败，不改写数据库 verdict。

## 3. 详细审计明细

### P0 — 阻断性缺陷

none。

### P1 — 严重缺陷

none。

### P2 — 主要缺陷

#### EVID-P2-01：关闭证据阅读器后键盘焦点丢失（已修复）

- **位置**：`frontend/components/analysis-evidence.tsx`，原 EvidenceLibrary 关闭处理仅 `context.select(null)`；复审修复位于 EvidenceProvider 的 opener/select 与 EvidenceReferences 的事件触发处。
- **审查维度**：4 容错/交互状态、9 可测试性、10 既定键盘操作要求。
- **置信度**：confirmed。
- **失败路径**：键盘 Enter 打开资料，标题 focus 成功；Tab 到收起按钮，再 Enter 移除当前焦点节点，未返回原资料入口。初审测试 `独立：键盘打开和收起证据后回到原入口` 在 `toBeFocused()` 失败；其余两个主题用例通过。
- **修法**：实现者以 ref 保存触发 HTMLElement，关闭后恢复焦点；节点已移除时回退当前资料列表入口。不再只删除面板。
- **复验**：同一独立反例通过，完整 8 项用例通过。不是通过删除或放宽断言消除失败。

### P3 — 次要缺陷

none。

## 4. 维度覆盖声明

| # | 维度 | 发现数 | 备注 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | API 只读摘要，公开 fixture 重建与导入/历史来源隔离；复现说明不改变执行判定 |
| 2 | SOLID 与现代设计 | 0 | 解析、展示、领域说明分离；未重复写入运行逻辑 |
| 3 | 并发、异步与资源安全 | 0 | gate + shield worker；断开不提前放槽；前端请求 AbortController |
| 4 | 容错与防御性编程 | 1 已修复 | 关闭回焦；错误、旧资源与缺证据显式降级 |
| 5 | 性能、伸缩性与计算效率 | 0 | 固定两个公开资源、bounded checker、32 引用、单执行槽；不是共享多租户服务 |
| 6 | 安全与数据合规 | 0 | no-follow / 完整文件 SHA / 固定 107–110 行；不返回参数值、凭据、私有文件或异常正文 |
| 7 | 可观测性与运维友好度 | 0 | 503/429 静态代码、可重试提示、未知内容可辨识 |
| 8 | 类型安全与契约表达 | 0 | Pydantic / 严格 Zod，前端验证 kind 与内容一致，严格归属核验 |
| 9 | 可测试性与死代码 | 0 未关闭 | 新增键盘和错配反例；后端临时真实库，前端 mock 范围明示 |
| 10 | 工程规范与一致性 | 0 未关闭 | ID/摘要收进次级信息，浅深主题变量，已修复焦点规则 |
| 11 | 数据与事务完整性 | 0 | 只读，不新增迁移/事务；损坏事件摘要拒绝生成可读内容 |
| 12 | 依赖与供应链治理 | 不适用新增依赖 | 本批未加依赖/改锁；不宣称重新审计整个供应链 |

## 5. 整改清单

| ID | 严重级 | 负责人 | 截止 | 状态 |
|---|---|---|---|---|
| EVID-P2-01 | P2 | root 实现者 | 本批交付前 | 已修复并独立复审 |

未施加风险豁免。

## 6. 架构防腐与长效治理建议

1. 保留本次 task/ref/hash/range 错配测试作为阅读器回归门禁；后续支持新证据类型时明确保存与展示契约，不能以任意路径重新读取代替历史证据。
2. 复现结论继续与调用 verdict 分离，新的故障类型须添加精确证据断言和环境异常反例；不把选择了某场景当作成功复现。
3. 浮层/展开阅读器增加键盘进入与关闭回焦测试；本次 1 条反例即防住实际可达的交互回退。

## 7. 审计声明

本报告只签收上述两个小批次。可读证据当前只支持固定公开合成案例的精确哈希重建；不能声称任意历史 trace 都已有正文。复现页中的“打开诊断分析”明确进入独立案例，未伪装成自动分析本条运行。部署后重载服务和真实路由联调仍由交付阶段完成。

审计源码 SHA-256（CSS 仅评审证据与复现说明选择器，整文件 hash 用于定位快照）：

| 文件 | SHA-256 |
|---|---|
| src/agent_workbench/analysis_store/evidence.py | f80d6a39af36dcbef5bbcad75a9e85dadc216769902c7c28226a0c9d95ee628f |
| src/agent_workbench/analysis_store/api.py | 01050d337e643418234bfe1b83290a2060cc4f9c34aa438a4d15b7a8e9e4937a |
| frontend/lib/analysis-evidence.ts | c53d8fdb3ef52fb537a0d7438c884802483009bb23f9395c7ef22adc3d4d9bc0 |
| frontend/components/analysis-evidence.tsx | d2e885ffa34508f7de479bc148bb93a558e7a8920d4bf478eeb255e7fedb807c |
| frontend/components/analysis-detail.tsx | 103789c1794076a88ba63f742b8f16ed6e446c1fe4f3ec9b1cd2c85dd3020f28 |
| frontend/app/globals.css | 9d27fd5e5768030c7e4bce6e05292cabd131285e7f1fcebef4e20beb5323208a |
| frontend/lib/reproduction-result.ts | aeb8695b9aa65859790c76a1cf2984c01682e6116d0c37fb84ac463034a33bc5 |
| frontend/components/run-report.tsx | 83fd1047e3814aa3af89ff69519939a3d33e9df6747c725594f40c5b7e6799be |
| frontend/components/run-detail.tsx | a8f200bf3dc6a7ec0af02f98419ec208b8e5407ff5bf2c482a1f71525a4d3a16 |

后续修改仅需对变化的评审范围增量复审，不能把此报告沿用为未评审功能的证据。

## 8. 后续增量复审：证据 GET 的 429 有界重查

2026-10-14。真实开发模式联调暴露 StrictMode 的首个 effect 请求取消后，后端仍正确持有核验槽；紧接的第二个 GET 会收到 429。实现者在 `EvidenceProvider` 增加仅针对 `RunApiError.status === 429` 的最多 5 次、每次间隔 1 秒重查。旧请求清理同时 abort 请求和 clearTimeout，其他错误立即展示，不改变 ID/hash/源码范围验证。

- 增量结论：**Pass**，无新 Defect P0/P1/P2。
- 独立新增 `frontend/tests/evidence-independent.spec.ts` 的 4 项 `限流重查`：429 后自动恢复；持续 429 达到上限后停止并显示错误；503 不自动重查；Next 客户端页面导航离开后不再发送重查。最后一项通过站内 Link 导航验证，未以整页刷新销毁 JS 代替 effect 清理。
- 命令：`PW_PORT=3012 PLAYWRIGHT_CHANNEL=chrome npx playwright test tests/evidence-independent.spec.ts -g '限流重查' --output=../artifacts/evidence-review-429`，结果 **`4 passed (15.4s)`**。接口 mock，证明客户端调度边界；真实 API 联调结果由实施者在交付报告另记。
- `npm run typecheck` 退出 0。
- 当前 `frontend/components/analysis-evidence.tsx` SHA-256 为 **`9fe2f91686effefdc700887b54428c29ea55ec91d6c7f1e2d13237919ede5b19`**，取代第 7 节该文件旧哈希。其余本批证据读写协议与归属校验未修改。
