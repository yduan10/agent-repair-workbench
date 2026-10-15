# UI-08 真实修复记录独立复验

- **对象**：新版生产 UI 读取真实 P0-06 冻结12次实验记录；`repairs-live.spec.ts`、`repair-cases.spec.ts`。仅修改测试等待/重试，生产代码冻结。
- **时间**：2026-10-15，Asia/Shanghai。
- **技术栈 / 场景 / 严苛度**：Playwright Chrome + Next.js生产服务 + FastAPI/SQLite，General SaaS，Mission-Critical。
- **版本**：HEAD `802bf70` + 当前工作树；修复 live 测试 SHA-256 `0ccf0def41c356e64634ff18c9e345a9d1abea71d520819c086e6d6f52340126`。

## 1. 代码质量评估卡

**Pass（本次真实只读 UI 链路）**，未发现新增 P0/P1/P2/P3。原测试额外 GET 与页面初始读取并发，曾触发真实429；本轮将对照 GET 移到页面就绪后，并加入严格有界、只针对实际429的UI重试。

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 0 new product findings
FINAL SCORE: 100 (this narrow follow-up only)
VERDICT: Pass — two actual read-only integration tests passed
NOT ASSESSED: all twelve patches' visual details; model/executor accuracy belongs to independent cohort audit
```

命令（frontend目录）：

```sh
AWB_REPAIR_LIVE_URL=http://127.0.0.1:8035 AWB_REPAIR_CASES_LIVE_URL=http://127.0.0.1:8035 PLAYWRIGHT_CHANNEL=chrome npx playwright test tests/repairs-live.spec.ts tests/repair-cases.spec.ts --trace on --output ../artifacts/ui08-real-repair-review
```

实际输出：**`2 passed (4.6s)`**，无 skipped。`npm run typecheck` exit 0。

## 2. 生产事故风险推演

P0/P1：none。真实只读服务会对竞争读取返回429，UI已有显式重试入口；本报告没有以自动隐藏错误或伪造HTTP成功来绕过该现象。

## 3. 详细审计明细

### 测试变更与防止掩盖错误

1. 页面初始 GET 完成并显示真实 diff 后，才另行取同 task/candidate 的对照diff，不人为增加初始并发。
2. 通过真实转发响应记下每个非成功HTTP；只有页面出现错误且本轮观察到的响应全部为429时，才点击已有“重试读取列表 / 重试读取详情 / 重试”。
3. 最多点击3次；任何非429响应、没有对应HTTP的解析错误、超限均失败，不自动重写请求或伪造响应。
4. 本轮 repairs-live 实际没有429，因此**只验证了正常真实读取链路，没有宣称实测了新增重试分支**。原失败trace与日志保留。

### 实际证据

| 层级 | 验证内容 | 真实性 |
|---|---|---|
| 双案例列表与详情 | API schema2，case集合恰为output_mismatch/counter_offset；逐任务点击，URL与任务标签对应，真实detail可解析 | 真实8035与12次实验SQLite记录 |
| 当前候选diff | 找到当前verified候选，页面每一行与随后GET所得 unified_diff逐行完全一致，包含hunk和空行顺序 | 真实保存补丁，不是静态fixture |
| 当前候选回归 | 同候选切到回归标签；三个类型/值错误与case一致；当前回归通过、人工接受仍未开放 | 真实比较记录 |
| schema负向测试 | 旧版本、未知case、错case指纹、0/1/3槽拒绝 | 在真实detail基础上构造的本地DTO反例；不是历史模型结果 |
| 旧列表版本UI拒绝 | 最后一轮显式返回schema1，页面提示不匹配 | 明确mock负向响应，不计正常真实链路 |
| 副作用 | repair API浏览器请求均GET，repairs-live写请求数组为空 | 不运行模型、不执行补丁、不更改实验库 |

材料：`artifacts/ui08-real-repair-review/` 两份trace；`network-summary.json`仅含origin/method/path/status；截图 `frontend/artifacts/ui08-live-diff.png`、`ui08-live-regression.png`。

**异常材料未隐藏**：case-live快速切换过程中有一条浏览器diff记录HTTP404，同时trace明确标记 `_failureText: net::ERR_ABORTED`；随后对同 task/candidate 直接GET8035返回200且验证通过。本报告不据此推断全部12个diff都经过视觉验收，也不把这条取消响应写成成功。case-live的门禁是逐任务标签/详情和schema关联；当前候选逐行diff由另一个live测试明确验证。

## 4. 维度覆盖声明

| 维度 | 结论 |
|---|---|
| 架构/边界、SOLID | 无生产修改，沿用只读API |
| 并发/资源、容错 | 对照GET后移；仅真实429显式有界重试；非429不得掩盖 |
| 性能、安全合规 | 不做压力评估；实验只读，不接触凭据或运行模型 |
| 可观测、类型安全 | 留存所有失败材料、网络摘要；严格case/schema/ID关联 |
| 可测试性、规范 | 实际服务内容与本地构造反例明确分开 |
| 数据完整性、依赖 | 无数据库写、无依赖更改、无接受候选 |

## 5. 整改清单

无新增产品缺陷。本轮未触发的重试分支不计实际恢复验证；不追加无意义重跑来追求某种网络竞态。

## 6. 长效治理建议

真实只读验收先让被测UI完成自身读取，再取独立对照；断言绑定task/candidate，不把重试、取消或旧记录当新结果。若产品后续统一只读429重试，仍需独立验证有界次数和非429拒绝。

## 7. 审计声明

本次只读真实实验产物，不新增实验、不修改冻结生产代码。两测试通过不代表全产品上线或多角色优于单角色；模型效果与成本应引用独立12次实验审计。
