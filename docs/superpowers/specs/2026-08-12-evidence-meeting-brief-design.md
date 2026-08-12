# Evidence-Bound Meeting Brief 设计

## 1. 目标

新增 `research-os meeting-brief`，把一个课题当前已经核验的证据、冲突、Idea、方法学边界和下一步压缩成可直接用于组会或导师沟通的 Markdown/JSON 简报。它必须回答四个问题：现在知道什么、哪里仍不确定、当前 Idea 为什么值得讨论、需要导师决定什么。

这不是另一套科研状态机。命令复用 `dashboard`、证据账本、Idea archive、cycle 产物校验和知识推荐，只负责从严格结构化事实生成决策视图。

## 2. 方案比较与选择

1. **证据绑定的组会简报（采用）**：本地、确定性、无模型成本，能立即减少周报和导师汇报整理工作。
2. **自动在线论文抓取**：信息新，但需要搜索质量评估、版权边界、网络失败恢复和来源核验，不能作为本轮单一增量。
3. **跨课题组合管理**：适合多个成熟课题，但当前用户更需要把第一个方向推进为可讨论决策。

## 3. 用户入口

```powershell
research-os meeting-brief `
  --project medical-reasoning `
  --as-of 2026-08-12 `
  --format markdown
```

`--format` 支持 `markdown` 和 `json`，默认 `markdown`。`--as-of` 省略时使用本地日期；显式日期保证可复现。命令只写标准输出，用户需要文件时使用 PowerShell 重定向。

## 4. 输出契约

### 4.1 课题决策状态

输出标题、slug、截止日期、当前阶段、状态、阻塞和是否存在人工 Idea 决策。状态完全来自已校验的 dashboard。

### 4.2 证据主张

每条有效 claim 保留：

- `claim_id`、statement、type、status、confidence；
- 支持与反对证据的 `source_id + locator`；
- limitations。

claim 按结构化状态路由：

- `verified` 且非 conflicted → 已支持；
- `conflicted` → 存在冲突；
- `unverified` 或 `partially_verified` → 仍待核验。

任何有 claim 级校验问题的条目都不得进入上述三组，而是进入“排除项”，显示 issue code 和原因。简报不得把 inference/hypothesis 改写为事实，不得省略 limitations。

### 4.3 当前 Idea

只显示 active run 中通过现有 archive/cycle 校验且未被拒绝的 Idea，最多四个，稳定按 `idea_id` 排序。每个 Idea 显示研究问题、假设、贡献、证据来源、新颖性状态、四项评分、方法风险、医疗安全风险、失败判据、外部实验边界和人工决定理由。没有 active run 时明确显示“尚未启动”，而不是猜测候选。

### 4.4 决策问题与行动

简报最多生成三个稳定的导师讨论问题：

1. 若有阻塞，先确认阻塞修复；
2. 若等待人工 Idea 决策，讨论 shortlist；若已选 Idea，讨论失败判据和实验边界；
3. 若有冲突或待核验 claim，讨论优先补证；否则讨论当前方法学风险。

执行行动直接复用 dashboard 的最多三个行动，不从 claim statement、来源 notes 或模型自由文本拼接 shell 命令。

### 4.5 方法学参考

最多显示 dashboard 已核验的三项方法学来源，并明确它们只是方法指导，不能自动成为当前课题引用证据。

## 5. 架构

新增 `src/research_os/meeting_brief.py`，负责不可变数据模型、严格聚合和 Markdown 渲染。CLI 只负责日期解析、JSON 序列化和输出。

为避免混合两个不同时间点或被替换的同名课题目录，`meeting-brief` 在任何业务读取前捕获一次 project identity，并把它传给 dashboard、manifest、ledger、Idea archive 和 active cycle 读取。`build_project_dashboard` 增加仅供内部编排使用的可选 `expected_project_identity`；未传入时行为与 v0.5 一致。

JSON 固定 `schema_version: 1`，所有 tuple 显式转为 list。Markdown 输出顺序固定，不包含当前时间、随机数或文件系统遍历顺序。

## 6. 失败语义与边界

以下情况以 CLI 错误码 2 失败关闭，不输出部分简报：

- 项目目录、ledger、archive 或 cycle 产物发生链接/替换/身份漂移；
- project slug、active run、Idea archive 归属不一致；
- 知识库存在但损坏；
- 日期格式无效；
- cycle 哈希或评审门禁不一致。

命令不联网、不调用 provider、不修改文件、不执行实验，也不处理真实病例或个体诊疗请求。它生成的是研究管理简报，不是临床决策支持。

## 7. 验收证明

自动化测试必须覆盖：

- valid/conflicted/open/excluded 四类 claim 路由和逐条 locator；
- active Idea 的问题、失败判据、风险与人工理由；
- 无 cycle、等待人工和已完成三种状态；
- Markdown/JSON 确定性、最多三个问题和三个行动；
- 命令前后工作区字节完全一致；
- 同名项目目录替换、archive 归属错误和无效日期失败关闭；
- installed wheel 在源码目录外完成一个医疗诊断推理旅程。

端到端示例必须证明：输入一个含支持证据、反对证据、未核验假设和一个通过人工门禁 Idea 的医疗诊断推理课题，输出能直接呈现“结论—定位—限制—冲突—决策—下一步”，且不会把未核验内容写成事实。

## 8. 非目标

本轮不做联网检索、自动引用格式化、向量数据库、全文摘要、幻灯片生成、实验执行或自动批准 Idea。这些能力只有在证据边界和当前简报契约稳定后再单独设计。
