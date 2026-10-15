# 企业代码质量审计报告：P0-06 H3 固定案例入口

- **审计对象**：`repair_runtime/cli.py`、`repair_runtime/controller.py` 及两个入口测试文件的 H3 增量。
- **审计版本**：`<review-workspaces>/p006-heldout/artifacts/h3-files.json` 冻结工作副本；SHA 见第 7 节。
- **技术栈**：Python 3.12、argparse、Pydantic、LangGraph、SQLite。
- **业务场景**：General SaaS。
- **审查严苛度**：Mission-Critical。
- **审计时间**：2026-10-14。
- **独立性**：H3 实现者为 root，本评审者为 web_analysis_service。评审者实现的 H1/H2 不属于本报告的批准范围，由 p006_contracts 单独评审。

## 1. 代码质量评估卡

- **综合质量得分**：**100 / 100**，限于本次无确认缺陷的受限增量，不代表完整产品质量评分。
- **上线评估结论**：**Pass，准予 H3 增量集成**。不是 P0-06 完成结论，也不替代 H1/H2、H4 或真实模型验收。
- **审计范围**：4 文件，132 行新增、8 行删除；另新增独立反例测试 22 项。
- **未评估项**：审计范围内 none。H1/H2 的内部实现、H4 页面、模型效果及通用仓库支持明确在本批范围之外。

| P0 阻断 | P1 严重 | P2 主要 | P3 次要 |
| :---: | :---: | :---: | :---: |
| 0 | 0 | 0 | 0 |

```text
STRICTNESS:   Mission-Critical
SCENARIO:     General SaaS
DEDUCTIONS:   none → Σ = 0
RAW SCORE:    100
CAP APPLIED:  none
FINAL SCORE:  100 / 100
VERDICT:      Pass — no confirmed defect in the frozen H3 delta
NOT ASSESSED: none within H3 scope
```

### 实际验证

评审者独立执行：

```sh
uv run --frozen pytest \
  tests/agents/test_repair_case_entry_review.py \
  tests/agents/test_repair_case_entry.py \
  tests/agents/test_repair_cli.py \
  tests/agents/test_repair_cli_review.py \
  tests/agents/test_repair_controller.py \
  tests/agents/test_repair_controller_review.py \
  tests/agents/test_repair_stage_review.py \
  tests/agents/test_repair_context_review.py \
  -o addopts='--import-mode=importlib' -q --tb=short
```

原始结果：`124 passed in 39.92s`。

其中独立新增 `tests/agents/test_repair_case_entry_review.py` 为 22 项：两案例分别测试六种超预算拒绝；四种新增权限参数拒绝；两案例分别测试 registry source、baseline manifest、intent 伪造。异常前后比对真实临时 SQLite 的 task/request/event 原字节，断言无新增模型准备、调用、容器尝试或任务写入。

Ruff 原始结果：`All checks passed!`。

Mypy（本批两个生产文件）原始结果：`Success: no issues found in 2 source files`。

本批测试使用真实临时 SQLite 与快照，模型和执行报告为明确标注的确定性替身；不读取网关密钥、不访问主库、不将其统计为真实模型成功。生产文件与作者冻结清单一致，主目录四个原文件与基线清单一致。

## 2. 生产事故风险推演

无 P0/P1 发现。重点验证的失败路径及控制结果：

| 触发条件 | 应有控制 | 实际证据 |
|---|---|---|
| 将 `--case` 当作文件路径、未知案例或传入额外 root/manifest/scenario/resume | 参数解析前置拒绝，输出固定错误 | CLI 旧测试、新案例测试与独立四组参数反例通过 |
| 选择新案例后试图超过旧 token、调用、候选或时间上限 | 同一 Budget 校验，不构造模型适配器、不写任务 | 两案例 × 六种预算反例通过 |
| 基线属于案例 A，registry 或 manifest/source 属于 B | 在创建任务、预留预算、准备模型前拒绝 | 作者交叉案例测试和独立六项伪造绑定反例通过 |
| 省略 `--case` 的旧调用 | 保持原 output_mismatch 与原单/三角色模式 | 既有 CLI 正向、重复运行新建任务、错误恢复身份测试通过 |

## 3. 详细审计明细

### P0 — 阻断性缺陷

none。

### P1 — 严重缺陷

none。

### P2 — 主要缺陷

none。

### P3 — 次要缺陷

none。

关键实现依据：

- `repair_runtime/cli.py:28–38`：`--case` 仅两个常量，默认 `output_mismatch`；既有模式与预算参数不变。
- `repair_runtime/cli.py:45–55`：先解析宿主 profile 与 Budget；输出上限 8,192 不因新案例放宽。
- `repair_runtime/cli.py:71–85`：相同 `profile.case_id` 同时生成 registry 和 baseline，不接收模型提供的路径、manifest、验收策略或续跑身份。
- `repair_runtime/controller.py:274–288`：首先从 baseline 的持久化 ref 解析 profile，核对 intent、case name、manifest，再验证快照和源文件摘要。失败发生在任务创建之前。
- `repair_runtime/controller.py:289–308`：既有全生命周期 fence、任务创建、预算、deadline 和工具桥保持原有流程；本批没有增加重试、并发 owner 或状态迁移。

## 4. 维度覆盖声明

| # | 维度 | 发现数 | 备注 |
|---|---|---:|---|
| 1 | 架构与边界 | 0 | CLI 只选固定 profile；controller 执行一致性检查，无模型授权扩展 |
| 2 | SOLID 与现代设计 | 0 | 复用固定加载接口和绑定校验，没有重复解释验收规则 |
| 3 | 并发、异步与资源安全 | 0 | 增量在既有 fence 之前校验；没有改变锁/取消/资源释放流程，相关旧回归通过 |
| 4 | 容错与防御性编程 | 0 | 未知参数、伪造绑定、异常映射均 fail-closed，无静默成功 |
| 5 | 性能、伸缩性与计算效率 | 0 | 固定两条 profile 查询，无新队列、列表扫描或网络调用 |
| 6 | 安全与数据合规 | 0 | 不增加任意路径、shell、scenario、resume；参数错误仍脱敏 |
| 7 | 可观测性与运维友好度 | 0 | 固定错误与已有 task/recovery identity 输出保留，无原始源码/密钥输出 |
| 8 | 类型安全与契约表达 | 0 | argparse choices、typed profile 与 ref 校验结合，Mypy 通过 |
| 9 | 可测试性与死代码 | 0 | 10 项作者入口测试及 22 项独立反例；完整目标回归 124 项通过 |
| 10 | 工程规范与一致性 | 0 | Ruff 通过，旧 CLI 测试仅改加载接口接缝 |
| 11 | 数据与事务完整性 | 0 | 无 schema/migration 改动；绑定失败前后数据库原字节不变 |
| 12 | 依赖与供应链治理 | 0 | 无第三方依赖或 lockfile 变更；宿主 profile 为既定 H1 接口 |

## 5. 整改清单

none；无待整改或风险豁免。

## 6. 架构防腐与长效治理建议

1. 保留两个案例的对称预算反例和“拒绝前数据库不变”断言，后续增加固定案例时扩展参数集合；当前维护成本为复用参数化用例。
2. 真实模型 H5 轮次必须冻结全部共同源摘要，单独记录 case/mode/配置，不能将入口合成正向测试作为模型效果；这是既定评估要求，本报告未新增架构范围。

## 7. 审计声明

已审计冻结版本：

| 文件 | SHA-256 |
|---|---|
| `src/agent_workbench/repair_runtime/cli.py` | `33f4586ba3d8b4621b743f8ad7717d712b0c32fb4e3fb2d87b211428c8c78d03` |
| `src/agent_workbench/repair_runtime/controller.py` | `ae6bcc65b5bd1240889107eb74278db95335d01f28f2c5b7ae0a6d878abae678` |
| `tests/agents/test_repair_cli.py` | `8ed5f17ef172b36c1201041cf666e4d94665765ed7c281d08d8bfbd35f4ba40b` |
| `tests/agents/test_repair_case_entry.py` | `7d145f2c94da8a04649dc4253cbe1cf521c1aab603b81ae1353f667b35888dc0` |

独立反例文件：`tests/agents/test_repair_case_entry_review.py`，SHA-256 `a290eb065f49ddda9e558f2ffe796b6e6f7a3d9a3dbbbd870a83a13777ea6b20`。

- 生产实现和作者原测试未修改；只新增评审反例与本报告。
- 未评估：本批 H3 范围内 none。H1/H2 与 H4 另行独立验收，不由本报告背书。
- 已施加豁免：none。
- 无 suspected 发现。本结论只对上述冻结文件和已验证依赖接口有效；后续生产改动需增量复审。
