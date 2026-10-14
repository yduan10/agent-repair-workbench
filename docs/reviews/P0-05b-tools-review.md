# P0-05b B2 受控工具独立评审

日期：2026-10-14。实现：独立 tools worker；评审：主线程（未实现 B2）。范围为三个 controlled_tools 模块、固定源码/证据包、wrong_type 容器增量和三个测试文件。评审约 1000 行实现与测试；不把该结论扩展为全项目生产认证。

## 结论

复审通过。发现并关闭 1 个 Defect P1。当前只允许审核过的合成案例，不支持任意工具上传，不应用模型建议。

| 编号 | 等级 | 问题与反例 | 修复与复验 |
|---|---|---|---|
| T01 | Defect P1 | asyncio.Task.cancel 可穿过 AnyIO thread 等待，T04 父任务先取消而实际 checker 尚未终止；同类 T05 清理需覆盖实际 CLI 取消机制 | `_owned` 持有子任务并 shield 等待；T04等待自身限时进程 terminate/join；T05将取消转为内部 AnyIO cancel scope，清理返回后携带宿主 cancelled 标记。原生重复取消真实 checker、实际 SDK/Docker 运行与 rm 后容器不存在均通过。协调器记录 tool_completed 后停止，不继续调用模型 |

## 十二维度门禁

| 维度 | 本批检查与结论 |
|---|---|
| 架构/边界 | 角色权限在宿主统一执行；T06～08未注册，通过 |
| 结构职责 | registry / response / execution分离，通过 |
| 并发/资源 | T05原子claim；重复ID不重执行；原生取消等待资源回收，通过 |
| 容错 | 保存失败/丢响应保留unknown，禁止自动重投，通过 |
| 性能/限制 | 文件128KiB、片段200行/16KiB、32证据、响应64KiB、执行30秒与清理窗口，通过 |
| 安全 | 逐级nofollow、拒绝硬链接/FIFO、完整文件SHA、目标白名单、角色/跨任务拒绝，通过 |
| 可观测 | 返回安全证据/报告关联/清理状态；源码仅临时返回不持久化，通过 |
| 类型 | 严格DTO并重新解码model_construct伪造输入，mypy通过 |
| 可测试性 | 本地工具、故障窗口、真实SDK/容器分开验收，通过 |
| 工程规范 | Ruff/格式和源码包固定摘要，通过 |
| 数据完整性 | task/request/payload绑定、报告SHA与两个执行ID校验，通过 |
| 依赖 | 复用已有runner/SDK；无新增B2第三方依赖。全批新增模型依赖另有61项审计，通过（0公告漏洞） |

## 复验命令及证据

- `uv run pytest tests/test_controlled_resources.py tests/test_controlled_runtime.py`：23通过。
- `AWB_TOOL_DOCKER=1 uv run pytest tests/test_controlled_tools_docker.py`：3通过。主线程独立重新运行通过。
- 实际 mismatch 为 `output_schema_violation`，路径 `/result/structured_content/count`，报告 failed、cleanup removed；正常对照passed。
- 同request重放返回同一持久报告，无第二次执行；源码快照与实际Docker server完全一致。
- 安全本地产物 `artifacts/p005b-tool-acceptance/` 不提交；公开测试代码可显式复跑。

## 故障推演与剩余边界

进程被强杀后：数据库有claim/关联，缺少最终报告即unknown；显式对账不重投。活owner暂停时由同task flock阻挡对账。Docker清理取决于本机daemon响应，失败会记录未确认，不承诺强多租户隔离。模型建议的正确性、真实模型验收、网页展示由其他批次验证。
