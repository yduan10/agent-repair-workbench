# 企业代码质量审计报告：P0-04 只读运行记录前端

- **审计对象**：P0-04 前端增量及测试门禁，文件摘要见附录。
- **审计版本**：独立目录 `p0-04-ui-review` 的冻结快照；实现者 `review_ui_api`，评审者 `docs_review`。
- **技术栈**：Next.js 16.4、React 19、TypeScript、Zod、Playwright、axe；浏览器实际连接 FastAPI / SQLite 只读 API。
- **业务场景**：General SaaS。
- **审查严苛度**：Mission-Critical，仅用于已声明的可信本机 UI 边界。
- **审计时间**：2026-10-13。

## 1. 代码质量评估卡

- **综合质量得分**：100 / 100（当前范围没有确认缺陷，不代表整个平台质量认证）。
- **上线评估结论**：✅ Pass，准予合入本地开发版本。
- **审计范围**：新客户端与页面组件共 288 行；另审路由、代理、局部 CSS、能力与历史文案、测试及 CI 增量。未变化的旧页面不作重复全面审计。本批增量小于 2000 行。
- **范围外未评估**：公网部署、多租户、远端 GitHub Actions 实际运行、SQLite 内部实现和 Docker 沙箱隔离。后两项交其他独立 reviewer；本评审者曾实现存储，不能以本报告审查自己的后端。

| P0 阻断 | P1 严重 | P2 主要 | P3 次要 |
| :---: | :---: | :---: | :---: |
| 0 | 0 | 0 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: none -> 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: Pass — 本地只读UI范围内无未解决缺陷
NOT ASSESSED: 上述范围外项目；不作整体生产上线结论
```

## 2. 生产事故风险推演

没有确认的 P0/P1 事故路径。实际验证过的失败路径：

- HTTP 503、断网、404、超 1 MiB、未知字段与状态、重复运行 ID、非法日期及事件倒序均拒绝显示不可靠数据；固定提示不回显服务器原始错误。
- 切换记录与离页中止旧详情请求；旧结果不能覆盖新选择。
- 报告摘要不符不会下载；下载过程中切换到另一条记录中止请求，即使旧报告晚到也不会触发下载。

## 3. 详细审计明细

### P0 — 阻断性缺陷

none。

### P1 — 严重缺陷

none。

### P2 — 主要缺陷

none。

### P3 — 次要缺陷

none。

### 验证证据

独立目录实际执行：

1. `npm run test:runs-live`：production build 成功；`20 passed (21.5s)`。真实 SQLite / API 场景包含空库不创建、六状态、事件、报告原字节摘要、断网恢复。此处 seed 是合成契约记录，不冒充 Docker 执行。
2. 20 项内包括 9 页面 × 2 主题 × 2 视口的 axe / 溢出检查，以及有记录详情 1440px 浅色、390px 深色；分别检查 `artifacts/p004-runs-1440.png` 和 `artifacts/p004-runs-390.png`，未见遮挡、越界或难辨文字。
3. 独立追加 `review-download.spec.ts`：`1 passed (1.4s)`。等待下载请求发出后切换记录，确认 requestfailed、没有 download 事件、当前选择保留且不出现下载成功提示。
4. 主题、系统偏好、受限 storage、降低动效与历史条目保留在上述 20 项中复核。草稿离页保护调用路径与原 Sidebar 保持不变；主 Agent 另有完整旧 POST / 草稿流程回归证据，本人不将该结果记为自己执行。
5. `.github/workflows/checks.yml` 增量静态验证：已安装 Chromium，原 UI 回归后增加临时库真实集成测试，`PLAYWRIGHT_CHANNEL: ""` 使用该 Chromium；测试禁止复用已有服务，端口固定 3011/8031，不放宽后端 Origin。
6. 未新增 npm 依赖，package-lock 与本轮基线一致。依赖公告扫描沿用主任务证据；此处不声称独立运行远端审计。

评审环境首次 build 因评审者漏复制 `examples` 依赖失败；补齐后独立 build 与全部测试通过。这是审查环境准备问题，不计产品缺陷。

## 4. 维度覆盖声明

| # | 维度 | 发现数 | 备注 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | GET-only；代理固定 loopback，精确三条 records 路由，无执行入口 |
| 2 | SOLID 与现代设计 | 0 | DTO与请求边界分离，组件负责页面交互 |
| 3 | 并发、异步与资源安全 | 0 | AbortController、15秒期限；详情与下载竞态独立负例通过 |
| 4 | 容错与防御性编程 | 0 | 流式1MiB上限、错误/空态、重试与旧列表提示 |
| 5 | 性能、伸缩性与计算效率 | 0 | 列表50、事件100；无轮询、无无限响应累积 |
| 6 | 安全与数据合规 | 0 | strict DTO拒绝token等未知字段，错误正文不展示，原字节hash+双ID关联 |
| 7 | 可观测性与运维友好度 | 0 | 真实状态/事件/摘要可查看，unknown不暗示未执行；无新增监控承诺 |
| 8 | 类型安全与契约表达 | 0 | 对照实际RunView/EventView/SandboxReport；Zod运行时校验 |
| 9 | 可测试性与死代码 | 0 | 真实SQLite集成和边界mock分明，附下载取消回归 |
| 10 | 工程规范与一致性 | 0 | 统一能力目录与历史保留，来源口径明确 |
| 11 | 数据与事务完整性 | 不适用 | UI只读；仅验证DTO关联与报告原始字节完整性，DB事务另审 |
| 12 | 依赖与供应链治理 | 0 | 无新增npm包；锁文件不变；远端CI执行在范围外 |

## 5. 整改清单

none，无需修复或风险豁免。新增独立下载取消反例已由主 Agent 纳入 `frontend/tests/runs.spec.ts` 持续门禁。

## 6. 架构防腐与长效治理建议

1. 保留当前真实 SQLite 集成测试作为 UI 门禁，后端 DTO 改动同时更新 schema 与测试；无需引入新框架。
2. 后续增加网页执行能力时单独评审权限、取消和幂等；当前 GET-only 页面通过不能替代未来执行入口评审。

## 7. 审计声明

- 结论仅针对附录 SHA-256 对应前端增量；后续行为变更需重新评审。
- 范围内无未评估实质路径；范围外内容列于第1节，不给全平台生产认证。
- 未施加豁免，没有疑似发现被当作确认缺陷。
- 本人未修改产品实现，仅在独立副本增加审查用负例与报告。

### 最终状态文案增量

主任务后端与UI门禁齐备后，将能力目录改为“记录可用”、P0-04历史标“已完成”，保留其余8条历史；未开放网页执行/取消/审批，未把344项工程验收写成用户运行数量。下载取消独立反例以原义加入正式测试。最终文本增量由本评审者静态复核，主Agent执行最终整合回归，双方证据不混算。

增量检查曾指出 appearance.spec.ts 残留旧文案断言和 modules.ts 未更新的验收中说明；主 Agent 已分别改为“任务总览已能查看运行记录”及“只读运行记录已接通”，本评审者逐项复核。没有未闭项。

## 附录：冻结源码摘要

以下20个实现/测试/配置文件为最终冻结范围。文档自身与验收日志另行维护，后续仅追加运行结果不改变代码摘要。

```text
b930a420aea15d590be11578fe15d6e9ff54140efa4487258ffe12750b313175  frontend/app/globals.css
069c059622a73bc98c6780c46d8698b8ff612513ac7b54076483e21a0dab8c20  frontend/app/page.tsx
78500f43811226a31d1e6fd5404e7a30ab949c16e9b6b699a376780c6cdd67fa  frontend/app/workspace/[section]/page.tsx
dcfd14071631a10367e1a44bd4bdcb5e9c44a59fa1b08a6c3c892ae3af7e3555  frontend/components/run-history.tsx
c1928b90401fb93e49bbdb57bd8b51f6cfb269abd6727de0267641d673ffd23f  frontend/lib/capabilities.ts
8f402daea4c64c94d67501f786c6ae23c19e3e70c042547b02e36485df2624df  frontend/lib/milestones.ts
871872afc7c12bd56339f7b49e523e914f92da912f4e99950885783702ab6a5f  frontend/lib/modules.ts
b97fc0e0e4273fb7a7511cf5e580407e5fdb4871527c0a90b7bbc967664b5ca3  frontend/lib/runs.ts
e003fa519b516b9791fd3288efa481a751713800f3ad7722d0eaf379cf8529cc  frontend/next.config.ts
a2a452868294309e9ec84cfe10023784036ad625ab1748d82632bf19b0ba8671  frontend/package.json
4eb7bafa8f4f6060989c22414ad6c8ee11fbffe8522aaa9a41959bee01ef24c8  frontend/package-lock.json
241ccd9a48f3744d9592eb6be3b1ca0d897d9d30da3cc0b31189c631aa72e775  frontend/playwright.config.ts
f3acbcb8a2fdc8b9d21778b50fd13184595b4cd972f911cd9a322143abffbfa1  frontend/tests/appearance.spec.ts
6038ad40aaa9b51a53ea661bd06a1714ed1a52b93ca5e6e546855d881c46314b  frontend/tests/product.spec.ts
cbe4cb464df3f3dc6e3215e452b6b5690dfa56af8c527bfd013a7a71bb13d22c  frontend/tests/progress.spec.ts
167d5b2fdfeb7341c13dbfdbb6379f4b71f646fa8b46866aeec9ecf9f4a26c38  frontend/tests/runs.spec.ts
ee2f5542f17d6cde37f4c07fc48bc3ed50cc51f330c993365d10b30f6babdefd  frontend/tests/runs-live.spec.ts
1c95187282dd9fa9fff5648942afbfd12daa494e686e8cbf0bedae8b65b0bf23  frontend/tests/run_live_tests.py
cda1d130b5397ca8e5ef0c161aaba0971b49e7a6ed811ff935be5e4e5299ff59  frontend/tests/fixtures/seed_runs.py
f34a091e18a7932cdd50257b80276c22307b06d1177af596dd5e246c6aef501f  .github/workflows/checks.yml
```
