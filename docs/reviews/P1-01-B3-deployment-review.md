# 企业代码质量审计报告：P1-01 B3 常驻部署

- **审计对象**：`ops/local_service.py` 及 B3 停写迁移/常驻服务操作证据；不包含网页控制器与事件 API（由另一位 reviewer 审查）。
- **审计版本**：B2 `9195df9` 之后的 B3 工作树；`ops/local_service.py` SHA-256 为 `fcc11fb5216ef4734f666bffcd1137b627d9be97bddcab820e1822f3ea523644`。
- **技术栈**：Python 3.12 标准库、macOS 用户 LaunchAgent、Uvicorn、Next.js production、SQLite。
- **业务场景**：General SaaS；实际信任边界为可信本机单用户。
- **审查严苛度**：Mission-Critical（对本批明确边界）。
- **审计时间**：2026-10-16。

## 1. 代码质量评估卡

- **综合质量得分**：代码复审 **100 / 100**；初版两类已确认 Defect P1 均已修复。
- **上线评估结论**：**Pass**：本批常驻部署代码、迁移保真与真实服务健康均通过独立复审；整个 B3 还须结合网页/事件评审及总体验收。
- **审计范围**：一份常驻服务脚本、独立测试、当前主库的显式迁移记录。
- **未评估项**：本次约定审计范围内 none。网页交互/事件接口由另一份报告负责；本报告不验证真实模型修复效果。reviewer 未安装/停止用户服务，也未读取任何凭据值。

| P0 阻断 | P1 严重 | P2 主要 | P3 次要 |
| :---: | :---: | :---: | :---: |
| 0 | 0（初版 2 类已关闭） | 0 | 0 |

初版评分轨迹：Mission-Critical / General SaaS；2 × 8 = 16；原始 84，存在 P1 封顶 79。修复后所有反例通过；最终代码评分 100 − 0 = 100，无封顶。门禁输入为无未关闭 P0/P1/P2、23 项部署测试通过、主库独立保真核验通过、launchd 与 HTTP 健康独立核验通过；未施加豁免。

## 2. 生产事故风险推演

> **场景 1 — 部分安装留下未预期的 API 服务**  
> API bootstrap 成功后，web plist 冲突或 web bootstrap 失败。初版脚本退出失败，但 API 仍常驻并接受操作。反过来，若把 launchctl 查询失败当作服务不存在，失败回滚还可能触碰安装前已经运行的服务。影响本机前后端发布状态；使用“先全量预检、只回滚本次启动的服务、未知查询结果拒绝操作”控制。

> **场景 2 — 停止命令成功但后端仍在运行**  
> launchctl bootout 失败，初版 `check=False` 后不核对结果，仍退出成功。操作员据此开始迁移或重启会破坏停写假设。另一个 checkout 的同标签服务也不应被此脚本直接卸载。影响本机部署与迁移窗口；以配置归属预检、卸载状态复查和非零失败退出控制。

## 3. 详细审计明细

### P0 — 阻断性缺陷

none。

### P1 — 严重缺陷

#### P1-1：安装缺少全量预检及失败补偿 [confirmed]

- **位置**：`ops/local_service.py:99-120,148-169`（修复后）；初版同一安装分支逐项校验后立即启动。
- **审查维度**：4 容错、3 资源安全。
- **证据**：独立测试分别注入第二个 plist 冲突、第二个 bootstrap 失败、第二个服务已注册、launchctl 查询失败。
- **最小修复要求**：先验证全部配置与注册状态；失败时仅回滚本次开始的 bootstrap；回滚失败继续明确报错；查询结果未知不能降级成 absent。
- **验证方式**：`tests/test_b3_local_service.py` 的 install/query/rollback 反例。
- **当前状态**：已关闭；查询非 0/113 失败拒绝操作，安装预检与补偿反例全部通过。

#### P1-2：stop 忽略卸载失败且不验证服务归属 [confirmed]

- **位置**：`ops/local_service.py:122-141`（修复后）；初版 stop 直接忽略 bootout 返回码。
- **审查维度**：4 容错、7 可运维性。
- **证据**：bootout 错误反例和另一 checkout 配置反例均在初版失败。
- **最小修复要求**：对所有待停止服务先验证归属，完整尝试停止后检查结果，任何仍存在/卸载失败显式返回错误；已经不存在允许幂等停止。
- **验证方式**：`tests/test_b3_local_service.py` 的 stop failure、other checkout、already absent 用例。
- **当前状态**：修复后反例通过。

### P2 — 主要缺陷

none。

### P3 — 次要缺陷

none。

## 4. 维度覆盖声明

| # | 维度 | 结论 | 备注 |
|---|---|---|---|
| 1 | 架构与边界 | 无新增发现 | 部署脚本不执行迁移、构建或自动下载，不开放远程任意 shell |
| 2 | SOLID 与现代设计 | 无新增发现 | 小型运维入口，配置生成与私有配置读取可独立验证 |
| 3 | 并发与资源安全 | P1-1 | 安装前预检与失败回滚；服务任务关闭由已有 lifespan 接管 |
| 4 | 容错与防御 | P1-1/P1-2 | 区分不存在、查询失败、停止失败 |
| 5 | 性能与伸缩 | 无新增发现 | 只操作两个固定服务；环境配置最大 16 KiB |
| 6 | 安全与合规 | 已测边界通过 | owner/0600/普通文件/非符号链接、字段白名单；无密钥 plist；loopback |
| 7 | 可观测与运维 | P1-2 | 状态检查、固定日志路径与失败退出；不输出异常原文 |
| 8 | 类型与契约 | 无新增发现 | 类型标注、枚举命令、配置值非空及禁止 NUL |
| 9 | 可测试性 | 已新增独立反例 | 临时目录与 launchctl 替身，测试不安装或停止主机服务 |
| 10 | 工程规范 | 静态检查通过 | Ruff/格式覆盖脚本和独立测试；启动、停止及状态为明确命令 |
| 11 | 数据完整性 | 独立复验通过 | 0007→0008，17张旧表183行原始tuple/BLOB/rowid相同，备份0600、两库完整性ok |
| 12 | 依赖与供应链 | 无新增发现 | 标准库脚本；使用现有固定 venv 与已构建 Next.js，无启动安装依赖 |

## 5. 整改清单

| ID | 严重级 | 负责人 | 截止 | 状态 |
|---|---|---|---|---|
| P1-1 | Defect P1 | 实施 Codex /root | B3 验收前 | 已修复，独立反例通过 |
| P1-2 | Defect P1 | 实施 Codex /root | B3 验收前 | 已修复，反例通过 |

## 6. 架构防腐与长效治理建议

1. 保留查询未知、部分安装与停止失败的反例，后续更换服务管理方式时仍用同样的失败契约；成本为本次新增用例的维护。
2. 将主库迁移证据和运行服务检查分开记录；服务端口可用不等于迁移保真，数据库版本正确也不等于常驻成功。

## 7. 审计声明

本报告仅对上述摘要对应的部署代码与2026-10-16真实操作证据给出 Pass；后续代码改动需增量复审。真实主库内容只做摘要/行数核对，不把原始内容或凭据写入仓库。故障注入测试使用 launchctl 替身，成功部署另有真实进程及 HTTP 证据；不以单测替代实际常驻验收。未施加风险豁免。

### 独立测试结果

```text
uv run --frozen pytest tests/test_b3_local_service.py
23 passed in 5.33s
uv run --frozen ruff check ops/local_service.py tests/test_b3_local_service.py
All checks passed!
uv run --frozen ruff format --check ops/local_service.py tests/test_b3_local_service.py
2 files already formatted
```

最终日志：`artifacts/b3-local-service-review-final.log`。初轮 `5 failed, 11 passed` 和第二轮查询失败反例保留在 `artifacts/b3-local-service-review-first.log`、`artifacts/b3-local-service-review-second.log`。覆盖私有配置 owner/权限/大小/符号链接/字段值、plist 无凭据、固定 loopback、安装部分失败、已有服务不受影响、停止失败与幂等、查询未知、失败回滚仍失败。

### 真实主库迁移独立复验

执行前已只读审查临时脚本 `artifacts/b3_migrate_main.py`，摘要 `d5b8f022302f3fde08b14a88a916d2d83865e403a0292a19275bd27b25ace535`。脚本要求 8030 无监听、无已知 CLI/API writer，并在持有三个网页 owner 锁时备份、显式迁移与核验。它不承诺支持任意 CLI 并发写入；停写窗口是前置条件。没有自动恢复备份覆盖可能的新写入。

执行后 reviewer 独立打开 0007 备份和 0008 主库，以只读 SQLite 事务逐表比较 `SELECT rowid,* ORDER BY rowid` 的原始 Python tuple（包括 BLOB bytes），不只相信实施脚本给出的摘要。结果保存为 `artifacts/b3-independent-migration-proof.json`：

```text
old_schema: 0007_web_analyses
new_schema: 0008_web_repairs
backup_mode: 0o600
backup_integrity: ok
main_integrity: ok
old_tables: 17
old_rows: 183
byte_and_rowid_equal: true
new_receipts: 0
```

备份：`artifacts/b3-main-backup-20261016T025810Z.sqlite3`；实施记录：`artifacts/b3-main-migration.json`。这些本地产物不入仓库；本报告不包含原始行内容。

### 真实常驻服务独立复验

实施记录：`artifacts/b3-launchd-health.json`；reviewer 独立只读复验：`artifacts/b3-independent-launchd-proof.json`。

| 项目 | 独立核查结果 |
|---|---|
| API LaunchAgent | `io.agentrepair.local.api`，`running`，PID 41973，PPID 1 |
| 前端 LaunchAgent | `io.agentrepair.local.web`，`running`，PID 41975，PPID 1 |
| 实际监听地址 | `lsof` 确认 API `127.0.0.1:8030`、web `127.0.0.1:3010` |
| API健康 | `8030/api/health` HTTP 200 |
| 前端代理健康 | `3010/api/health` HTTP 200 |
| 产品页面 | `3010/workspace/repairs` HTTP 200 |
| 修复目录 | `8030/api/repair-runs/catalog` HTTP 200 |
| 两个plist | 0600，配置中无模型密钥字段或密钥参数 |
| 私有配置 | 文件0600、目录0700、当前用户持有、普通文件、git忽略；未读取值 |

服务由当前用户 launchd 管理，父进程为 PID 1，生命周期不依赖聊天工具会话。配置为 RunAtLoad/KeepAlive；这是用户登录会话的 LaunchAgent，未宣称系统级无人登录 daemon。本次核查没有发送模型请求、启动修复任务或停止服务。

### 最终重启增量复审

实施者真实停止时发现 launchd 的 bootout 完成与注册消失存在短暂间隔；即时查询会误报停止失败。修复在 stop 与安装失败回滚两条路径共用 `wait_unloaded`，最多50次间隔0.1秒查询，最后再次确认；状态查询未知继续报错，不能将尚未卸载认定完成。这是查询重试次数上限，不声称给每次外部 launchctl 调用设置了5秒总超时。

修复后复跑23项部署测试通过（20项初轮独立测试、2项实施者新增停止竞态测试、1项独立新增回滚竞态测试）。新增独立反例验证回滚等待注册消失后仍抛出原始 bootstrap 失败，不误判回滚未完成、不吞掉安装失败。静态检查两文件通过；生产脚本摘要以上方最终值为准。

真实 `stop && install` 成功后的实施证据为 `artifacts/b3-launchd-delivery.json`。reviewer 再次独立只读确认，证据保存为 `artifacts/b3-independent-restart-proof.json`：API PID76124、web PID76126，均为 `running`、PPID1；仅监听loopback，8030/3010健康、修复页面和前端代理目录均返回200。前一节PID41973/41975记录首次安装的历史核验，本节记录重启后的核验；后续仅文档构建重启会生成新PID，不改变已审计生产脚本摘要。

增量结论仍为 **Pass**，无未关闭 Defect P0/P1/P2。未额外启动模型或修复任务。
