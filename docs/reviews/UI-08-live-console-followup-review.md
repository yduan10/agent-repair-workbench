# UI-08 真实执行控制台独立复验

- 审计对象：`frontend/tests/console-live.spec.ts` 新版 UI 的真实契约检查与两场景复现；只调整测试关联与等待，不改生产代码。
- 版本：2026-10-15 工作树，HEAD `802bf70`；测试 SHA-256 `f565fa17c99c22c6df8e9a421e5b77a3f255af300ea709fae3c5e3f7e5029ed3`。
- 技术栈：Next.js 生产前端 / Playwright Chrome / 真实 FastAPI / SQLite / Docker。
- 场景与严苛度：General SaaS / Mission-Critical。
- 时间：2026-10-15，Asia/Shanghai。

## 1. 代码质量评估卡

**Pass（本次限定真实 UI 链路）**。未发现新增产品 P0/P1/P2/P3，原测试有一个跨任务等待错误，已修。

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 0 new product findings
FINAL SCORE: 100 (only this follow-up scope)
VERDICT: Pass — 3 actual live tests passed
NOT ASSESSED: actual model branch intentionally skipped; evaluated separately
```

**环境与命令**：复用生产前端 3010，将浏览器所有 `/api/**` 通过 route.fetch 转发到隔离真实 API 8034。没有编造 HTTP body、模型回复或 SQLite 记录；这与用固定 JSON mock 响应不同。数据目录为主项目忽略目录 `artifacts/awb-console-live-bz4rdusn/state`，没有对主服务 8030 发写请求。

```sh
AWB_CONSOLE_LIVE=1 AWB_STATE_DIR=<project-root>/artifacts/awb-console-live-bz4rdusn/state PLAYWRIGHT_CHANNEL=chrome npx playwright test tests/console-live.spec.ts --trace on
```

实际输出：**`1 skipped` / `3 passed (9.7s)`**。跳过真实模型建议测试：此轮没有 `AWB_LIVE_MODEL=1`，不把它算通过。

## 2. 生产事故风险推演

P0/P1：none。实际观察为测试提前读取新任务，而终端仍展示合法的旧历史任务；没有证明生产页面把旧任务数据写进新任务。

## 3. 详细审计明细

### 首轮失败与根因边界

- root 第一轮旧测试认为刷新后必须继续展开实时终端，实际已结束记录默认收起；运行复现又没等本次 POST ID 对应的新 URL，读取了前一条成功记录。
- root 第二轮已修上述两项，容器场景2项通过；契约分析仍先匹配任意终端“分析已结束”，随后直接GET新ID、未检查HTTP就访问 summary，因此出现 `data.summary undefined`。
- 审计者确认测试存在这个跨任务竞态。旧失败当时具体HTTP状态未保存为充分证据，不能断言一定是404或429；本轮trace确有证据读取短暂429，并在已有只读重试中恢复。

### 测试最小修改

1. 点击前注册本次分析 POST 响应等待。
2. 要求 HTTP 成功，接受结果 `task_id` 与本次浏览器 request_id 一致，summary task_id 一致。
3. 先等 URL 指向新ID，再检查终端结束事件。
4. 对新ID的只读详情 GET 有界轮询，只有404/429作为暂态；其他非成功响应立即失败；每次成功都核对 summary task_id。
5. 不自动重 POST、不放宽结果断言，仍要求 `check_complete`、模型调用0次、可读字段证据、刷新后同ID且浏览器只有1次POST。

### 本轮真实结果

| 路径 | 验证 |
|---|---|
| 网页契约分析 | 新ID关联、check_complete、model_calls=0、字段证据可读、刷新不重复提交；2.8s |
| pass 容器复现 | 本次202接受ID对应URL，scenario=pass、status=succeeded、executor_state=absent、调用成功；2.8s |
| tool_error 容器复现 | 本次202接受ID对应URL，scenario=tool_error、status=failed、executor_state=absent、调用失败；2.8s |
| 模型三角色建议 | skipped，未调用 |

网络摘要存本地 `artifacts/ui08-live-console-review-network.json`：每项分别有一条浏览器3010 POST以及一条测试转发8034 POST，属于同一次转发请求，不是两次执行。分析刷新没有新增浏览器 POST。

## 4. 维度覆盖声明

| 维度 | 结论 |
|---|---|
| 架构/边界、SOLID | 未改变产品架构，仅测试跟随真实接受契约 |
| 并发/资源、容错 | 新ID绑定、受限GET轮询；不重POST；两容器已回收 |
| 性能、安全合规 | 无压力测试；仅隔离目录；没有主库写入或模型外发 |
| 可观测、类型契约 | 明确HTTP失败，不直接解引用不存在summary；ID一致性断言 |
| 可测试性、规范一致性 | 测试符合新UI历史终端默认收起规则，未弱化最终结果 |
| 数据完整性、依赖治理 | 不修改持久数据、依赖和生产源文件 |

## 5. 整改清单

无新增产品缺陷。真实模型分支独立验收，不能用此报告替代；先前失败日志保留在 `artifacts/ui08-live-console*.log`。

## 6. 长效治理建议

所有“启动后等完成”的 E2E，先等待接受ID，再把 URL、详情和终态断言绑定到该ID；不能只凭一个历史面板里出现终态文案。

## 7. 审计声明

评审者只改测试和报告，未改生产、未启停服务、未写主数据库。三项成功均是真实 HTTP / SQLite 链路，其中两项实际执行 Docker；模型一项明确跳过。trace不包含凭据，报告不转载原始敏感响应。
