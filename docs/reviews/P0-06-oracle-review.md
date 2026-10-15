# P0-06 B2 独立宿主 Oracle 代码评审

- 对象：`candidate_execution/{__init__,models,docker,oracle}.py`，`containers/p0_06/{Dockerfile,prepare.py,supervisor.py}`，`tests/test_candidate_{oracle,docker}.py`。
- 追加评审反例：`tests/test_candidate_oracle_review.py`、`tests/test_candidate_oracle_version_review.py`。
- 版本：当前工作树，本报告末尾记录复审快照；不包括尚未冻结的 `compare.py`。
- 技术栈：Python 3.12、AnyIO / asyncio、MCP 2.3.0、Docker 本机 Unix socket。
- 方法：auditing-enterprise-code-quality；General SaaS / Mission-Critical。
- 日期：2026-10-14；评审者 final_review，独立于作者 review_ui_api。

## 1. 代码质量评估卡

**最终复审 Pass，100/100。** 初评 Defect P1-01 已由作者修复，独立反例及真实 Docker 门禁复跑通过。本批只覆盖单快照/场景的受控执行与宿主行为判定，不覆盖四容器比较、T07 持久事务、恢复命令、CLI 或网页。

| Defect P0 | Defect P1 | Defect P2 | Defect P3 |
|---|---|---|---|
| 0 | 0（1 项已修复） | 0 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 0 (P1-01 closed after independent rerun)
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: Pass (B2 single-snapshot oracle only)
NOT ASSESSED: future comparison/persistence/recovery/API integration
```

## 2. 生产事故风险推演

**P1-01 — 同一验收器摘要对应不同安全执行实现。** 修改共享 `runner/docker.py` 的命令或身份检查逻辑，或者修改快照核验、JSON 解码逻辑后，当前摘要仍相同。历史报告与新报告因此看起来使用同一 oracle 版本，破坏冻结回归的版本追溯；不能据此安全比较行为。该问题是版本绑定缺口，不是已证明的候选逃逸。影响所有沿用该摘要的跨版本比较。

## 3. 详细审计明细

### P1-01：Oracle 版本没有绑定承重共享依赖 [confirmed]

- 位置：初评 `src/agent_workbench/candidate_execution/oracle.py:78–88`，`oracle_sha256`。
- 维度：架构与边界、数据完整性、工程规范。
- 机制：仅列入五个源文件，遗漏实际 Docker 调用与清理、SnapshotStore、JSON/契约解析及锁定依赖版本。
- 独立复现：`tests/test_candidate_oracle_version_review.py` 在临时源码副本修改 `runner/docker.py` 后，`verify_oracle()` 仍 True。`--maxfail=1` 实际 `1 failed in 0.43s`；未改变主目录生产源码、未执行修改后的程序。
- 最小修复：扩展显式安全依赖清单与 `uv.lock`，同时纳入摘要；对逐文件变化与缺失做失败关闭测试。由原作者实施，评审者不改生产代码。

其余 P0/P2/P3：none。

### 已实测证据

主目录显式运行 `uv run --frozen python containers/p0_06/prepare.py`，本地已有基础镜像、离线 build；没有复制作者沙盒运行产物、没有自动拉取或迁移主数据库。

```text
image_id: sha256:3eb5785888b80196832d32a2e93d82823461b9fd5c5eb8c519bcdd44800160b9
source_sha256: 219fc569b3187a1b24562170b2a64148565e2a57ed88f10e764fbef1beeabf78
```

初评独立复跑：

```sh
AWB_CANDIDATE_DOCKER_TEST=1 uv run --frozen pytest tests/test_candidate_oracle.py tests/test_candidate_docker.py -o addopts='' -q
AWB_CANDIDATE_DOCKER_TEST=1 uv run --frozen pytest tests/test_candidate_oracle_review.py -o addopts='' -q
```

```text
66 passed in 15.33s
4 passed in 3.23s
All checks passed!
8 files already formatted
Success: no issues found in 5 source files
```

66 项含 54 个确定性测试、12 个真实 Docker 测试。追加 4 项真实 Docker 反例覆盖重复 JSON-RPC 响应、stderr 洪泛、容器内拒写/UID/网络/cgroup 实况，以及已有 attempt 不被接管或删除。新增权限探针最初仅接受 EROFS，实际 0444 文件先返回 EACCES，已修正探针接受这两种拒写 errno 后通过；不是生产实现修复。

## 4. 维度覆盖声明

| # | 维度 | 初评发现数 | 结论 |
|---|---|---|---|
| 1 | 架构与边界 | 1 | P1-01；单 oracle 不生成 candidate_verified |
| 2 | SOLID 与设计 | 0 | 镜像准备、权限检查、冻结判定、报告分离 |
| 3 | 并发与资源 | 0 | native 重复取消等清理；attempt 唯一所有权由调用层保证 |
| 4 | 容错 | 0 | 协议缺项 inconclusive；清理不明 unknown |
| 5 | 性能与限额 | 0 | 帧/累计输出限制；阶段/总期限及回收有界 |
| 6 | 安全与合规 | 0 | 非 root、断网、只读唯一 mount、cap-drop；无 oracle 挂载 |
| 7 | 可观测性 | 0 | 摘要/失败码/逐项状态，未泄露异常或响应正文 |
| 8 | 类型与契约 | 0 | 严格整数、冻结 schema、非法参数不计数 |
| 9 | 可测试性 | 0 | 真 Docker、取消、伪造成功、实际输出洪泛 |
| 10 | 工程规范 | 关联 P1-01 | 锁版本绑定待补；依赖当前 MCP 精确版本 |
| 11 | 数据与事务 | 关联 P1-01 | 跨版本追溯待补；持久账本另批 |
| 12 | 依赖治理 | 关联 P1-01 | 固定镜像摘要与最小离线 context；锁文件待绑定 |

同一问题只按 P1-01 扣分一次，不重复累计维度。

## 5. 整改清单

| ID | 严重级 | 负责人 | 截止 | 状态 |
|---|---|---|---|---|
| P1-01 | Defect P1 | review_ui_api | B2 签发 Pass 前 | 已修复并独立复审 |

## 6. 架构防腐与长效治理建议

1. 新增安全依赖时更新显式版本清单及逐文件失效测试；避免共享执行代码变化却继续复用旧 oracle 身份。
2. 持久调用层在任何 create 前保证 attempt 独占和已登记；本底层拒绝已有容器，但不替代跨进程请求幂等、SIGKILL 残留恢复或四次比较的事务。后续集成必须另行故障实测。

## 7. 审计声明

评审只修改测试与报告。当前没有候选运行代码在宿主执行，只有 AST/源码复制与可信工具执行器在宿主运行。宿主死亡后的独立硬到期回收没有承诺，也未作为本批通过项；恢复精确 reap 仍待持久层交付。没有豁免；P1 已通过下述独立增量复审。范围外集成不得据此宣称已完成。


## 8. P1 修复后独立复审与冻结

作者仅修改 `oracle.py` 与 `test_candidate_oracle.py`。新增 `ORACLE_SAFETY_FILES` 最初明列 34 个路径，覆盖共享执行/清理/快照/JSON/MCP/契约及顶层导入的安全依赖与 `uv.lock`；容器源码和快照内容继续使用各自独立摘要。逐路径测试确认任何一项变化导致版本校验失败，缺文件失败关闭。评审者独立的 7 项既有反例全部转绿，无需修改测试期望。P1-01 关闭。

```sh
AWB_CANDIDATE_DOCKER_TEST=1 uv run --frozen pytest tests/test_candidate_oracle.py tests/test_candidate_docker.py tests/test_candidate_oracle_review.py tests/test_candidate_oracle_version_review.py -o addopts='' -q
```

```text
112 passed in 16.98s
All checks passed!
9 files already formatted
Success: no issues found in 5 source files
```

此修订 112 项 = 96 个确定性测试 + 16 个真实 Docker 测试；包含原作者 66 项、作者新增 35 项版本绑定测试、评审者 4 项容器反例与 7 项版本反例。全部由评审者在主目录复跑，未复用沙盒产物。镜像内容未变，无需重复准备。测试计数不代表真实模型评估或宿主死亡恢复已完成。

```text
621e9fc48c074f6ac1a364b36976553885eb64439acd743f89a280ef7388664e  src/agent_workbench/candidate_execution/__init__.py
ca45237561ec016909e3acbcf11bad044694746da97df5e51480d9faa3fee51b  src/agent_workbench/candidate_execution/models.py
0d02601b23432913f3d9ae79bba2e132abe5595149caca5adb09ec3617972805  src/agent_workbench/candidate_execution/docker.py
564762f64b5740b285cdbd43956976fec31a8cc72a057bc51cdb41d2c8862678  src/agent_workbench/candidate_execution/oracle.py
3513ed7decbddc319786ea20c047395ecb4105d1cb026d2b709b480b5dcbe56e  containers/p0_06/Dockerfile
b304e73167b55c786ce8b14e7243efe7ff6cb6a67dc8e7d66c1129c709dffcf6  containers/p0_06/prepare.py
bd48989d63a199045cd7c9c9a07217d2e90345f3fbbe7e610cca9ee0e971e635  containers/p0_06/supervisor.py
d7de4f770a75be6a75d26b481b1b5a4a820ae2f3d2e7c7206ad2004d7665dd01  tests/test_candidate_oracle.py
448b93fe4fbb56ebb8445c02ad443bcbb8a239b845fb3eb77123e5086ff31838  tests/test_candidate_docker.py
5212a42493e7094250e4c314fb81fe12f3cd2b6f8127abaf6550e9dd5f5d49f8  tests/test_candidate_oracle_review.py
0951fac9a19e73fbea51cdf2881303dea91ea93c470261e42d039201ed460ce9  tests/test_candidate_oracle_version_review.py
```


### 比较器依赖绑定的最终增量

随后按主线程要求把 `candidate_execution/compare.py` 纳入第 35 个安全依赖（仅计算文件摘要，不导入比较器），自动增加一项版本变更反例。比较器实现由另一位独立 reviewer 另批审查，本报告不冒充其代码评审。

最终范围共覆盖 **113 项**：97 个确定性、16 个真实 Docker。该轮整批结果为 `2 failed, 111 passed in 17.24s`；两项失败均为 `oracle_unverified`，由主线程在测试期间修改被绑定的 compare.py 引起，符合冻结门禁行为。主线程确认比较器冻结后，评审者仅复跑受影响的 stderr 洪泛和真实权限两项：`2 passed, 2 deselected in 1.85s`。未更改测试预期掩盖失败。最终 oracle/test 文件 Ruff 与格式通过，旧 P1 关闭，B2 本批 Pass。上述 SHA 为增加第 35 项后的最终源文件版本；比较器未来变动需重新启动进程绑定新摘要。
