/** Commands and settings shown on the 环境与接入 page. All run from the project root. */
const cli = "uv run --frozen agent-workbench";

export const commands = {
  startApi: "uv run --frozen uvicorn agent_workbench.api:app --host 127.0.0.1 --port 8030 --no-access-log",
  prepareImage: "uv run --frozen python containers/p0_03/prepare.py",
  runsInit: `${cli} runs init`,
  runsList: `${cli} runs list`,
  runsReconcile: `${cli} runs reconcile`,
  runsPrune: `${cli} runs prune --days 30`,
  mcpCheck: `${cli} mcp-check --server-config examples/mcp/pass-server.json --case examples/mcp/lookup-case.json`,
  sandboxCheck: `${cli} sandbox-check --server-config examples/sandbox/pass-server.json --case examples/mcp/lookup-case.json`,
  analysesReconcile: (taskId: string) => `${cli} analyses reconcile ${taskId}`,
};

const guide = "/docs/27-local-development-guide";
export const docs = {
  start: `${guide}#启动网页`,
  container: `${guide}#受控容器执行`,
  model: `${guide}#模型分析与配置`,
  records: `${guide}#运行记录与恢复`,
  mcp: `${guide}#mcp-stdio-调用`,
};

export const apiAddress = "127.0.0.1:8030";
export const defaultStateDir = "artifacts/run-store";

/** Variable names only. Values are never read or shown by the page. */
export const modelVariables = [
  { name: "AWB_MODEL_BASE_URL", purpose: "兼容接口的地址，可以带 /v1。" },
  { name: "AWB_MODEL_NAME", purpose: "模型名称，需是支持列表中的名称。" },
  { name: "AWB_MODEL_API_KEY", purpose: "接口密钥。只放在进程环境里，不要写进文件或命令参数。" },
  { name: "AWB_MODEL_LIMIT_PROFILE", purpose: "输入与输出上限的配置名。" },
] as const;
