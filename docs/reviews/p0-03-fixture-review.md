# 企业代码质量审计报告：P0-03 fixture 第一批（最终复审）

- **审计对象**：`containers/p0_03/{Dockerfile,server.py,prepare.py,test_prepare.py,README.md}`，5 实现/说明文件及1份新增反例测试，最终摘要见清单。
- **版本**：2026-10-13 独立副本，文件 SHA-256 见 `p0-03-fixture-snapshot.json`。
- **目录**：`<review-workspaces>/p0-03-review`。
- **技术栈**：Python 3.12 标准库、Docker、pytest；未改实现、未构建镜像；最终独立运行5个自有UUID的受控容器。
- **场景 / 严苛度**：General SaaS / Mission-Critical。
- **依据**：AGENTS、docs/01、03、04、11；auditing-enterprise-code-quality skill。

## 1. 代码质量评估卡

**100 / 100，本批受控本地 fixture 范围 Pass。P003-F01/F02 均修复并独立复审关闭；不是生产环境或恶意租户安全认证。**

| 未关闭 P0 | P1 | P2 | P3 |
|---|---|---|---|
| 0 | 0 | 0 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 0 unresolved; F01/F02 fixed and re-reviewed
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: scoped trusted-local fixture Pass
NOT ASSESSED: production deployment / hostile multi-tenant isolation (outside scope)
```

独立执行：

```sh
uv run --frozen pytest containers/p0_03/test_prepare.py
uv run --frozen ruff check containers/p0_03
uv run --frozen mypy --strict containers/p0_03/server.py containers/p0_03/prepare.py
```

输出：

```text
.........................                                                [100%]
25 passed in 0.53s
All checks passed!
Success: no issues found in 2 source files
```

这些是无 Docker 单测，不代替真实容器验收。

## 2. 生产事故风险推演（原缺陷，现已修复）

> **场景：并发准备错误绑定镜像身份**
> **触发条件**：两个本项目独立副本以不同 server.py 同时显式 prepare，使用同一 daemon/tag。
> **机制**：A build 结束后、A inspect 前，B build 将 `awb-p0-03:local` 更新为 B 镜像。A 读取 B ID，仍以 A 源摘要发布 manifest。
> **用户症状**：执行工具与已核验本地源码不对应；复现与 watchdog/故障声明失真。
> **范围**：该 manifest 后续容器运行。
> **检测性**：现有本地源码前后摘要不变，不能发现 tag 被其他合法任务更换。

## 3. 详细审计明细

### P0

none。

### P1 — P003-F01：共享 tag 读取不能证明本次构建身份（已关闭）

- **原版本位置**：`prepare.py:46–75`，尤其 `image inspect ... IMAGE_TAG`。
- **维度**：12 依赖与供应链治理；11 证据完整性。
- **置信度**：confirmed，代码路径与 mock 反例确认；未运行真实并发 Docker build。
- **复现**：拦截 subprocess.run 模拟 build 后 tag 已指向不同合法 SHA-256 ID，调用原 prepare；它仍发布该 ID 配本地 source_sha256。

```json
{"case":"tag_replaced_after_build","current_build_id_assumed":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","published_id":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","published_own_source_hash":true,"build_has_iidfile":false}
```

- **修复建议**：build 增加独立 `--iidfile`，读取本次构建结果，并以该不可变 ID inspect；不要从共享 tag 反查本次 ID。示意最小改动（需调整临时目录生命周期）：

```diff
+ iid_path = context.parent / unique_output_name
  ["docker", "build", ...,
+  "--iidfile", str(iid_path),
   "--tag", IMAGE_TAG, str(context)]
- ["docker", "image", "inspect", "--format", "{{.Id}}", IMAGE_TAG]
+ image_id = iid_path.read_text().strip()
+ ["docker", "image", "inspect", image_id]
```

- **验证**：mock 写 iid=A，但共享 tag=B；最终 manifest 必须为 A。缺失/非法 iid、inspect 身份不符均不替换旧 manifest。最终 ENV/VOLUME/ENTRYPOINT/USER 也应有明确审核/拒绝规则。

### P2 — P003-F02：stdout 洪泛在上限前先触发 JSON 错误（已关闭）

- **原版本位置**：`server.py:153–158`。
- **维度**：9 可测试性与验收真实性。
- **置信度**：confirmed；截获真实 call 的第一段 os.write 数据。
- **问题**：首帧为 4095 个 x 加换行，严格 transport 会先报非法 JSON；不能以此证明字节/帧上限触发。若测试仅断言不成功，删除输出限制后也可通过。

```json
{"case":"stdout_flood_first_frame","bytes":4096,"ends_newline":true,"valid_json":false,"below_1MiB_frame_cap":true}
```

- **修复**：总量洪泛使用可被接受的合法通知帧；超帧使用无换行持续输出。真实容器测试分别断言 stdout_total_limit / frame_limit 对应的固定代码，而非任意失败。stderr 可继续使用固定任意字节。
- **验证**：新增 fixture 单测确认总量场景首帧合法且未超单帧限制、超帧场景没有换行；真实 transport/容器验收确认具体限额生效。

### P3

none。

### 初审提出的联动边界（完成情况见最终复审）

- watchdog 静态结构为独立监督进程监视 worker，受 monotonic 截止控制；但 `--init` 退出是否回收 setsid 孙进程、宿主 SIGKILL 后容器是否停止须实际证明。
- policy_probe 对 `/` 的写失败可能只是非 root DAC 权限不足，不能单独证明只读挂载。建议对归属 65532 的 `/opt/fixture/server.py` 以不截断、不写入方式尝试写打开，并只将 EROFS 作为只读证据，结合 HostConfig inspect。
- 当前 prepare 仅 inspect ID，没有最终 ENV/VOLUME 策略检查；需与 runner 的启动前 inspect 联动确认。镜像 UID/entrypoint 静态声明不能代替完整镜像的运行检查。
- 固定官方 base digest 的真实性、Docker policy、OOM/PID/CPU限制、daemon 故障与输出输送不在本批已验证结论中。


### 最终复审增量

- **F01 关闭**：prepare 使用独立临时 `--iidfile`，输出路径在 build context 外；以本次不可变 ID inspect，并核对精确 ENV、无 VOLUME、ENTRYPOINT、USER、WorkingDir；缺失/非法 iid 和 identity mismatch 拒绝。44 项准备/fixture 单测通过，包含并发 retag 反例，manifest 不再取共享 tag 的 ID。
- **F02 关闭**：无换行洪泛与合法通知总量洪泛分开；独立截获首个 write 验证两者格式。真实产品 CLI 分别触发 `frame_limit_exceeded` / `stdout_limit_exceeded` 并清理确认，不再把非法 JSON 当限额证据。
- policy_probe 已改为对归属 65532 的 server.py 进行不截断、不写入的写打开，并区分 EROFS 与 EACCES。独立两项回归通过。
- PID fixture 改为 `os.fork` 写时复制，避免 Python 新解释器内存耗尽先于 PID 上限；EAGAIN marker 和释放少量槽位逻辑已读。主 Agent 报告真实 EAGAIN=11、SIGKILL watchdog=8 秒/exit124/Pid0 的验收；本 reviewer 阅读真实测试代码，未独立重复故障宿主 kill。
- 主 Agent 报告完整 274 项（含 18 Docker）通过，再合入 reviewer drain 测试为 275 项；这些是主集成证据，不能表述为本 reviewer 亲跑全部 275。
- 本 reviewer 亲跑本批与联动单元总计 **110 项**，另亲跑 5 项真实 CLI：pass=0；duplicate_result/stdout_flood/stdout_total_flood/stderr_flood=2，错误代码正确，cleanup 均 removed。随后逐个查询自身 UUID，确认 5 容器均不存在。
- 固定执行 image ID：`sha256:3c5b0613294b2fb3cfc63817085fcae590676c2df5c482f18334929fd78da766`；source SHA：`5b5031e5ffb18daf1161e6fd867551f31f3db0f582c4da4f6ab44af219443cd3`。
- 最后追加5项manifest/source/symlink篡改测试已读并独立运行，生命周期文件13项通过；加上前述105项，其中5项为新增，独立去重单元总数110。
- Ruff、mypy（8 source files）、uv lock --check 均通过。本地原始输出仅在 reviewer 独立 `artifacts/review-p0-03/`，报告未包含调用值或原始 stderr。

## 4. 维度覆盖声明

| # | 维度 | 发现 | 备注 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | 合成 fixture 明示，不冒充公开 bug |
| 2 | SOLID / 设计 | 0 | 标准库 fixture 范围清楚 |
| 3 | 并发与资源安全 | 已评估 | watchdog 静态与主集成证据核对；5项受控CLI亲跑 |
| 4 | 容错 | 0 | CLI 错误固定代码，准备失败保留旧 manifest |
| 5 | 性能 | 已评估 | 运行inspect强校验，完整资源故障由主集成证据支持 |
| 6 | 安全与合规 | 0 新确认 | 未输出传入参数或完整异常，镜像策略待集成 |
| 7 | 可观测性 | 0 | 来源与合成边界明确 |
| 8 | 类型契约 | 0 | mypy 通过，固定场景与数值范围 |
| 9 | 可测试性 | 1 | P003-F02（已修） |
| 10 | 工程规范 | 0 | Ruff 通过，批次小于 2000 行 |
| 11 | 数据完整性 | 见 F01 | manifest 错误来源绑定，不重复扣分 |
| 12 | 依赖治理 | 1 | P003-F01（已修） |

## 5. 整改清单

| ID | 严重级 | 负责人 | 截止 | 状态 |
|---|---|---|---|---|
| P003-F01（已修） | P1 | `/root/review_ui_api` 修复，`/root` 合入 | 2026-10-13 | fixed / independently verified |
| P003-F02（已修） | P2 | `/root` | 2026-10-13 | fixed / independently verified |

## 6. 架构防腐与长效治理建议

1. 镜像构建产物 ID 与源快照绑定，不通过共享名称反查；成本为 iidfile 与几项反例测试。
2. 每个故障场景断言特定故障原因；以“删除防线则测试失败”核对验收质量，避免所有负例都只验 exit 非零。
3. 将 mock 准备测试与真实容器隔离验收分开统计，缺 Docker 的 skip 不计通过。

## 7. 审计声明

此为 fixture 实现与反例批次；初审未操作容器，最终复审独立运行了下述 5 个精确 UUID 的受控容器。未构建镜像、未操作其他项目容器、未修改实现。两个原发现有反例及修复证据且均关闭；不签发恶意租户隔离或生产许可。后续改动需更新摘要并增量复审。
