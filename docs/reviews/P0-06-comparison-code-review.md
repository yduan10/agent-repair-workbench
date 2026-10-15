# P0-06 B2：固定比较器独立代码评审

日期：2026-10-14。结论：**Pass，仅限本批比较器合入**。不表示 T07 持久登记、恢复、模型修复或父 P0-06 已完成。

## 范围与独立性

- 实现：`src/agent_workbench/candidate_execution/compare.py`。
- 作者测试：`tests/test_candidate_comparison.py`。
- 独立反例：`tests/test_candidate_comparison_review.py`。
- 依据：`docs/26-p0-06-candidate-verification.md`，使用 auditing-enterprise-code-quality 技能。
- 本评审者未参与比较器实现；参与过下层 Oracle，实现自审不包含在本报告结论。下层 Oracle 由另一评审者独立审查。
- 没有调用模型、访问用户数据库或修改服务端口。比较器真实 Docker 门禁由作者执行；本次独立复核聚焦决定性规则和生命周期编排。

## 缺陷及闭环

### Defect P2：公共 Python DTO 可接受被修改的嵌套报告 — 已关闭

合法 `SlotResult` 内持有可变 `OracleReport`。构造之后把候选步骤改为 `failed/count_value`，但保留父报告的 `passed`，直接构造 `ComparisonReport(... outcome="candidate_verified")` 原先仍成功。Pydantic 默认不重新校验已经创建的嵌套模型实例，而比较判定依赖父状态。

现有 `make_report` 工厂通过 JSON 重校验，因此实际比较主路径已有保护；未证实外部 JSON 可绕过。不把公共 Python 对象边界问题夸大为候选代码逃逸。

修复：`ComparisonReport.coherent` 在推导结论前对所有嵌套 `OracleReport` 做 JSON 重解析。独立反例 `test_python_dto_cannot_preserve_verified_with_mutated_failed_step` 修复前失败、修复后通过；保留为回归门禁。

当前未关闭 Defect P0/P1/P2：0。

## 已核验的规则

1. 四个槽位固定、顺序固定，attempt UUID 必须唯一且逐一绑定快照、场景、镜像和 Oracle/suite 版本。
2. 基线须同时满足 wrong_type 的三处精确类型错误，以及正常场景通过。其他错误不能冒充原问题复现。
3. 候选两种场景必须全部通过；缺槽、未执行步骤、版本不符、取消和清理未知均不能验证通过。
4. 结果逐项持久化后才开始下一个容器；保存失败直接传播，不启动下一槽位、不重投。
5. 取消、未知、不完整结果保存一次后停止；独立三个参数化反例验证调用与保存次数均为 1。
6. 比较前后均检查快照、镜像与完整 Oracle 版本；比较器自身已纳入 Oracle 的固定安全依赖哈希清单。
7. `accepted` 固定为 false；验证通过没有被等同于用户接受或写回项目。

## 验证证据

实际运行：

```text
uv run pytest tests/test_candidate_comparison_review.py tests/test_candidate_comparison.py
35 passed, 3 skipped in 0.33s

uv run mypy src/agent_workbench/candidate_execution/compare.py
Success: no issues found in 1 source file

uv run ruff check tests/test_candidate_comparison_review.py
All checks passed!
```

独立反例 5 项全部通过；作者确定性用例 30 项通过。3 项 Docker 用例要求 `AWB_CANDIDATE_DOCKER_TEST=1`，此次独立复核未启用，不计入通过数。作者报告已实际跑过固定正确修复、常量 1、仅修好 wrong_type 却破坏 pass 的三组四容器比较；最终集成仍以主线统一冻结后的真实门禁为准。

## 十二维度检查与确定性评分

按技能 `references/scoring-rubric.md` 计算。维度表记录检查依据；不对每个维度主观打分，也不把本批得分视为产品效果或全项目质量指标。

| 维度 | 依据或边界 |
| --- | --- |
| 架构与边界 | 比较判定与持久化、模型、容器执行分离 |
| 职责与依赖 | 固定计划、判定和编排各自明确 |
| 并发与资源 | 串行已登记身份；持久 owner fence 由调用方负责，本批已核验调用契约 |
| 容错 | 不重投，保存失败停止，未知不能通过 |
| 性能与伸缩 | 固定四次，拒绝无有效余量；未做吞吐承诺 |
| 安全与合规 | 不接受候选结论、命令或验收规则 |
| 可观测性 | 完整槽位及版本绑定，结构化原因 |
| 类型安全 | 严格 DTO，已修复嵌套实例重校验 |
| 可测试性 | 独立失败反例及确定性边界覆盖 |
| 工程规范 | 类型检查通过，独立复核与源码冻结 |
| 数据与事务 | 外部副作用前登记由上层契约承担，本批没有数据库事务 |
| 依赖与供应链 | 宿主安全依赖与锁文件哈希，固定已准备镜像 |

初审曾发现 1 项 confirmed Defect P2：`100 − 3 × 1.0 = 97`；在默认 Mission-Critical 下 P2 预算为 0，因此初审不能 Pass。该问题已修复并通过独立反例，复审仅按剩余未关闭项计算：

```text
STRICTNESS:   Mission-Critical
SCENARIO:     General SaaS
DEDUCTIONS:   open P0=0, P1=0, P2=0, P3=0 -> sum=0
RAW SCORE:    100 - 0 = 100
CAP APPLIED:  none
FINAL SCORE:  100 / 100
VERDICT:      Pass (this comparison batch only)
NOT ASSESSED: none within the stated comparison-module scope
```

100 表示本次已审范围没有未关闭发现，不表示已经证明不存在其他缺陷。下层 Docker 与上层持久账本不包含在本批实现范围；它们由各自独立评审与集成门禁负责，不能由此分数代替。

## 故障推演与交付限制

- 持久化失败：已经执行的槽位不能自动重跑，后续执行不得启动；由上层预登记身份做显式对账。
- 主机进程 SIGKILL：本模块不能保证已登记容器自行到期；待后续持久恢复和精确 reap 验收。不继承旧 profile 的硬到期承诺。
- 时间边界：`total_timeout` 是执行预算，清理属于额外有界收尾；若产品要承诺端到端墙钟上限，需要在上层明确纳入 create ACK shield 和资源回收最坏余量。当前余量检查不能当作绝对到期保证。
- 有限行为集：验证仅证明冻结序列，没有证明任意程序语义，也没有自动接受候选。

源码与测试 SHA 见同目录 `P0-06-comparison-source-sha256.json`。
