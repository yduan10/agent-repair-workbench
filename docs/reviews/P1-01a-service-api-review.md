# 企业代码质量审计报告

- **审计对象**：P1-01a 第二批，Web 受控复现的 catalog、接收/执行 service、HTTP API；根 API 生命周期与精确来源端口；runner 的私有 image_root 测试接缝增量。
- **审计版本**：已冻结工作副本；8 文件完整 SHA-256 见 [源码清单](P1-01a-service-api-sha256.json)。包括作者 7 个目标文件及本次独立反例文件。
- **技术栈**：Python 3.12、FastAPI、asyncio、AnyIO、Pydantic、SQLite/SQLAlchemy；复用已审 Docker runner。
- **业务场景**：General SaaS（实际部署边界为可信开发者的本机单用户工具）。
- **审查严苛度**：Mission-Critical。
- **审计时间**：2026-10-14。
- **独立性**：评审者未参与本批后端实现；未修改生产实现，新增反例只在独立副本执行。第一批存储/迁移另由独立评审负责，本报告读取其接口作为依赖。

## 1. 代码质量评估卡

- **综合质量得分**：**100 / 100**，表示已评范围无扣分发现，不是对完整产品无缺陷的保证。
- **上线评估结论**：**Pass — 本批实现可进入主线集成门禁**。
- **审计范围**：3 个 Web 模块、根 API 与 runner 私有参数增量、2 个作者测试文件及 1 个独立测试文件；第一批存储与 fencing 作为直接依赖核读。
- **未评估项**：本批声明范围内 none。整产品真实浏览器→HTTP→Docker 联调由主线单独执行，不以本报告替代；任意代码执行、多租户与模型修复不在当前产品开放范围。

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
VERDICT:      Pass — 本批无已确认未闭缺陷；整产品仍须主线集成验收
NOT ASSESSED: none within the declared batch
```

### 实际验证证据

独立副本执行：

```text
uv run --frozen ruff check src/agent_workbench/web_runs src/agent_workbench/api.py src/agent_workbench/runner/service.py tests/test_web_reproductions_reviewer.py
All checks passed!

uv run --frozen mypy src/agent_workbench
Success: no issues found in 48 source files

uv run --frozen pytest tests/test_web_reproductions.py tests/test_web_reproductions_reviewer.py -ra
45 passed in 7.15s
```

其中作者已有 39 项、本次新增独立反例 6 项。测试采用临时 SQLite、固定合成请求；未读写用户运行库，未操作主服务端口。作者另提供 4 个显式真实 Docker 场景通过证据，本评审没有重复运行并计入上述 45 项。

## 2. 生产事故风险推演

没有已确认 P0/P1 事故路径。对下列承重交错进行了实际验证：

1. **提交已入库、HTTP 等待者取消**：分别通过 service 等待者取消与经过 FastAPI/ASGI middleware 的请求任务取消，确认独立 owner worker 完成一次执行；重放返回 200 原记录，没有第二次调用。ASGI 取消探针不冒称真实 TCP 拔线测试。
2. **claim 已提交、执行 scope 尚未注册时停服**：人为阻塞 admit 返回，在 close 已开始后释放。使用实际 run_sandbox，仅替换镜像/Docker 依赖，保存 cancelled/not_created，释放执行槽。
3. **开始前已有持久取消标志**：实际 runner 在第一处异步检查点观察取消，不发送 Docker 命令，保存可核对的终态和未创建资源证据。未复现“进入 taskgroup 就失去报告、必然遗留 running”的怀疑。
4. **另一进程请求停止**：独立 Python 进程通过其 FastAPI/TestClient 取消端点写入持久 flag；原 owner 的 watcher 观察后保存 outcome_unknown，清理证据明确后释放槽；重复提交只读取旧记录。
5. **执行异常或 finish 保存失败**：保留不安全 active 槽及 running 证据，不将异常猜测成成功，不自动重新执行。显式 reconcile 仍为恢复边界。
6. **停服发生在准备探测期间**：close 等待已注册接收任务收尾；准备返回后再次检查 stopping，拒绝新 claim/dispatch。

## 3. 详细审计明细

### P0 — 阻断性缺陷

none。

### P1 — 严重缺陷

none。

### P2 — 主要缺陷

none。

### P3 — 次要缺陷

none。

### 关键路径核对

- `web_runs/service.py:71`：注册独立 asyncio owner task 后等待 shield Future，HTTP 取消不撤销接收/执行所有权。
- `web_runs/service.py:84`：已有请求先查询，再取跨进程 owner fence；保留同 ID 幂等与冲突、墓碑语义，准备检查只影响新接收。
- `web_runs/service.py:129`：开始前与运行中的取消均读取持久 flag；取消作用域退出后使用 shield 保存真实 runner 报告，release_safe 依据持久清理证据。
- `web_runs/service.py:194`：先禁止新接收，再取消已登记 scope，等待已拥有任务保存/回收。依赖 runner 和 Docker 边界既有时间限制，不宣称能在宿主硬杀时继续执行 Python 清理。
- `web_runs/api.py:24`：精确 Origin、JSON 类型、4 KiB 与 5 秒读取界限；重复键/未知字段/非法 UUID 被固定错误拒绝。取消只接受空对象与规范 UUID。
- `web_runs/catalog.py:75`：准备探测仅核验 manifest 与 image inspect；不 prepare、不 pull、不执行 fixture，也不初始化不存在的运行库。
- `api.py:22`：可配置单个前端端口，非法端口启动失败；默认来源没有与独立测试端口一起被隐式放宽。
- 捕获实际 claim token 后将其放进合成执行异常，核对接收、详情、重放响应与日志均无 token 或原异常文本。私密 claim 仅用于宿主 finish。
- runner 新增 image_root 仅为受信测试调用参数，HTTP 请求 schema 不含任意路径或执行配置；主 API lifespan 不从用户请求传入此值。

## 4. 维度覆盖声明

| # | 维度 | 发现数 | 备注 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | HTTP、准备探测、生命周期与已审存储/执行器分离；固定四场景。 |
| 2 | SOLID 与现代设计 | 0 | 新特性模块边界明确；使用已存在 runner，不复制执行协议。 |
| 3 | 并发、异步与资源安全 | 0 | 持久 flag、owner fence、独立任务与取消保存交错经反例验证。 |
| 4 | 容错与防御性编程 | 0 | 固定错误、无重复执行；未确认保存/资源时保守保留槽。 |
| 5 | 性能、伸缩性与计算效率 | 0 | 固定体积/时间限额、单执行槽；SQLite 操作在线程执行。并非通用共享托管服务。 |
| 6 | 安全与数据合规 | 0 | Host/Origin、固定 profile/case、无任意 argv/env；claim token 与错误隐私反例通过。 |
| 7 | 可观测性与运维友好度 | 0 | 持久运行/报告、固定 readiness 原因、明确需要显式核对的未知状态。 |
| 8 | 类型安全与契约表达 | 0 | 严格请求类型；公开输出与前端契约逐字段对照；mypy 48 文件通过。 |
| 9 | 可测试性与死代码 | 0 | 39 作者测试及 6 独立反例；跨进程取消是真正独立进程，未用同对象替代。 |
| 10 | 工程规范与一致性 | 0 | Ruff 通过，沿用既有确定性报告与本地部署约定。 |
| 11 | 数据与事务完整性 | 0 | 第一批已审原子 admit/claim 与安全释放被直接消费；异常后不另建执行账本。 |
| 12 | 依赖与供应链治理 | 0 | 本批无新增依赖；uv frozen 环境，runner 使用已有固定镜像和 SDK 边界。 |

## 5. 整改清单

none；没有需要作者修复的已确认缺陷。

## 6. 架构防腐与长效治理建议

1. 将 `tests/test_web_reproductions_reviewer.py` 纳入常规 CI；6 个确定性交错反例成本低，可防止后续重构将独立 owner 误合并到 HTTP 任务或提前释放槽。
2. 保留显式真实 Docker 与浏览器门禁的独立统计；mock、ASGI 生命周期通过不能替代真实容器策略、页面来源边界与最终报告验收。

## 7. 审计声明

- 结论只适用于 [SHA 清单](P1-01a-service-api-sha256.json) 中的冻结版本；相关实现变化须增量复审。
- 已施加豁免：none。
- 未评估：声明批次内 none；模型协作、任意外部代码与完整产品上线能力未在本批声明。
- 置信度：没有保留为缺陷的 suspected 项；开始前取消丢报告的怀疑已用实际 runner 路径核实，未复现。
- 本报告由后端实现者之外的评审者产出；前端实现已另交其他评审者审查，不以自查代替独立 review。
