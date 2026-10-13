# 合成证据示例

两个 JSON 都是本项目编写的 synthetic fixture，没有连接真实 MCP server，也不是已经复现的公开 issue。

- `passing.json`：声明整数 count，记录返回整数 2。
- `failing.json`：同一声明下记录返回字符串 "2"，应输出 `output_schema_violation` 并退出 1。

示例仅检查已记录的观察。修改 JSON 不代表修复了真实工具；真实执行链和公开故障复现属于 P0-02。
