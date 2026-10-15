# 企业代码质量审计报告

- **审计对象**：P0-06 B3e 固定案例修复 CLI。
- **审计版本**：独立目录 `agent-sandboxes/p006-controller`，`artifacts/b3e-files.json` 的 3 个冻结文件。
- **技术栈**：Python 3.12、argparse、asyncio、Pydantic、既有修复控制器与 SQLite。
- **业务场景**：General SaaS；本机可信单用户工具。
- **审查严苛度**：Mission-Critical。
- **审计时间**：2026-10-14（Asia/Shanghai）。
- **独立评审者**：p006_contracts；未参与该批实现。使用 auditing-enterprise-code-quality。

## 1. 代码质量评估卡

- **综合质量得分**：**100 / 100**，本批无已确认缺陷，不代表真实修复率或整体上线成熟度。
- **上线评估结论**：**Pass：允许 B3e 整合**。
- **范围**：`repair_runtime/cli.py`、顶层 CLI 注册增量、作者 21 个用例；新增独立测试文件 5 项。B3d 控制器依赖已另行评审，本批不重复修改其实现。
- **未评估项**：范围内 none；只读历史 API、恢复命令、网页、真实模型/容器联合实验不在本批，仍需单独验收。

| P0 | P1 | P2 | P3 |
| :---: | :---: | :---: | :---: |
| 0 | 0 | 0 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: none -> 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100 (B3e only)
VERDICT: Pass - no confirmed defect in scoped CLI boundary
NOT ASSESSED: later history/recovery/API/UI and real provider/container experiments
```

## 2. 生产事故风险推演

无已确认 P0/P1。核对了下列边界：

- **SIGINT 发生在模型等待期间**：真实 Python 子进程接收 POSIX SIGINT，控制器等待 owned sender 退出，CLI 返回退出码 2 和可查询 task_id/SHA 的 JSON，保留未知 token 预留；无堆栈或密钥输出。模型是合成 sender，不涉及实际 provider 费用。
- **任务元数据为 verified，但运行器仍要求对账或标记取消**：CLI 仍退出 2，不能只看 task.outcome 就返回成功。
- **快照目录被替换为软链接**：已有安全快照边界拒绝，外部目录没有文件，未调用模型或 oracle。
- **旧 schema / 缺状态 / 缺镜像配置**：预检静态拒绝，无隐式迁移、自动 build/pull 或外部执行；旧记录保留。

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

评审操作位于独立目录；数据库、快照使用真实 pytest 临时目录；模型及 oracle 为合成实现。未写主库、未重启主服务、没有真实 Docker/provider 调用。

原批新旧 CLI 回归：

```sh
uv run --frozen pytest -o addopts='--import-mode=importlib' tests/agents/test_repair_cli.py tests/test_cli.py tests/test_run_persistence.py -q
```

```text
57 passed in 20.33s
```

其中新 repair CLI 21 项，既有 CLI/run persistence 36 项。测试检查两种模式、每次新 UUID、预算上限、无配置/旧库/缺镜像、未知用量、固定错误码、未知参数不回显、末次读取失败保留恢复标识。

独立故障文件：

```sh
uv run --frozen pytest -o addopts='--import-mode=importlib' tests/agents/test_repair_cli_review.py -q
```

```text
5 passed in 4.96s
```

覆盖：快照根软链接、收紧 model_calls 后账本与实际调用一致、两种 verified 但不可成功的标志、真实子进程 SIGINT。SIGINT 测试只验证 OS/asyncio/CLI 的取消链路，不能据此宣称真实容器回收通过。

```text
All checks passed!
3 files already formatted
Success: no issues found in 2 source files
```

分别为 CLI 两个源文件加独立测试的 Ruff/format，以及两个源文件的 `mypy --no-incremental`。

## 4. 维度覆盖声明

| # | 维度 | 发现数 | 备注 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | CLI 只组装既有共享实现，不复制 Agent、预算、oracle |
| 2 | SOLID 与设计 | 0 | configure/main 分开；控制器是唯一模型循环入口 |
| 3 | 并发与资源安全 | 0 | asyncio.run 驱动单任务，store finally 关闭；SIGINT 不返回伪成功 |
| 4 | 容错 | 0 | 缺前置条件静态拒绝，最后 candidates 读取失败保留 task/SHA 与要求对账 |
| 5 | 性能 | 0 | 参数可收紧但不突破固定预算；预检只读 1 条运行；没有无界历史加载 |
| 6 | 安全与合规 | 0 | 无任意源路径、shell、task ID 或 resume；密钥仅环境；无参数/异常原文回显 |
| 7 | 可观测性 | 0 | 安全任务元数据、hash、candidate_ids、cancelled/reconcile；不把费用未知写为零 |
| 8 | 类型与契约 | 0 | Budget 校验与输出上限；输出只从受校验 task 构建，不序列化私有 claim |
| 9 | 可测试性 | 0 | 21 作者+5独立 CLI 用例及旧36回归，真实信号测试无真实 provider |
| 10 | 工程规范 | 0 | 命令注册复用现有 parser 的安全错误策略；默认不迁移、不构建镜像 |
| 11 | 数据完整性 | 0 | 新调用新 UUID，不从旧任务续跑；未知量保留，不重置同一任务预算 |
| 12 | 依赖治理 | 0 | 无新增依赖、下载或镜像供应链变动；不重做全项目供应链扫描 |

## 5. 整改清单

none。本批无需生产代码补丁。

## 6. 架构防腐与长效治理建议

1. 将本次独立子进程 SIGINT 与退出码测试保留为 CLI 回归，防止包装层把未知结果误转成 exit 0；维护成本是现有 5 个测试。
2. 后续 history/recovery 命令另审读权限与精确容器身份，不在本 CLI 加“自动重试原任务”；每次新任务和同任务恢复是不同操作。
3. 产品文档明确 `repair` 当前只处理公开固定案例的隔离副本；真实模型修复率、单/三角色优劣需后续对照实验提供证据。

## 7. 审计声明

- 只批准以下冻结版本及已评审 B3d 依赖的组合；后续修改需按影响范围复审。
- 本批没有提供任意用户项目修复、自动接受补丁、历史恢复或网页执行修复能力。
- 豁免 none；未使用 suspected 发现驱动结论。
- 独立测试 SHA：`tests/agents/test_repair_cli_review.py` → `0d4b8dc4964b629dc4718b4ae5d8458a2663dba244bdb8759092337a12326ee6`。

```json
{
  "src/agent_workbench/cli.py": "db5bc4a6792daf551f4b78da5b511c3278abb884198efef1596312606b55fded",
  "src/agent_workbench/repair_runtime/cli.py": "bf43b086851a0c1f21d334d0748f1bfc3410c5937a12af65a37d9938ae5f0d78",
  "tests/agents/test_repair_cli.py": "09203575415c3b57a3636b87e2c1f5b6799bbfc65d813f5ef638d62204b2e652"
}
```
