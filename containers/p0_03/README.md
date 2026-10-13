# P0-03 受控容器 fixture

本目录是**合成故障注入**，不是公开历史缺陷复现或任意不可信仓库运行环境。
服务仅用 Python 标准库实现本里程碑所需的 MCP 2025-11-25 stdio 子集：逐行 JSON-RPC、initialize、tools/list、tools/call、ping 和无响应通知。产品客户端继续使用固定版本官方 MCP SDK。本 fixture 不替代通用 MCP Server SDK。

## 明确准备镜像

先由开发者在受控环境准备已有的官方基础镜像：

`python@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134`

本脚本**不会拉取**镜像或安装依赖；基础镜像缺失直接失败。仅开发者显式执行：

```sh
python3 containers/p0_03/prepare.py
```

脚本先本地 inspect 固定基础 digest，再用只有 Dockerfile/server.py 的临时 build context 执行 `docker build --network=none --pull=false`。通过独立 iidfile 获取本次构建的不可变ID，并按ID核验镜像配置；不从可变tag解析构建身份。只写本项目 tag `awb-p0-03:local`，120 秒构建超时，inspect 各 5 秒上限；不读其他项目镜像。运行期间源文件变化时拒绝发布 manifest。

成功显式原子写入项目 `artifacts/p0-03-image.json`（忽略目录），stdout 为同一 JSON：

```json
{"image_id":"sha256:<64 lowercase hex>","source_sha256":"<64 lowercase hex>","base_digest":"python@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134"}
```

source_sha256 为固定顺序 `['Dockerfile','server.py','prepare.py']`：
`sha256(b'\0'.join(name.encode()+b'\0'+file.read_bytes() for name in names))`。
拒绝源文件 symlink。运行器须复核源摘要及 manifest，并使用不可变 image_id 启动，不能把浮动 tag 当版本证据。manifest 不表示主机/镜像安全认证。

准备失败仅输出固定 `image_prepare_failed` / `image_prepare_timeout`，非法参数输出 `invalid_arguments`；不回显命令、路径、异常正文。不在客户端启动时自动运行准备器。

## 服务接口与运行约束

镜像 ENTRYPOINT：`python -I -B /opt/fixture/server.py`，非 root UID/GID 65532。

参数：`--scenario` 下表枚举，`--seed` 整数 0..2147483647（默认 0），`--lifetime` 整数 5..45 秒（默认 45）。不得开放内部 `--worker` 给外部配置。seed 控制 OOM 分配的合成填充值；其他故障场景的行为是确定性的，无随机成功率。

主运行器负责 `--init`、断网、只读根、受限 `/tmp` tmpfs、CPU/内存/PID 限额、cap-drop、no-new-privileges、输出限额与容器清理。**禁止任何宿主目录或 Docker socket 挂载，禁止继承宿主环境变量。** 只存在 `/.dockerenv` 的进程才接受启动；监护进程须 PID1 或 init 的直接子进程。这是防误运行提示，安全边界仍为宿主运行器的 Docker 策略。

监护进程另起 worker，共享标准流；通过独立 monotonic deadline 每 50ms 检查，超过 lifetime 硬退出（124），worker 退出则监护立即退出。SIGTERM/SIGINT 也硬退出监护。使用 Docker `--init` 时 init 随主进程结束退出，由 PID namespace teardown 回收 TERM 无效的孙进程。宿主被 SIGKILL 后，容器仍至多运行到自身 lifetime；是否停止必须以真实容器状态验证，不凭宿主 pipe 结束推断。

工具 `lookup`：输入严格对象 `{id: integer}`；通常输出严格对象 `{count: integer}`。count 是当前容器 `/tmp/call-count` 中累计调用次数，每次合法调用仅写一次。工具错误也可已有副作用；重复结果不重复写入。crash_during_call 在写入前退出；其余发出调用后但终态缺失时，客户端不得假定无副作用或自动重试。

| 场景 | 行为 |
|---|---|
| pass | 写计数后正常回复 |
| tool_error | 写计数后 isError=true 合成错误文本 |
| timeout / response_lost | 写计数后一直等待，不返回结果 |
| duplicate_result | 写一次计数，同一个 wire ID 返回两次相同结果 |
| crash_before_call | tools/list 阶段退出 71，未进入工具调用 |
| crash_during_call | 收到合法调用后、计数写入前退出 72 |
| crash_before_result | 写计数后、返回结果前退出 73 |
| stdout_flood / stderr_flood | 无换行原始块，分别触发帧字节上限/标准错误字节上限 |
| stdout_total_flood | 合法通知持续输出，触发stdout累计字节上限 |
| pid_limit | fork共享内存页直到进程配额拒绝(EAGAIN)，写marker并释放3个槽供验收探针使用 |
| spawn_child | 写计数后启动 setsid 孙进程并忽略 TERM；写 `/tmp/child-pid`，等待回收 |
| oom | 写计数后按 seed 分配内存直到限制触发，不在宿主运行 |
| cpu_spin | 写计数后确定性 CPU 忙循环，不在宿主运行 |
| policy_probe | 写计数并返回下述策略观察 |

policy_probe 单独扩展 outputSchema，结果为 `{count,policy}`，policy 包含：

- `uid_nonzero`、`root_write_denied`、`only_loopback`、`no_host_secret`：boolean，schema要求true。只读探针对owned server.py执行O_WRONLY但不写入/截断，仅EROFS为true。最后一项仅检查固定合成 `AWB_TEST_SECRET` 不在容器环境中，绝不枚举/输出真正凭据；不能据此证明任何其他 secret 不存在。
- `cpu_max`、`memory_max`、`pids_max`：string，读取 cgroup v2 文件原文 strip。例：cpus=0.5 通常得到 `50000 100000`（本镜像的验收schema固定为该值；其他周期配置需独立适配）；128m 得到 `134217728`；pids-limit=32 得到 `32`。非 cgroup v2 环境明确失败，不伪造配额证据。

## 单测与独立集成验收

```sh
uv run --frozen pytest containers/p0_03/test_prepare.py
```

单测 mock Docker，仅验证准备流程、摘要、红线、错误脱敏以及协议/副作用契约；不会构建镜像、启动容器或制造 OOM。真实隔离、CPU/OOM、输出限额、取消、宿主 SIGKILL 和进程树回收由主运行器的真实容器集成测试验证。本目录单测通过不能代替那些门禁，也不能由本实现者自评替代独立 code review。

### 本子任务执行记录（2026-10-13）

- `uv run --frozen pytest containers/p0_03/test_prepare.py`：44 passed（修复后）（mock Docker 的单测）。
- `uv run --frozen ruff check containers/p0_03`：All checks passed。
- `uv run --frozen mypy --strict containers/p0_03/server.py containers/p0_03/prepare.py`：2 source files 无类型错误。
- fixture作者未操作Docker；主任务的真实容器验收及独立评审结果统一见 [规格](../../docs/11-controlled-execution.md) 与台账。
