# 企业代码质量审计报告

- **对象**：P0-06 上下文进度及参数纠错增量，context/controller、4 个角色 prompt 1.3、作者控制器测试和独立反例。以前次 B3d 冻结代码为基线。
- **评审者**：p006_contracts，未参与生产实现；使用 auditing-enterprise-code-quality。
- **日期 / 场景 / 严苛度**：2026-10-14 / General SaaS / Mission-Critical。
- **技术栈**：Python 3.12、LangGraph、Pydantic、既有 SQLite 修复账本。

## 1. 代码质量评估卡

**Pass：允许本批进入真实模型实验。100 / 100，冻结版本无确认缺陷。** 此分数只反映本范围的缺陷扣分，不代表模型修复率；单角色/三角色效果必须报告真实实验结果，不得由静态评审推断。

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: none -> 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100 (context/progress/correction only)
VERDICT: Pass
NOT ASSESSED: real model efficacy, holdout generalization, arbitrary project repair
```

P0 / P1 / P2 / P3 均为 0；模型效果、跨项目泛化和未开发能力不在本次审查结论内。

## 2. 生产事故风险推演

- 参数错误出现后模型重复修正：最多允许 2 次纠错机会，总数跨成功工具、跨角色保留；每次新模型调用仍由原账本预留和结算预算。
- 已接收操作返回看似可纠正的错误：必须 task SHA 完全不变且 ready 才能反馈纠错；真实 reserve/finish 改变 SHA 的反例不能继续。
- 取消、未知结果、回放：先处理取消/对账，再看错误码；回放也不进入参数纠错。没有重放副作用的“自动重试”。
- 共享诊断读取结果：传递已授权事实，不能增加 repair 的工具权限；复制一个 diagnosis 的 check_contract 请求仍被 repair schema 拒绝。
- 上下文重复/膨胀：语义 target 去重而非随机 request ID；保留 48 KB 编码上限，结束清空临时素材，不以缓存替代宿主授权。

## 3. 详细审计明细

### P0 — 阻断性缺陷

none。

### P1 — 严重缺陷

none。

### P2 — 主要缺陷

none。

### P3 — 次要缺陷

none。

审阅 1.2 时指出 diagnosis 文案允许静态证据直接 handoff，而宿主要求先实际 T05 且自动转入 repair。最终 1.3 已明确必须先复现及宿主自动路由，未通过放宽宿主规则解决。

### 独立验证

```sh
uv run --frozen pytest -o addopts='--import-mode=importlib' tests/agents/test_repair_context_review.py tests/agents/test_repair_controller.py tests/agents/test_repair_controller_review.py tests/agents/test_repair_gateway.py -q
# 59 passed in 20.60s
```

其中本轮新增独立测试 10 项，使用真实临时 SQLite/快照及合成模型/oracle，不调用主库、真实模型或 Docker：

1. 相同 target 新 request ID 保留单个完成事实，去掉对应未完成模板。
2. diagnosis 的 check/source 结果能供 repair 使用，但不扩大 repair 工具 schema；未泄露隐藏 oracle 名称、版本、写入 replacement 或宿主镜像路径。
3. 已完成事实超出上下文上限拒绝；空结果不会虚构实际复现或候选状态。
4. 模型响应未知时清空暂存读取与素材。
5. stale candidate 使用相同 request ID 改参会冲突停止，不会重复候选接收。
6–9. 实际已接收完成、replayed、cancelled、requires_reconcile 四种情况均不能触发参数纠错。
10. 成功工具和 diagnosis→repair 切换不重置总计两次纠错额度。

```text
All checks passed!
3 files already formatted
Success: no issues found in 2 source files
```

对应 controller/context/独立测试的 Ruff 与 format，及两个生产源文件 `mypy --no-incremental`。作者新测试额外覆盖错误参数纠正后正常读取、总纠错次数、stale hash 换新 ID 后完整候选比较。

## 4. 维度覆盖声明

| # | 维度 | 发现数 | 结论 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | 上下文提示不能改角色权限、oracle、宿主路由 |
| 2 | SOLID 与设计 | 0 | context 负责组织事实，controller 控制纠错；未复制桥接逻辑 |
| 3 | 并发与资源安全 | 0 | 保留原 whole-life fence 和取消语义；本增量无新后台任务 |
| 4 | 容错 | 0 | 只纠正未接收且三类明确拒绝；未知/已接收/冲突仍停止 |
| 5 | 性能 | 0 | target 去重、48 KB cap、总计两次纠错和原模型预算 |
| 6 | 安全与合规 | 0 | 错误反馈只有固定 tool/code/accepted=false/剩余额度；不回显恶意参数 |
| 7 | 可观测性 | 0 | 已完成读取、执行进度与最后拒绝分开；不将参数请求当完成 |
| 8 | 类型与契约 | 0 | 复制宿主 candidate binding；schema 与权限保持原样 |
| 9 | 可测试性 | 0 | 10 个独立反例及已有 controller/gateway 回归，共 59 项 |
| 10 | 工程规范 | 0 | 4 个角色 prompt 同版本，gateway hash 回归覆盖；结束清空临时内容 |
| 11 | 数据与事务完整性 | 0 | 不改账本；纠错必须 SHA 不变，已接收调用仍完整计费 |
| 12 | 依赖与供应链治理 | 0 | 无依赖增量；全仓供应链未重审 |

## 5. 整改清单

none。最终冻结版本无待整改项。

## 6. 长效治理建议

1. 保留以上独立反例，后续若改变桥接错误码或 admission 流程，必须同时核对 SHA 不变是否仍能证明未接收。
2. 保持 `candidate_available` 的含义为曾创建候选，与比较通过、接受补丁分开。模型或页面不得将此布尔值解释为修复成功。
3. 记录相同版本、相同预算的真实单/三角色实验，包含失败；不要以合成脚本通过替代模型有效性。

## 7. 审计声明与冻结版本

生产源码只读；评审仅新增独立测试、报告及哈希清单。未改主数据库、prompt 或 oracle。后续版本变化按影响复审。无豁免。

```json
{
  "src/agent_workbench/repair_runtime/controller.py": "702ca5bd1eae5b5fa0c192ae913c6fa5c1d0a9ef225d8f62fe9ec2d85bec9f8b",
  "src/agent_workbench/repair_runtime/context.py": "ae8581cf3560ad2aefbb6849519f26aca1ee1b8aa4db00f837b79a953da2a1f9",
  "src/agent_workbench/agents/diagnosis/prompts/p006.txt": "b03c7921288f58808469257dbb8f8ef663039de58130c0ebca386d7f1fd591e5",
  "src/agent_workbench/agents/repair/prompts/p006.txt": "d0c70b5ca2b6907449c5682a2931286e33d7a83c703d346029fb72ce194b695a",
  "src/agent_workbench/agents/verification/prompts/p006.txt": "dc2bc771c6c119fbde118a83af66ff6f0a27b3deb42e860f83d6e65ab0a6b4fd",
  "src/agent_workbench/agents/single/prompts/p006.txt": "02edc483f96f30cc3595f230ff2f753532f4445e2c76fba9a245a395cf061cd6",
  "tests/agents/test_repair_controller.py": "c92bab469fa16b594da23abc81d929262a56784bcc5f9534aedb7d707295c192",
  "tests/agents/test_repair_context_review.py": "4f6540ea09d821d6115f276b657e3f4d784be535adeec09590d29b1c0d9f6987"
}
```
