# 企业代码质量审计报告：P0-06 H4 案例身份与网页契约

- **审计对象**：repair_reader/models.py、reader.py、frontend/lib/repairs.ts、repair-workspace.tsx 增量及相关测试；10文件约280新增行。
- **审计版本**：工作树，文件摘要见文末；主评审者 root，独立于H4实现者 final_review。
- **技术栈**：Python/Pydantic/FastAPI、TypeScript/Zod/React。
- **业务场景**：General SaaS，本机可信单用户。
- **审查严苛度**：Mission-Critical。
- **审计时间**：2026-10-14。

## 1. 代码质量评估卡

- **综合质量得分**：100/100（仅此冻结增量，无未关闭确认缺陷，不代表全产品无缺陷）。
- **上线评估结论**：Pass，可整合此增量；不替代H1/H2/H3评审、真实模型保留实验和P0-06总门禁。
- **未评估项**：全产品安全、任意仓库支持、多租户与模型修复效果均不在本审计范围。

| P0 | P1 | P2 | P3 |
|---|---|---|---|
| 0 | 0 | 0 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 0 -> 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100
VERDICT: Pass, scoped integration only
```

## 2. 生产事故风险推演

无未关闭P0/P1。已验证失效路径：伪造/交叉基线摘要时服务端拒绝推导案例；旧schema1、未知case、错误失败指纹与缺槽不能显示通过。混用新前端与旧API会显式拒绝响应，因此部署须协调API重启与前端构建，不做静默兼容。

## 3. 详细审计明细

### P0 — 阻断性缺陷
none。

### P1 — 严重缺陷
none。

### P2 — 主要缺陷
无未关闭项。联调发现重复选择当前任务清空详情，作者已在choose同ID直接返回，真实API浏览器复测通过。评审要求外层Zod判定访问slots[0]前显式检查四槽，已增加；独立0/1/3槽反例证明safeParse失败且不抛异常。未将未实际复现的原异常猜测记作确认生产缺陷。

### P3 — 次要缺陷
none。

## 4. 维度覆盖声明

| # | 维度 | 结论 |
|---|---|---|
| 1 | 架构与边界 | 案例从持久baseline经固定profile绑定推导，HTTP不选规则 |
| 2 | SOLID与设计 | DTO投影与渲染分离，只增加两个封闭案例 |
| 3 | 并发与资源 | 沿用读worker限额/取消；无新增外部副作用 |
| 4 | 容错 | 未知/跨case/畸形槽显式拒绝；同任务重选不清空 |
| 5 | 性能 | 原50条及512KiB限额未放宽；case解析固定2项 |
| 6 | 安全与合规 | 无路径、模型原文、secret、规则定义外泄；只读 |
| 7 | 可观测性 | 人类可读case名；历史与当前核验分离 |
| 8 | 类型与契约 | list/detail升级v2；comparison/diff保留v1，严格枚举 |
| 9 | 测试 | 新独立20边界、真实SQLite/API、浏览器标签验证 |
| 10 | 工程规范 | Ruff/mypy/TS通过，变更已冻结 |
| 11 | 数据完整性 | 无迁移/旧记录重写，case不来自用户字段或全局当前case |
| 12 | 供应链 | 无新依赖、lock未改；全供应链漏洞扫描不属本批 |

## 5. 整改清单与复核

| 项 | 负责人 | 状态 | 证据 |
|---|---|---|---|
| 同任务重选详情丢失 | final_review | closed | 真实临时API两case联调复跑 |
| 缺槽边界防御 | final_review | completed | 独立20项schema检查含0/1/3槽及混合指纹 |

评审者亲自运行：

```text
45 Python targeted checks: exit 0
Success: no issues found in 4 source files
All checks passed!
20 independent schema checks passed
17 passed (10.3s)
```

命令：`uv run --frozen pytest -q tests/test_repair_case_reader.py tests/test_repair_read_api.py tests/test_repair_reader.py tests/test_repair_reader_review.py`；`node tests/repair-case-schema-review.cjs`（frontend下）；`AWB_REPAIR_CASES_LIVE_URL=http://127.0.0.1:8037 PLAYWRIGHT_CHANNEL=chrome PW_PORT=3019 npx playwright test --config tests/repair-cases.config.ts`。

实链路只验证真实临时SQLite中两case ready记录的投影/导航；成功comparison DTO是明确合成的契约反例，不冒充模型结果。API读服务由作者启动，评审者独立执行上述浏览器测试。未操作主用户库。

## 6. 架构防腐与长效治理建议

1. 保持list/detail schema显式升级与配套前端部署，代价是同步重启；防止旧客户端悄悄忽略案例身份。
2. 后续profile新增必须增加互换/混合失败指纹反例，单个case约数条确定性测试；禁止将错误码集合放宽成通用成功条件。

## 7. 审计声明

无豁免。只批准下列SHA的H4增量与独立检查脚本，不等于P0-06整体完成。后续修改须增量复审。

```json
{
  "src/agent_workbench/repair_reader/models.py": "ae8e4fba3261f8b1ff8a65325c41735cb8efd1d79fbe7dd2d0cd156a13e93513",
  "src/agent_workbench/repair_reader/reader.py": "31003f96532353c6e91a654498069e390a06cb4221b623647608f6194c42b90a",
  "frontend/lib/repairs.ts": "76af9f39d0ee32abd656d578af4572055aba53ff561e626d3a795ae1fc93bf88",
  "frontend/components/repair-workspace.tsx": "f9de2c68767ba6dbdd429e9cf6dca69a69cfdb48571f49287089c1c4719aec4e",
  "tests/test_repair_read_api.py": "c4653b8cb96171e0288ef9bd53dc9320a82d4d574cc62bbff129f96b27a817f4",
  "tests/test_repair_reader_review.py": "89e262ccbbcabfc7b0787a4e81a4f3b661cbd0ffc4c3bed24db54b3ee422fd8d",
  "frontend/tests/repairs.spec.ts": "9d8431f72d7ed8c319755acf05bb8b6c1ed8456c0fedd4a0af880c02dff84f6f",
  "tests/test_repair_case_reader.py": "be0ba67fe0a91891b09b2bedacae5d9f27d5bce7942d33cda5c0d184ccaebbc9",
  "frontend/tests/repair-cases.spec.ts": "e85192bd8e9568308a7f234f9a3111830253d75b5a01dfce5b8e0ff371adba52",
  "frontend/tests/repair-cases.config.ts": "051033dcefd2a1fb1a2e2d9eb616331caeb0f6e825c8f32e223134c2b4e4abf3"
}
```
