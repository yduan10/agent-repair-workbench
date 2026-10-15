# 企业代码质量审计报告

- **审计对象**：P0-06 recovery CLI，`agent-sandboxes/p006-recovery/artifacts/recovery-files.json` 的 7 个冻结文件，约 900 行；未改 store。
- **评审者**：p006_contracts，未参与实现；使用 auditing-enterprise-code-quality。
- **日期 / 场景 / 严苛度**：2026-10-14 / General SaaS / Mission-Critical。
- **技术栈**：Python 3.12、asyncio、POSIX flock、Docker CLI、既有 SQLite 修复账本。

## 1. 代码质量评估卡

**Pass：允许本批整合。100 / 100，无已确认缺陷。** 分数只反映本批缺陷扣分；恢复退出码 0 表示资源清理和账本对账完成，不表示候选修复成功。

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: none -> 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100 (recovery CLI only)
VERDICT: Pass
NOT ASSESSED: automatic watchdog, web recovery actions, adversarial same-UID operator
```

P0 / P1 / P2 / P3 均为 0。所有范围内维度已检查；宿主死亡后自动 watchdog、网页恢复、多租户/不可信本地操作员不在本批。

## 2. 生产事故风险推演

- **活 owner 被 SIGSTOP**：真实进程持锁，恢复返回 OWNER_ACTIVE，不碰 Docker；SIGKILL 后锁释放，才能开始检查孤儿资源。
- **容器删除成功但响应丢失**：保持原 pending 账本和预算，不宣称对账成功。再次显式 apply 看到 absent 后才收束为 unknown，没有第二次删除。
- **预检或删除后容器被同名替换**：绑定初次完整 ID；后续出现另一 ID 拒绝，替换资源不被删除，也不将其误判为 absent。
- **任一目标身份不匹配**：全目标预检完成后才删除，因此不会先删前三个再发现第四个属于未知资源。
- **取消或清理后抢锁**：取消传播，原状态保留；重新获取 fence 和 CAS 后才写对账，新 owner 或新 revision 不能被旧恢复覆盖。

## 3. 详细审计明细

### P0 — 阻断性缺陷

none。

### P1 — 严重缺陷

none。

### P2 — 主要缺陷

none。

### P3 — 次要缺陷

none。

### 独立验证证据

```sh
uv run --frozen pytest tests/test_repair_recovery_review.py tests/test_repair_recovery.py tests/test_repair_reproductions.py tests/test_repair_comparisons.py -o addopts='--import-mode=importlib' -q --tb=short
# 93 passed in 8.99s
```

93 项 = 本批作者 19 项、既有账本 68 项、独立新增 6 项。独立用例包括删除 ACK 丢失、所有 Docker 操作持有 fence、删除后替换、删除期间取消、两个扫描 ID、非 ASCII 扫描输出。均使用真实临时 SQLite 与快照、Docker double。

```sh
AWB_REPAIR_RECOVERY_DOCKER=1 AWB_REPAIR_RECOVERY_IMAGE_ROOT=<project-root> uv run --frozen pytest tests/test_repair_recovery_docker.py -o addopts='--import-mode=importlib' -q --tb=short
# 2 passed in 3.84s
```

独立重跑的两项真实 Docker 测试：T05 baseline、T07 candidate；真实宿主进程持久登记身份后创建 Running 容器，经历 SIGSTOP 拒绝恢复、SIGKILL、只读 inspect、显式 apply、重复 apply。预算完全保留；非终态最终为 outcome_unknown，历史终态不重写。没有模型调用，没有主数据库写入。

证据位于 sandbox：

- `artifacts/recovery-docker/c0d61f83-de21-4754-b679-98feea9b6689/acceptance.json`（T05）。
- `artifacts/recovery-docker/58fbd5db-8b8a-45ff-ac20-2e2d29dee1e4/acceptance.json`（T07）。

```text
All checks passed!
5 files already formatted
Success: no issues found in 5 source files
```

对应 recovery 包、CLI 与独立测试的 Ruff，recovery 包与独立测试的 format，以及包/CLI 的 fresh mypy。独立测试初次仅 import 排序由 Ruff 修正，不改生产代码。

## 4. 维度覆盖声明

| # | 维度 | 发现数 | 核查结果 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | CLI 仅显式恢复，不续跑模型/T05/T07；账本语义复用原 store |
| 2 | SOLID 与设计 | 0 | inventory、service、CLI 分离；不复制状态迁移规则 |
| 3 | 并发与资源安全 | 0 | 检查/删除全过程 fence；对账重新锁与 CAS；完整容器 ID 绑定 |
| 4 | 容错 | 0 | 全目标预检，未知保守保留；ACK 丢失可再次显式检查 |
| 5 | 性能 | 0 | 最多 80 身份、120 秒异步期限、沿用每条 Docker 命令超时；无全局扫描 |
| 6 | 安全与合规 | 0 | 精确名称/标签/镜像/挂载/场景/快照核验，错误固定且不泄露路径 |
| 7 | 可观测性 | 0 | inspect/apply、资源状态、待对账、账本对账分开；退出码不宣称修复有效 |
| 8 | 类型与契约 | 0 | UUID 校验、DTO 固定资源状态；CLI 无任意 argv、镜像或路径输入 |
| 9 | 可测试性 | 0 | 93 确定性测试及两项真实宿主信号/容器测试独立重跑 |
| 10 | 工程规范 | 0 | 默认 inspect；--apply 明确副作用；不隐式迁移、构建镜像或查模型配置 |
| 11 | 数据与事务完整性 | 0 | 不覆盖 terminal outcome；pending→unknown，不释放未知预留预算 |
| 12 | 依赖与供应链治理 | 0 | 无新依赖；复用已准备固定镜像，无下载或 pull |

## 5. 整改清单

none，无需生产代码补丁。

## 6. 长效治理建议

1. 保留完整 ID 替换与 ACK 丢失反例；不得把按名删除或全局 prune 引入恢复捷径。
2. 真实 SIGSTOP/SIGKILL 测试作为显式 Docker 门禁保留，使用独立 state 和持久身份，不扫描清理开发者其他容器。
3. 展示恢复结果时以 resource.state 为当前资源状态；running 是预检时观测。exit 0 和 ledger_reconciled 不等于候选通过或未知费用变为零。

## 7. 审计声明与冻结版本

没有修改生产源码、store、主库或镜像。仅新增 sandbox 独立测试、两份真实测试运行证据及主目录报告。该批是手动恢复能力，不提供宿主死亡后的硬实时清理保障。不可信同 UID 操作员不在威胁模型。无豁免。

独立文件 `tests/test_repair_recovery_review.py` SHA-256：`cd0b312908bec821548861a86cb184228760347c786fcba4201e049db23824e3`。

```json
{
  "src/agent_workbench/cli.py": "3ff7d95457638844483e1687ab9efb63d41a78c759bcb35cf0382658852b28a8",
  "src/agent_workbench/repair_recovery/__init__.py": "b1c564b320cea75b9cd038c5c95da17256c59887e5ec7806e909c318fad1f9ff",
  "src/agent_workbench/repair_recovery/cli.py": "a042ce6ccb6594af8dbdf171807aefdb51b5b11e9bb1e2c8f3d175c58e87a986",
  "src/agent_workbench/repair_recovery/inventory.py": "6b97e2b211773eb8c512280397aae9ee02928da96435a0b83b9f69124911526c",
  "src/agent_workbench/repair_recovery/service.py": "e5104ad85c684a8a7421bd3648471942f89850b17afb1b14ce4902fae496e396",
  "tests/test_repair_recovery.py": "1e5dd440524091c02eb8f39f1b51a1d2e41562e0284478ae9d58b4a033f30912",
  "tests/test_repair_recovery_docker.py": "305936748eafeee8817fa14cebce03e04459310e409d1d6bdccb89682c5f4eaa"
}
```
