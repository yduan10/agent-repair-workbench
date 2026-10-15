# 企业代码质量审计报告：P0-06 B3a 模型修复契约

- **审计对象**：`repair_contracts/`、四角色 P0-06 契约与提示词、相应测试，以及 `pyproject.toml` 的 single 测试发现路径。
- **审计版本**：2026-10-14 工作树，文件 SHA-256 见末尾；不是对整个未提交工作树背书。
- **技术栈**：Python 3.12、Pydantic、pytest、JSON Schema。
- **业务场景**：General SaaS。
- **审查严苛度**：Mission-Critical。
- **审计时间**：2026-10-14。
- **独立性**：实现者 `p006_contracts`，评审者 `p006_contract_review`。评审者仅新增独立测试和本报告，提示词修复由主实现者完成。

## 1. 代码质量评估卡

- **综合质量得分**：**100 / 100 — 健康**（修复后无未解决发现；此分数并非功能完整度）。
- **上线评估结论**：**Pass — B3a 契约批次通过，可接入下一批运行器开发**。不代表 P0-06 端到端修复已通过验收。
- **审计范围**：21 个实施清单文件（20 个文件共 753 行，另加 pyproject 一行发现路径增量），新增 1 个独立反例文件。
- **未评估项**：本批契约范围内 none。模型网关、持久运行器、T06/T07 实际执行、真实模型效果及网页不属于本批，不能凭本报告验收。

| P0 阻断 | P1 严重 | P2 主要 | P3 次要 |
| :---: | :---: | :---: | :---: |
| 0 | 0 | 0（1 项已修复） | 0 |

```text
STRICTNESS:   Mission-Critical
SCENARIO:     General SaaS
DEDUCTIONS:   unresolved P0×0, P1×0, P2×0, P3×0 → Σ = 0
RAW SCORE:    100
CAP APPLIED:  none
FINAL SCORE:  100 / 100
VERDICT:      Pass — bounded contract batch only
NOT ASSESSED: none within the declared batch
```

初审 P2×1 扣 3 分，97/100；Mission-Critical 的 P2 预算为零，因此修复前为 Conditional Pass。提示词 1.1 修复后闭环，无豁免。

## 2. 生产事故风险推演

none：没有确认的 Defect P0/P1。模型伪造接受结论、跨角色请求变更工具、向证据嵌入控制字段、重复 JSON 键、超长或非法编码补丁等均在解码边界拒绝。权限 schema 是第一道边界；真实资源归属、幂等、预算与最终判定仍必须由后续宿主运行器校验。

## 3. 详细审计明细

### P0 — 阻断性缺陷

none。

### P1 — 严重缺陷

none。

### P2 — 主要缺陷

#### P2-1. 通用提示词禁止 paths，与 T03 必填读取路径冲突（已修复）

- **位置**：四角色 `prompts/p006.txt` 初审第 6–7 行；T03 `controlled_tools/contracts.py` 的 `ReadSource.relative_path`。
- **维度**：8 类型安全与契约表达。
- **置信度**：[confirmed]，指令与必填字段直接冲突；未声称测得真实模型失败率。
- **失效机制**：严格遵守“Never provide … paths”的模型无法同时构造需要 relative_path 的 read_source 请求，可能拒绝取证或产生无效请求，消耗修复预算。
- **最小修复**：主实现者将四份提示词升为 1.1，改为“Never choose output/write paths. For read_source use only the host-provided relative_path.”，并从通用禁止字段段移除 paths。
- **验证**：逐份核对修改后的公共段和 T03 schema；修复后运行下述 155 项测试通过，T06/T07 仍没有可由模型指定的写入路径。实际模型服从程度在 B3 真实验收中另测。

### P3 — 次要缺陷

none。

### 执行证据

所有命令在项目根目录执行。没有调用模型、Docker 或写主数据库。

```sh
uv run --frozen pytest tests/agents/test_repair_contracts_review.py tests/agents/test_repair_contracts.py src/agent_workbench/agents/diagnosis/tests src/agent_workbench/agents/repair/tests src/agent_workbench/agents/verification/tests src/agent_workbench/agents/single/tests
```

实际输出：

```text
155 passed in 0.24s
```

其中新契约原有 119 项；独立新增 14 项；另含 22 项原有角色测试。此前新契约加独立反例单独运行的实际输出为 `133 passed in 0.23s`；这些数字有重叠，不相加。

独立反例覆盖：导出 JSON Schema 的 8 组 T06/T07 角色权限；相同 evidence_id 配不同 hash 的拒绝；整个决策 repr 不泄露补丁；3 类控制字段藏入 evidence 的拒绝；嵌套重复键的拒绝。

```sh
uv run --frozen ruff check src/agent_workbench/repair_contracts src/agent_workbench/agents/diagnosis/repair_contracts.py src/agent_workbench/agents/repair/repair_contracts.py src/agent_workbench/agents/verification/repair_contracts.py src/agent_workbench/agents/single tests/agents/test_repair_contracts.py tests/agents/test_repair_contracts_review.py
uv run --frozen ruff format --check tests/agents/test_repair_contracts_review.py
uv run --frozen mypy --no-incremental src/agent_workbench/repair_contracts src/agent_workbench/agents/diagnosis/repair_contracts.py src/agent_workbench/agents/repair/repair_contracts.py src/agent_workbench/agents/verification/repair_contracts.py src/agent_workbench/agents/single/repair_contracts.py
uv run --frozen pytest --collect-only -q
```

实际输出分别为：

```text
All checks passed!
1 file already formatted
Success: no issues found in 8 source files
```

默认全仓收集退出 0，包含 `src/agent_workbench/agents/single/tests/test_repair_contract.py: 2`。这是收集验证，不是全仓测试运行。pyproject 相对交接清单仅 single testpath 排列位置不同，含义一致。

## 4. 维度覆盖声明

| # | 维度 | 未解决发现 | 结论 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | 各角色独立，通用契约不执行工具，旧 P0-05 解码不扩权 |
| 2 | SOLID 与现代设计 | 0 | T01–T05 复用类型；T06/T07 与候选权威字节限制保持一致 |
| 3 | 并发、异步与资源安全 | 0 | 不适用：本批无并发任务、网络或资源句柄 |
| 4 | 容错与防御性编程 | 0 | 复用有界严格 JSON 解码；对外固定错误代码 |
| 5 | 性能与伸缩性 | 0 | 64 KiB 消息、20 层 JSON、32 引用、8 KiB UTF-8 片段有界 |
| 6 | 安全与数据合规 | 0 | extra forbid、冻结 DTO、补丁 repr 隐藏；整对象禁止持久化的要求明确 |
| 7 | 可观测性与运维 | 0 | 契约层只出固定错误；运行期追踪与脱敏由后续运行器负责 |
| 8 | 类型安全与契约表达 | 0 | 原 P2-1 已修复；角色 schema 与拒绝 verdict 的边界有反例 |
| 9 | 可测试性 | 0 | 确定性测试不依赖外部服务；独立 JSON Schema 和旧角色回归通过 |
| 10 | 工程规范 | 0 | per-role 目录、pytest 发现、Ruff/mypy 通过 |
| 11 | 数据与事务完整性 | 0 | 不适用：本批不写数据库/文件、不签发执行身份 |
| 12 | 依赖与供应链 | 0 | 没有新增依赖；pyproject 仅测试路径增量 |

## 5. 整改清单

| ID | 严重级 | 负责人 | 截止 | 状态 |
|---|---|---|---|---|
| P2-1 | Defect P2 | Root 实现者 | B3a 接入前 | 已修复、复审通过 |

无延期、无风险接受。

## 6. 架构防腐与长效治理建议

1. 保留全部角色×工具解码矩阵和独立 JSON Schema 权限用例；新增角色时成本为增加一行角色配置与对应负例，防止模型 schema 与实际权限漂移。
2. 后续运行器以宿主登记/授权为准，不能把通过本 schema 当作执行许可；集成测试需覆盖伪造引用、重复请求、预算耗尽与跨任务 candidate_id，防止结构正确但未授权请求执行。属于既定后续门禁，不是本批新增平台功能。

## 7. 审计声明

- 下列文件哈希构成本次版本证据；改变这些文件需增量复审。
- 既有 codec/contracts/候选验证器按直接依赖读取；其整个执行子系统不在本批重新验收。
- 未施加豁免；没有 suspected 发现。
- 本报告不证明模型已生成有效候选，不证明持久预算、真实隔离回归或 UI 已接通，不修改 P0-06 父任务完成状态。

### SHA-256 文件清单

审计清单规范 JSON 摘要：`d7ce758dfd25dbb282e613f5e6d3af52b05c4abddc412ebc70706ffa0e006717`。

```json
{
  "pyproject.toml": "4f557ea58964eae142f9c497dcdad987f56018843129699fecd3c18fe709f361",
  "src/agent_workbench/agents/diagnosis/prompts/p006.txt": "eb921d6f60937873b7883271b98d6808b8a789880370647a5ac0274758ad6f04",
  "src/agent_workbench/agents/diagnosis/repair_contracts.py": "758112ea2926f5ad500beb38aa8a6b411ea3acdbbb433b16a7c4db5b44d44712",
  "src/agent_workbench/agents/diagnosis/tests/test_repair_contract.py": "3862e632991e3a9f13a82fbd46677475d5d1a7c854abbcb95b396f1d0a9d015b",
  "src/agent_workbench/agents/repair/prompts/p006.txt": "93f2ff0992a2686e9106efbdd8c30454925bcb0ff94ae1ecf716e9c36252900c",
  "src/agent_workbench/agents/repair/repair_contracts.py": "efb866cf6a37ddec670ab72963238306197ea12b29368de4255d250931d86621",
  "src/agent_workbench/agents/repair/tests/test_repair_contract.py": "4d44576cfeaf2e7569577636a9e2835db6019236792cfc420c2712c925948963",
  "src/agent_workbench/agents/single/README.md": "d302f9682098ec09a28d029c71081807e97417b2297ceeda11f11395b93ad317",
  "src/agent_workbench/agents/single/__init__.py": "848a30f3123c57c1dabb4066a5eb294dd4fbae18b0619b36d0675f94b6dc5dbe",
  "src/agent_workbench/agents/single/prompts/p006.txt": "a74145e058394d02c7135eb7ccecb547002206b88d9f7383bc87acf116c3004a",
  "src/agent_workbench/agents/single/repair_contracts.py": "89f4fd8af3a8d187414519698637d712b7a11b1e48df2fb3e4a926aa90691ccf",
  "src/agent_workbench/agents/single/tests/test_repair_contract.py": "b86a2794238309ef94afd20db4829ad47d3a510633ffb875ed0b493c5a80d8be",
  "src/agent_workbench/agents/verification/prompts/p006.txt": "4b8f552d973762c87d2fdea0460e628418789cc30578dc2f461be9ed876b7ec4",
  "src/agent_workbench/agents/verification/repair_contracts.py": "e7003d3ef874c233c88ed053b36cb2e36936cd230429c2ed9a5ea3503135a0f8",
  "src/agent_workbench/agents/verification/tests/test_repair_contract.py": "5618755921b87ac1e918ce998c40a7f2e61c9a01332fd40fc1f7483e5f121d52",
  "src/agent_workbench/repair_contracts/README.md": "b169c91cf5341773fce88476ada914a608aec6e2ce2d50978d5cc3a832659f52",
  "src/agent_workbench/repair_contracts/__init__.py": "e4bf9fb23b31a70d7cc93765af285c21c98b83d31f8dd14300e1039b05e635b4",
  "src/agent_workbench/repair_contracts/codec.py": "122ea142d370f008fc87549e3b88126b70fdeac196d3bad9acbbce55f36550ee",
  "src/agent_workbench/repair_contracts/common.py": "390fe0c762c679378a21eeadd870f0b4c9e8a9df9e6f50da89ea944df1fa8969",
  "src/agent_workbench/repair_contracts/tools.py": "a7b1256ad8aec318460329a8132d3966158b5896c4d6fecc417cca88c87e55cd",
  "tests/agents/test_repair_contracts.py": "5937ac6e63b2a890c49c9fa61ac2c8102f75e5b9c18ae4165d44a35371a9e984",
  "tests/agents/test_repair_contracts_review.py": "0373f52e453d55b8958bdcdc7beabc1e1465b1094c57f57cddf6ee94a9a060e0"
}
```
