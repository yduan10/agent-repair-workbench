# UI-06：文档阅读器公开发布安全审计

日期：2026-10-13。基线：`82b1a23ccf2ecd6c93ea79218bc6322729fcca6b`。方法：企业代码审计 skill，General SaaS / Mission-Critical；独立只读检查。

## 1. 结论与范围

**公开内容与供应来源专项 Pass，100/100。** Defect P0/P1/P2/P3均0，无扣分、封顶或豁免。结论仅适用于本批公开安全性，不替代独立UI功能/可访问性/Mermaid行为评审，也不表示UI-06远端CI已通过。

检查基线后的20个修改/新增候选文件，共344,528字节：

- `docs/{02-architecture,03-roadmap,06-dependencies,20-ui-05-public-source,21-ui-06-document-reader}.md`、`docs/README.md`、`docs/reviews/CI-01-review.md`。
- `frontend/app/docs/page.tsx`、`frontend/app/docs/[...slug]/page.tsx`、`frontend/app/globals.css`。
- `frontend/components/document-diagram.tsx`、`frontend/lib/{docs.server,documentation,milestones}.ts`。
- `frontend/package.json`、`frontend/package-lock.json`。
- `frontend/tests/{appearance,document-reader,guidance,reviewer-document-reader}.spec.ts`。

锁文件按供应来源元数据单独批量检查，不将其3000余行机械展开为功能代码评审。原有CI和路径助手仅为直接依赖只读核对。

## 2. 生产事故风险推演

本批未发现可确认的公开泄露或供应来源阻断项，无P0/P1事故条目。构建输入由维护者控制；未来在docs中新增内部材料会随站点构建公开，必须继续执行公开内容审计。

## 3. 检查证据

- 候选全文件扫描：没有命中常见提供方令牌、私钥、JWT、URL内嵌凭据、长字面量密钥赋值、个人主目录绝对路径、RFC1918地址；没有二进制、符号链接或超过1MiB的候选文件。文档事实补录不含个人原始trace。
- 未读取`.env`、原始运行产物、模型配置或其他项目。扫描结果不输出疑似秘密值。
- `docs.server.ts`只从前端工作目录的同仓README和docs递归读取`.md`；路由参数仅匹配预先枚举的slug，不进入readFile路径。当前README/docs根及docs子树无符号链接；目录枚举不会沿符号链接项递归。该实现并不调用Git过滤，docs应持续只放可公开材料。
- 阅读器禁用raw HTML/MDX，远程图片不加载；外链只允许HTTP(S)，绝对路径/非HTTP协议/根外相对路径拒绝。非文档链接拼接公开GitHub源码地址，不转为本地文件读取。
- 锁文件相对基线新增/变化220个包条目，均使用HTTPS `registry.npmjs.org`和`sha512-`完整性，没有新增安装脚本、私有源、嵌入身份信息或本机依赖路径。
- 三个新增直接依赖锁定版本与许可证一致：react-markdown10.1.0、remark-gfm4.0.1、Mermaid12.2.0，均MIT；依赖说明已同步。
- 独立执行`npm audit --package-lock-only --ignore-scripts --json`，退出码0：`"vulnerabilities": {}`，`"total": 0`；依赖统计325。仅表示执行时公告扫描未发现已知漏洞，不保证依赖无未知漏洞。
- CI未新增写权限、部署令牌或外部代码自动准备；既有构建在frontend目录执行，与同仓文档读取根一致。

## 4. 十二维度覆盖

| 维度 | 本专项结论 |
|---|---|
| 架构/边界 | 请求参数不进入磁盘路径，文档范围固定 |
| SOLID | 无本专项结构缺陷 |
| 并发/资源 | 没有公开审计新增执行资源；运行行为另有UI评审 |
| 容错 | 未登记slug不读取任意路径 |
| 性能 | 候选无意外大文件；加载性能属于UI评审 |
| 安全/合规 | 内容扫描与路径检查未发现泄露 |
| 可观测 | 历史CI事实与UI-06待验收明确区分 |
| 类型契约 | 不以路由输入构造文件名 |
| 可测试性 | 路径拒绝测试纳入候选；本专项未重复功能测试 |
| 工程规范 | 本批源码、文档、测试、锁文件范围明确 |
| 数据完整性 | 无数据库/用户数据改动或原始trace入库 |
| 依赖治理 | 公共源、摘要、版本/许可证与公告扫描通过 |

## 5. 整改清单

无本专项待修项。新增文件或渲染读取范围改变后补充审查；UI功能结论以另一份独立评审为准。

## 6. 后续维护

1. docs目录作为公开构建输入维护，内部笔记和运行报告继续放忽略的产物目录。
2. 后续锁文件变化继续核对源、完整性、安装脚本及公告；不将一次零公告结果当作永久保证。

## 7. 快照与声明

审计者未修改实现、未安装依赖、未提交或推送。完整扫描清单保留独立审查目录，不再发布整套自循环manifest。关键文件SHA-256：

```text
e6efc598fd00e60211b541f03345e5eedf20fbd79e7b654516b28e2bd57e097f  frontend/lib/docs.server.ts
0cf661a6689b44474378e092c4cbc89168a32431af52df732c3a0f3906a82681  frontend/app/docs/[...slug]/page.tsx
c31e015c8cd86ebb2878cdcbb1109ef29624cf24c7bbb5b27270d66d89c4a935  frontend/package-lock.json
```

本专项范围内无未评估内容；产品功能完整性、Mermaid绘制与UI行为由专职UI评审负责，明确不在本报告的Pass范围内。
