# UI-05 首次公开源码独立审计

- **对象**：首次提交前Git索引中的205个文件，合计1,202,104字节；以暂存字节为准，不以工作区内容代替索引。
- **日期**：2026-10-13。
- **授权**：用户明确授权创建公开GitHub仓库及首次提交、推送。本报告只审公开候选内容，不执行Git写入或发布。
- **方法**：企业审计的证据、风险与范围门禁；General SaaS / Mission-Critical。锁/源码/文档/合成样例和CI针对性公开检查，不重复大规模功能审计。
- **内容清单**：`UI-05-publication-manifest.json`，SHA-256 `bfaff9a652a5b678128a1c4ab242c0a8416d71377bf2ad7db11bf42fdd887211`。清单不包含自身和本报告，避免循环哈希。

## 1. 质量评估卡与发布门禁

**100/100，Pass：当前冻结索引可作为公开开发源码首次提交。** 无未关闭P0/P1/P2/P3；初轮个人机器绝对路径问题已修复复核。此结论不表示完整Agent能力、正式产品发布、开源许可证或公网部署已完成。

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 0 unresolved findings
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: Pass — reviewed index is suitable for public development-source publication
NOT ASSESSED: actual remote push/CI execution; whole-product maturity is outside this audit
```

## 2. 风险核查结果

- 未发现私钥、常见供应商/GitHub/GitLab/Slack token、AWS访问标识、Google API key、JWT、Bearer字面凭据或URL内嵌认证。
- 未发现真实个人机器绝对路径、私人临时目录、个人原始会话trace、私网地址、环境配置、数据库或模型调用产物进入索引。
- 未发现二进制、符号链接、子模块或单文件大于1MiB；205项索引mode均为100644。最大文件是约108KiB的uv锁。
- `.env`、`.env.local`、artifacts、node_modules、.next、.venv由git check-ignore确认忽略。未读取这些忽略路径里的凭据、用户数据库或模型探针内容。
- 主/实验uv锁及npm锁使用公开PyPI、pythonhosted、npm来源；代码归档与文档链接为公开GitHub或官方文档。没有私有SSH源或认证参数。loopback与保留测试域名为本机服务/合成负例，不当作私人服务泄漏。

这些结论来自模式扫描和命中上下文人工核对，不宣称可以数学证明任意编码、拆分或未知格式的秘密不存在。

## 3. 发现与关闭记录

### P0 / P1

none。

### P2：初稿文档个人绝对路径，closed

初轮13份文档中的16处个人机器绝对路径已改为项目/审查目录占位符，README启动命令使用可复用路径。最终索引无此类真实路径命中。

`docs/README.md`说明路径脱敏会改变历史文档字节，旧评审摘要保留当时版本的含义，不伪造重写旧hash；本清单单独冻结当前公开字节。

扫描仍命中 `tests/test_docker_control.py:99,103` 两处用户目录形状字符串。人工核对为测试自己构造的Docker socket路径负例，使用合成身份，不是实际个人目录、凭据或运行trace，允许保留。

### P3

none。README已明确尚未选定项目开源许可证；公开可见不被描述为额外许可授予。

## 4. 维度覆盖声明

| # | 维度 | 本轮结论 |
|---|---|---|
| 1 | 架构与边界 | 公开开发源码范围明确，不扩大现有执行权限 |
| 2 | SOLID与设计 | 不变；功能实现沿用独立后端/UI评审 |
| 3 | 并发资源 | CI job有10/15分钟上限，UI独立数据库和端口 |
| 4 | 容错 | 流水线失败会停止job；远端尚未实际执行 |
| 5 | 性能 | 无意外大文件、依赖缓存或运行产物 |
| 6 | 安全合规 | 敏感扫描与脱敏复核通过；不上传模型配置/trace |
| 7 | 可观测性 | 保留初审→修复→复审历史，不伪造旧快照 |
| 8 | 类型契约 | 未改运行契约，沿用已审测试证据 |
| 9 | 可测试性 | 合成样例明确；默认CI不自动启动Docker或下载历史源码门禁 |
| 10 | 工程规范 | 权限/许可证/源码公开与产品发布表述有区分 |
| 11 | 数据完整性 | 索引字节逐项SHA复核，真实SQLite/报告不纳入公开 |
| 12 | 依赖供应链 | 锁与安装命令一致，action固定SHA、无凭据保留 |

## 5. CI公开仓库适配

`.github/workflows/checks.yml`使用push/pull_request，contents:read；checkout不保留凭据，actions固定SHA。没有pull_request_target、高权限仓库写入、secret注入、自托管runner或评论自动执行。uv使用frozen，Node使用npm ci；浏览器服务仅loopback，真实SQLite网页测试使用一次性目录。未发现需要个人机器路径或账号配置才能运行的CI步骤。

没有在本轮重复联网验证此前审核过的action SHA，也没有冒称GitHub Actions已通过。首次推送后应查看远端结果并如实追加证据；本地通过不能替代远端运行。

## 6. 可公开范围与后续变更

批准本清单覆盖的源码、合成fixtures、测试、依赖锁、规格与脱敏评审。继续排除忽略产物，勿force-add凭据、数据库、模型探针或浏览器报告。

本报告和内容清单可随首次提交公开；二者不含个人绝对路径或秘密，且清单明确排除二者。随后docs20/roadmap补充真实仓库、提交号和CI结果属于新文档字节，应保留当前清单为发布前历史快照，不将旧SHA冒充后续版本。运行代码变化需要相应增量审查。

## 7. 审计声明

未修改源码、暂存区、提交历史、仓库权限或远端。此次索引扫描包括新增UI页面、公开仓库链接、文档和独立测试；UI实现行为依据单独的UI-05独立评审，不重复启动整个测试矩阵。未读取任何其他项目、个人记忆或凭据。

最终索引内容复核205项均与扫描时SHA一致。功能回归、真实模型/工具执行、远端推送与CI、正式发行许可及稳定产品上线均不由本次公开内容审计替代。
