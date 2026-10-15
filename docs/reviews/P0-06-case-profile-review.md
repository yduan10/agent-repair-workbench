# 企业代码质量审计报告

- **范围**：P0-06 H1/H2 + H09，`p006-heldout/artifacts/heldout-h12-files.json` 的 20 个冻结文件，约 1200 行增量。H3 入口与 H4 展示由其他独立评审者负责，不在本报告批准范围。
- **评审者 / 日期**：p006_contracts（未参与实现）/ 2026-10-14；使用 auditing-enterprise-code-quality。
- **技术栈 / 场景 / 严苛度**：Python 3.12、Pydantic、SQLite、Docker / General SaaS / Mission-Critical。

## 1. 代码质量评估卡

**Pass：允许 H1/H2/H09 整合。100 / 100，未发现确认缺陷。** 分数只对应本范围扣分，不代表模型修复成功率或泛化。

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: none -> 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100 (H1/H2/H09 only)
VERDICT: Pass
NOT ASSESSED: H3 entry, H4 UI, 12-run model evaluation, cross-project generalization
```

P0/P1/P2/P3 均为 0。设计中的独立变体已实现为同服务 `counter_offset`；仍不得称为真实业务或跨仓库泛化验证。

## 2. 生产事故风险推演

- **原案例与偏移案例规则混用**：按基线持久 manifest/source/tree 精确选出单个失败指纹。原案例收到 count_value 或变体收到 count_type 均不能授权修复；不是两类错误的并集。
- **修复后两个案例产生相同源文件**：独立反例实际创建两种候选，file hash 相同，但 baseline/manifest 不同；交叉 diff、ComparisonPlan 与伪 manifest 快照仍拒绝。
- **bridge 创建后替换 registry**：每次执行仍重验持久基线、case、manifest、source，拒绝且不增加工具接收记录。
- **新 profile 文件变化未纳入 oracle**：独立只读模拟文件内容变化，ORACLE hash 改变、verify_oracle=false；SUITE 仍相同，不遗漏新增可信依赖。
- **保留变体宿主中断/未知费用**：H09 真实临时账本加 Docker double 验证精确资源恢复、错标签/错源码不删、unknown 预算保留及不续跑。

## 3. 详细审计明细

### P0 — 阻断性缺陷

none。

### P1 — 严重缺陷

none。

### P2 — 主要缺陷

none。

### P3 — 次要缺陷

none。

### 独立测试与实际证据

```sh
uv run --frozen pytest tests/test_repair_case_profile_review.py tests/test_repair_case_profiles.py tests/test_repair_case_ledger.py tests/test_repair_case_recovery.py tests/test_candidate_snapshots.py tests/test_candidate_comparison.py tests/test_candidate_comparison_review.py tests/test_repair_reproductions.py -o addopts='--import-mode=importlib' -q --tb=short
# 169 passed, 3 skipped in 7.56s
```

含本轮独立 6 项反例：相同正确候选字节仍保持案例 provenance、两种 profile 的错 snapshot/空步骤报告拒绝、新可信模块变化使 oracle 失效、两种 profile 的运行中 registry 变更在接收前拒绝。3 项旧快照 Docker 用例因其显式开关未启用而跳过，不计通过。

首次独立测试的两项断言把 `Mutation` 的可选 request/candidate 回执字段与仅含 task 的读取结果直接比较，失败原因属于测试过度约束；改为比较真实 task、task SHA 与持久状态后全量上述用例重跑通过。生产代码未改。

```sh
AWB_HELDOUT_DOCKER=1 uv run --frozen pytest tests/test_repair_case_docker.py -o addopts='--import-mode=importlib' -q --tb=short
# 10 passed in 27.73s
```

独立重跑两次真实 T05、八次真实四容器 T07，共 34 个容器全部 cleanup=removed。两种基线分别严格观测三个 count_type/count_value，pass 基线通过；人工正确候选通过，常量1、int偏移、破坏pass候选均拒绝。人工候选测试不能计模型修复成功。

```text
All checks passed!
1 file already formatted
Success: no issues found in 11 source files
```

为本批 11 个生产源文件与独立测试 Ruff、独立测试 format，以及 11 源文件 `mypy --no-incremental`。测试、快照、SQLite 位于 sandbox 临时目录；无主库、密钥或模型访问。作者及 root 全仓测试结果未当成本评审独立运行计数。

## 4. 维度覆盖声明

| # | 维度 | 发现数 | 核查结果 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | 两个固定宿主 profile，P0-05 loader 仍只接受原两项；不开放任意案例 |
| 2 | SOLID 与设计 | 0 | profiles 为不可变轻量元数据，bindings 独立验证，避免 registry/store 循环依赖 |
| 3 | 并发与资源安全 | 0 | 不改 claim/CAS/fence；保留快照逐级拒绝链接与原子发布 |
| 4 | 容错 | 0 | unknown/清理失败保守保留；缺步骤、混合规则、版本不符不能通过 |
| 5 | 性能 | 0 | 封闭二项登记，无外部扫描或新无界读取 |
| 6 | 安全与合规 | 0 | 模型不接收 profile规则；root/path不成为新模型参数；T05证据如实来自执行 |
| 7 | 可观测性 | 0 | 新初始 envelope 静态通过，未伪造类型失败；manifest标识案例可追溯 |
| 8 | 类型与契约 | 0 | baseline强制显式传入result_outcome；嵌套报告重新验证 |
| 9 | 可测试性 | 0 | 169确定性/回归通过+10真实Docker，独立6反例 |
| 10 | 工程规范 | 0 | 不改prompt1.4、输入序列/断言、预算/工具schema；旧默认保持 |
| 11 | 数据与事务完整性 | 0 | 无迁移重写；持久manifest绑定规则；相同候选hash不能跨case混用 |
| 12 | 依赖与供应链治理 | 0 | 新3模块进入ORACLE闭包；SUITE保持、ORACLE更新；无新第三方依赖 |

## 5. 整改清单

none，无生产补丁要求。独立测试文件须随本批整合保留。

## 6. 长效治理建议

1. 保留 case→精确指纹的互斥反例，未来新增案例不能把规则简化为“任意失败”或多错误码并集。
2. 历史 recorded_outcome 保留，旧 oracle 的当前验证按版本失配处理；禁止重新盖上新版本通过标签。
3. 整合 H3/H4 后重新冻结全部可信依赖，再做开发样本与保留变体各单/三3次的12次实验。失败完整入账；本批 Docker 人工补丁不计入模型效果。

## 7. 审计声明与冻结版本

20 个文件均与作者冻结清单一致，生产源码只读。独立测试在 sandbox：`tests/test_repair_case_profile_review.py`，SHA-256 `76cb79e58b90ea824a600fe67a7c6fe2a7cb00cfd314cc5986572e37ce22f63f`。无豁免。H3/H4与真实模型评估须各自完成门禁。

```json
{
  "src/agent_workbench/repair_cases/__init__.py": "7689dcf57eb39b6d92f3fb7d745128d966244d4a0a70c5c4f366d4b53b457e83",
  "src/agent_workbench/repair_cases/profiles.py": "06eec28ffc6e4a0f09607bf43a7c6189f9c1bc5c6ca5affb81cbba29db016b73",
  "src/agent_workbench/repair_cases/bindings.py": "2fba0ea15dbd25510a1ef672bcce4e3e93dd77b3470b4e6ed31c4353ae104527",
  "src/agent_workbench/controlled_tools/resources.py": "007d6a5d3ea4ba25f1563c7bc28d46aaed3898390a39c09c483736fc23d16c72",
  "src/agent_workbench/candidates/snapshots.py": "2f0fc194667ec3977108735fa5e3b63e29836d14f66f0e03c71c9c77bbf89300",
  "src/agent_workbench/candidate_execution/oracle.py": "f4802352d776a51a91beaaeea351b2b75b4a84515cab422d39c5ba829177341e",
  "src/agent_workbench/candidate_execution/compare.py": "b9f57c4e502a954ae625d6e3bb7b25ebc4209b1858740834ef38c5f9dd183428",
  "src/agent_workbench/repair_store/reproduction_models.py": "7ce3c76e7b1d8ade8d2e3204e80079ccb5fb84a38c4b5e1deda76542051b6784",
  "src/agent_workbench/repair_store/reproductions.py": "0d361a725b173d60107721938be6b822b30bf81c5e2bc9c1948d5c62c05ab87d",
  "src/agent_workbench/repair_runtime/feedback.py": "45ac89e6c5ced3d1a1951cb2f16e0516aa0a48b13bab789c51adbf0e60d26ef1",
  "src/agent_workbench/repair_runtime/tools.py": "8e0211d8b191866014e53e970c9914fa8fca76c1bb994cbae3172d1e331841e9",
  "examples/repair/counter_offset/manifest.json": "81b89fc6fddfa5b1dd1cf173d2a788cedf8646ee3c290b4511b7eb3373b55465",
  "examples/repair/counter_offset/counter_offset.json": "758339422bcc33ac2cf967d6722d420df2d5e6a0bbfef38008131c854b26e280",
  "examples/repair/counter_offset/source/server.py": "b8568ee1bd93e6a35b2015380dba05994c318132ae66841d3d6ccbc1000d96ee",
  "tests/test_candidate_comparison.py": "56eb2ad759dbfee6dc8775339f5e42d609320dd4d857baa39b580d11fd6c792e",
  "tests/test_candidate_comparison_review.py": "c355f5fb0c1334c88f033a4a96b50fae23e158fd6c35a14973c3c935ca215a92",
  "tests/test_repair_case_profiles.py": "80c0b52525ad6da6b63773ed5b7c56963dad0494ac8b3979c7411290a18e5868",
  "tests/test_repair_case_ledger.py": "6fb0ada76aacd783a5d2e436c3f8321d4eaf1c3ee3ca09296bf7ebcbf005a8dd",
  "tests/test_repair_case_docker.py": "6425539ca0abd1847d013f836b7de5d44afbd5d2f513ffa39b50c4691dca34ff",
  "tests/test_repair_case_recovery.py": "5274d64f285d4fd2f69bc62569ef33d2f85fe0559bf45448f2ea7d8d9218d85c"
}
```
