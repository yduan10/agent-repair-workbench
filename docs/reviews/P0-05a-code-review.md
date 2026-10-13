# 企业代码质量审计：P0-05a 后端契约与纯策略

- **范围**：`orchestration/*`、`controlled_tools/*`、三角色 contracts/init/角色单测；catalog 路由挂载；pyproject 测试发现和mypy测试排除；`tests/agents`、`tests/tools`。前端、真实模型/工具运行、存储迁移均非本批实现。
- **快照**：独立 `<review-workspaces>/p005a-code-review`；初稿SHA清单 `P0-05a-code-initial-snapshot.json`。
- **技术栈**：Python3.12.13、Pydantic2.14.1、FastAPI；现有uv锁，无新第三方依赖。
- **依据**：AGENTS、docs01/17/18；auditing-enterprise-code-quality，General SaaS / Mission-Critical。

## 1. 代码质量评估卡

**复审 100 / 100，后端本批范围 Pass。** 初审91分/3项Defect P2已全部修复，类型门禁差异已消除；初审记录保留如下，不将其误认为当前未闭项。前端仍独立评审，不能由本报告推出P0-05运行功能已完成。

| P0 | P1 | P2 | P3 |
|---|---|---|---|
| 0 | 0 | 0 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 0 remaining findings (initial 3 P2 × 3 = 9, all closed)
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: scoped Pass — no unresolved defect or backend gate
NOT ASSESSED: frontend (separate batch), model runtime/tools/storage (not implemented in this batch)
```

初审独立实际运行（历史）：原77项定向测试通过（含既有API）；9项独立反例全部失败，准确暴露3类遗漏。Ruff通过、uv lock --check通过；mypy普通及`--no-incremental`都在codec.py:17/18/19报3条unused-ignore（40源码文件），不能把实现方先前通过当作本次独立通过。

## 2. 事故风险推演

无P0/P1；当前代码没有模型运行、文件打开或工具执行，不能把本轮契约遗漏写成已经发生的越权或副作用。

- R01允许错误类型版本通过纯CAS比较；会掩盖未来调用方序列化错误，但本批不具备并发持久化执行。
- R02允许C1控制字符作为合法路径；当前只生成授权键，实际文件打开仍未实现。
- R03为公共泛型decoder的非有限数门禁遗漏；当前角色/工具具体schema没有float槽位，不能声称现有角色JSON已穿透为危险数据。

## 3. 详细审计明细

### P0

none。

### P1

none。

### P2 — P005A-R01：版本比较隐式接受bool与float

- **位置**：`src/agent_workbench/orchestration/policy.py:103–107`。
- **维度/置信度**：8类型契约；[confirmed]。
- **反例**：queued revision0，传expected_revision=False或0.0仍能transition；checking revision1传True或1.0也成功。
- **原因**：Python相等比较将bool/float与int视为相同，函数未像其他版本边界执行严格类型检查。
- **最小修法**：比较前要求`type(expected_revision) is int`且在允许范围内，拒绝时固定PolicyError码。
- **验证**：独立4项参数化反例应从DID NOT RAISE变为通过，保留正常int/stale路径。

### P2 — P005A-R02：相对路径未拒绝C1控制字符

- **位置**：`src/agent_workbench/controlled_tools/contracts.py:19–26`。
- **维度/置信度**：8契约表达、6输入边界；[confirmed]。
- **反例**：完整合法ReadSource JSON的relative_path加入U+0080/U+0085/U+009F，decode均接受。
- **原因**：检查只覆盖ordinal<32与127，遗漏128..159；docs18的“拒绝控制字符”未满足。
- **最小修法**：覆盖C0、DEL和C1（例如`ord(char)<32 or 127<=ord(char)<=159`），保留普通中文路径。
- **验证**：3个真实ReadSource JSON反例固定INVALID_MESSAGE；现有中文target_key测试继续通过。

### P2 — P005A-R03：泛型JSON解码遗漏指数溢出

- **位置**：`src/agent_workbench/orchestration/codec.py:42–54`。
- **维度/置信度**：8契约、4防御性编程；[confirmed]。
- **反例**：`decode(b'1e999', TypeAdapter(float))`返回inf，负指数溢出返回-inf。
- **原因**：json.loads的parse_constant仅处理NaN/Infinity字面量，不处理普通数字转换为float时的溢出；预检树没有finite检查。
- **最小修法**：预检树每个float明确isfinite，统一INVALID_MESSAGE；拒绝完整消息而非夹断数值。
- **验证**：正负溢出两项反例，另保留正常有限数字与严格具体角色模型行为。

### P3

none。mypy门禁已有工具精确报告，不额外计作风格缺陷。

## 4. 维度覆盖声明

| # | 维度 | 发现/判断 |
|---|---|---|
| 1 | 架构与边界 | 三角色只声明契约，控制器持有策略，模型不带task/role/权限字段 |
| 2 | SOLID | 共用工具/类型，无角色间实现导入；无动态插件注册 |
| 3 | 并发资源 | 纯函数和只读catalog，无执行器/DB；缓存bytes无写任务副作用 |
| 4 | 容错 | R03泛型decode边界；错误统一固定码、不回显Pydantic输入 |
| 5 | 性能 | 64KiB/深度20、200行、有限集合/修复字节预算 |
| 6 | 安全合规 | 精确目标hash包含tool与版本/参数；完整证据ID+hash/任务绑定；R02 |
| 7 | 可观测性 | catalog明确runtime_available=false；不将schema算执行成功 |
| 8 | 类型与契约 | R01/R02/R03；其余strict/frozen/extra forbid及tuple边界清晰 |
| 9 | 可测试性 | 77既有用例通过；9独立反例可复现，角色路径纳入发现 |
| 10 | 工程规范 | 锁/Ruff通过；mypy初审3条unused-ignore已删除；无缓存40文件通过 |
| 11 | 数据完整性 | Summary双ID、revision、UTC/终态、预算、预留、未知费用有交叉校验；实际保存留后续 |
| 12 | 依赖治理 | 本批无新依赖，复用已有锁；不重复宣称新漏洞扫描 |

## 5. 整改清单

| ID | 严重级 | 负责人 | 截止 | 状态 |
|---|---|---|---|---|
| P005A-R01 | Defect P2 | root | P0-05a完成前 | closed：严格int及范围门禁，4反例通过 |
| P005A-R02 | Defect P2 | root | P0-05a完成前 | closed：C0/DEL/C1覆盖，3反例通过 |
| P005A-R03 | Defect P2 | root | P0-05a完成前 | closed：预检树float finite检查，2反例通过 |
| mypy gate | 自动门禁 | root | P0-05a完成前 | closed：去除unused ignores，--no-incremental通过 |

## 6. 长效治理建议

1. 维持公共decoder与具体schema两层测试：通用限额/格式拒绝不依赖“当前模型恰好没有对应字段”。
2. 版本与预算这些Python入口也使用严格原始类型门禁，防止bool/int子类型关系悄悄扩大契约。
3. 后续真实T01～05网关必须再核对物理存在性、归属和摘要；精确授权集合不是文件安全打开或已执行证明。本批没有替后续实现提前背书。

## 7. 审计声明

实现只读；反例在独立 `review/tests/test_p005a_strict_boundaries.py`，无模型调用、凭据读取、容器执行或数据库写入。初稿快照SHA `aa8fa26a6901dd99f118fd3469e4a433c1b29466da9df0028e8cd6ef5b8adbff`。本批范围约1100行按父任务拆分，前端另审。只读catalog真实TestClient GET/来源限制/POST405/不创建state目录已运行；R03明确仅泛型边界问题，不误称当前角色输出已含非有限浮点。修复后需重跑对应9项和原77项、类型门禁，再冻结最终SHA。

## 修复后复审与冻结

三文件最小增量已逐行复核：transition先严格检查expected_revision真实int及0..1000000；relative_path拒绝C1；codec对预检树float检查math.isfinite。没有扩大工具权限、修改验收规则或添加执行器。修复测试正式路径 `tests/agents/test_strict_boundaries.py` 与独立9项反例AST完全相同（仅格式化），这9项只计数一次。

```text
uv run --frozen pytest src/agent_workbench/agents/diagnosis/tests src/agent_workbench/agents/repair/tests src/agent_workbench/agents/verification/tests tests/agents tests/tools tests/test_api.py
86 passed in 1.62s
uv run --frozen mypy --no-incremental
Success: no issues found in 40 source files
uv run --frozen ruff check src/agent_workbench/orchestration src/agent_workbench/controlled_tools src/agent_workbench/agents tests/agents tests/tools
All checks passed!
uv lock --check
Resolved 55 packages in 8ms
```

角色目录定向collect为22项，3个目录与pyproject默认testpaths逐项核对一致；未冒称在缺少既有实验目录的审查副本执行了全仓默认collect。独立29文件最终清单 `P0-05a-code-snapshot.json`，逐项哈希与主目录一致；清单SHA256 `ed9be2e49aa2ae78554855591fa6ab6350bcfb079ae69e5dec626cc75103798a`。

最终后端批次无未闭缺陷，零豁免。真实模型、工具handler、物理产物/授权校验、预算执行控制、存储CAS和前端未在本批实现，不把这些后续内容计成已通过。当前新增API仅返回固定schema目录与runtime_available=false，已验证不读取模型环境、不创建状态目录、不提供执行POST。
