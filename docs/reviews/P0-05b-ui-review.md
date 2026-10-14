# P0-05b B4 前端独立代码质量审计

- 审计对象：分析记录页、只读 API 客户端、运行关联选择、协作目录 v2、能力/历史/文档文案及对应测试。
- 审计版本：879bf6a 基线上的工作树增量；冻结文件见 [SHA 清单](P0-05b-ui-snapshot.sha256)。
- 技术栈：Next.js、React、TypeScript、Zod、Playwright、真实 FastAPI/SQLite。
- 场景：General SaaS；严苛度：Mission-Critical。
- 时间：2026-10-14；独立评审者 final_review 未参与实现，仅新增独立验收测试与报告。

## 1. 代码质量评估卡

**Pass，100/100。** 仅 B4 前端范围通过；不以此替代 A14 真实模型及 B3 运行时验收。20 个冻结文件、约 460 行净增量，未评估项：本批范围内 none。

| Defect P0 | Defect P1 | Defect P2 | Defect P3 |
|---|---|---|---|
| 0 | 0 | 0 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: Pass (B4 only)
NOT ASSESSED: none within B4
```

## 2. 生产事故风险推演

无残余 P0/P1。已实测的失效边界：迟到详情不覆盖新选择；未知字段/错误关联/私有错误正文不展示；断网保留旧详情并明确更新暂停，恢复读取后同一摘要一致；网页无 API 写请求。模型费用未知不会显示为零，未结算预留不会被描述为已实际消耗。

## 3. 详细审计明细

无确认缺陷或待判项。核对事项：

1. `analyses.ts` 的 strict DTO 拒绝未知字段，检查枚举、预算、终态时间、事件连续版本、任务及证据关联，GET 有字节上限、15 秒超时与取消。服务端先校验摘要/事件账本，前端没有伪称再次验证整个账本的哈希。
2. `analysis-history.tsx` 按任务 ID 关联详情，切换时清空旧详情，AbortController 防止迟到响应覆盖；非终态串行轮询，错误停止轮询、提示旧详情。无模型密钥输入、执行或修复按钮。
3. CLI 命令只引用固定案例和经 UUID schema 验证的任务标识。候选仅建议、验证未执行、费用未知、合成来源均明确；运行关联落到已有真实详情页。
4. 协作目录升版为 v2，分别描述 CLI 与网页可执行状态。能力目录、站内文档、迭代历史同步，保留此前记录；本次仍为评审中，不把页面接通写成整阶段验收完成。
5. 新增 `wrong_type` 只用于解释读取到的实际运行；没有扩张网页受控场景选择权限。
6. 1280/390 浅色与深色四组合 axe WCAG2A/AA 无违规、页面无水平溢出；独立目视检查浅色桌面/深色手机截图，列表/详情层级、预算数值、CLI 入口及主题对比正常。

独立新增 `tests/analyses-live.spec.ts`：临时目录最初不存在，真实 CLI 初始化并执行 `check_only`，真实 SQLite → HTTP API → 页面呈现，核对模型调用为零、检查终态、摘要 SHA 一致、无隔离执行、断网恢复与全程 GET-only。未用路由 mock 代替该链路。

## 4. 维度覆盖声明

| # | 维度 | 发现数 | 说明 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | DTO/API 读取与组件呈现分离，网页只读 |
| 2 | SOLID | 0 | 状态标签/契约集中，未复制执行逻辑 |
| 3 | 并发与资源 | 0 | Abort、串行轮询、超时、卸载关闭 |
| 4 | 容错 | 0 | 明确旧数据、错误正文不回显，可重试 |
| 5 | 性能 | 0 | 最多50条摘要、256事件、响应字节有界 |
| 6 | 安全 | 0 | 无凭据/原始模型输出；UUID链接及React转义 |
| 7 | 可观测性 | 0 | 结构化步骤、用量/未知预留/固定错误码 |
| 8 | 类型 | 0 | strict schema、实际API数据联通，tsc通过 |
| 9 | 可测试性 | 0 | mock故障覆盖+独立真实CLI/API链路 |
| 10 | 工程规范 | 0 | 能力/历史/文档同步，原记录保留 |
| 11 | 数据事务 | 0 | 本批不写数据库；读取关联由B1校验 |
| 12 | 依赖 | 0 | 无前端新依赖或锁文件变化 |

## 5. 整改清单

none；没有风险接受或豁免。

## 6. 架构防腐与长效治理建议

1. 将独立 `analyses-live.spec.ts` 保留为显式 SQLite 集成门禁；`python3 frontend/tests/run_analysis_live_tests.py` 会构建到专用端口并创建临时状态目录，成本约一次构建与一次浏览器测试，避免服务端/前端契约一起漂移。
2. 后续若开放网页模型发起，须新写操作授权与幂等规格；当前只读页面测试明确禁止 API 写请求，防止演进时悄然突破边界。

## 7. 审计声明

实际运行（复用作者已冻结、指向8034的production build；专用3014/8034，临时状态目录）：

```text
AWB_ANALYSES_E2E=1 AWB_RUNS_E2E=1 AWB_STATE_DIR=<临时awb-analysis-e2e目录>/state AWB_API_PORT=8034 PW_PORT=3014 PLAYWRIGHT_CHANNEL=chrome npx playwright test tests/analyses-live.spec.ts tests/analyses.spec.ts --reporter=line
10 passed (9.4s)
npm --prefix frontend run typecheck
tsc --noEmit  [exit 0]
```

初次独立测试的末尾断言误将 Next 自带空 route announcer（role=alert）计为错误，9项通过/1项测试断言失败；检查快照后把断言限定在分析记录区域，再跑10项全部通过。未修改实现来规避测试。4项主题/尺寸测试包含axe与截图，不能重复加算为额外用例。

原作者18项定向/build记录不计入本评审者独立运行数量。真实模型对话由A14另行验证；本报告不声称诊断准确率、自动修复或商业化效果。冻结后实现变化须复核增量。

## 8. 分析摘要下载及 CI 接线增量

2026-10-14，独立只读复核新增下载按钮、`proposal_reviewed` 标签与 CI 接线，未发现阻断。下载仅序列化已经严格校验的 `AnalysisDetail`，文件名包含已验证 UUID，Blob URL 在一秒后释放，无额外 API 或第三方请求；不包含模型原文、候选正文或凭据。标签改为“证据已核对”，不会将只读证据复核表述为补丁验证通过。

`test:analyses-live` 顺序构建与执行独立临时 SQLite/API，8034/3014 与用户服务隔离，CI 复用已安装 Chromium（显式空 channel），无新增 Actions 或依赖。真实链路新增下载内容与 CLI summary/SHA 的一致性断言；本评审者没有并行启动 build，最后下载运行证据由主线程完整门禁补入交付记录。

## 9. 最终状态与下载门禁核对

独立评审直接核对主线程最终日志：完整UI82passed/3显式live skipped；独立运行链路21passed；独立分析链路1passed，已包含下载summary/SHA与CLI记录一致性。三处旧诊断状态断言改为网页只读且展开实际折叠进度，未移除原取消/权限/导航检查。能力/迭代文案与实际P0-05b建议边界同步，无新增阻断。最终下载增量运行证据已补齐，第8节待验证项关闭；仍不等同P0-06补丁应用或回归完成。
