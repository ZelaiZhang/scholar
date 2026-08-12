# Research OS v0.4 科研方法知识库设计

日期：2026-08-12
状态：设计已获用户方向批准，等待书面规格复核

## 1. 背景

Research OS v0.3 已经提供证据优先、可恢复、受预算约束的科研指导循环，但全局 `library/literature-matrix.csv` 仍基本为空。目前系统能判断“下一步做什么”，却没有稳定的跨课题方法学底座来回答：

- 医疗诊断 AI 研究应采用哪类评价与报告规范；
- Chain-of-Thought、过程监督、自一致性和可观察理由之间有什么区别；
- RAG、微调、量化、DPO 与 RLHF 分别适合解决什么问题；
- 一个候选方法需要哪些基线、消融、外部测试和失败判据；
- 某篇论文是只读过摘要，还是已经全文核验并可以进入引用链。

v0.4 新增一个本地、结构化、可审计的科研方法知识库。它不是通用聊天记忆，也不是未经核验的向量数据库。结构化来源登记和知识卡是唯一真源；主题地图、方法手册和项目推荐都是可重建派生物。

## 2. 设计依据

首批方法学依据包括：

- AI 科研自动化：Nature 论文 *Towards end-to-end automation of AI research*（DOI `10.1038/s41586-026-10265-5`）和 *Towards an AI co-scientist*（arXiv `2502.18864`）。前者支持候选档案、检索、新颖性筛查、科研日志和多阶段审查，但也表明全自动输出存在一致性与质量上限；后者强调研究者目标约束和多智能体竞争性审查。
- 医疗语言模型与诊断：*Large language models encode clinical knowledge*（DOI `10.1038/s41586-023-06291-2`）、*Towards accurate differential diagnosis with large language models*（DOI `10.1038/s41586-025-08869-4`）和 *Towards conversational diagnostic artificial intelligence*（DOI `10.1038/s41586-025-08866-7`）。这些工作要求评价不能只看考试或单一准确率，还要覆盖伤害、偏差、沟通、工作流和外部适用性。
- 推理与证据：Chain-of-Thought（arXiv `2201.11903`）、Self-Consistency（arXiv `2203.11171`）、过程监督（arXiv `2305.20050`）、RAG（arXiv `2005.11401`）和 Self-RAG（arXiv `2310.11511`）。系统只保存可公开复核的简洁依据和验证记录，不保存或索取模型隐藏思维链。
- 模型适配：LoRA（arXiv `2106.09685`）、QLoRA（arXiv `2305.14314`）和 DPO（arXiv `2305.18290`）。知识库记录论文报告的适用条件与限制，不把单篇结果改写为普遍最优实践。
- 医疗 AI 方法规范：TRIPOD+AI（DOI `10.1136/bmj.q902`）、PROBAST+AI（DOI `10.1136/bmj-2024-082505`）、STARD-AI（DOI `10.1038/s41591-025-03953-8`）、FUTURE-AI（DOI `10.1136/bmj-2024-081554`）、DECIDE-AI（DOI `10.1038/s41591-022-01772-9`）和 CLAIM 2024（DOI `10.1148/ryai.240300`）。

报告规范只以“适用范围、版本关系和原文链接”的形式进入知识库。除非许可明确允许，不复制完整清单或受版权保护的全文。

## 3. 目标与非目标

### 3.1 目标

1. 建立跨课题复用的科研方法来源目录、知识卡、主题地图和方法手册。
2. 明确区分元数据核验、摘要核验和全文核验，防止摘要线索被当作全文证据。
3. 让 `guide` 根据课题画像和当前阶段给出最多三项方法学参考，同时继续保持唯一下一步动作。
4. 提供确定性、本地可解释的检索与推荐，不依赖外部 API。
5. 为医疗 AI 自动提示适用的报告规范、偏倚风险工具和临床评价边界。
6. 保留项目证据隔离：全局知识卡不会自动成为项目可引用证据。
7. 支持未来增加本地向量索引，但不让向量结果成为证据真源。

### 3.2 非目标

- 不下载或提交无明确许可的论文全文。
- 不处理真实病例、可识别健康信息或临床诊疗请求。
- 不执行微调、量化、强化学习、训练或任何实验。
- 不自动宣称研究空白、新颖性、临床有效性或投稿准备完成。
- 不在 v0.4 实现在线自动更新、网页爬虫、Zotero 双向同步或向量数据库。
- 不把模型隐藏 Chain-of-Thought 持久化；只记录简洁理由、证据定位、冲突和结论边界。

## 4. 方案比较

### 4.1 纯 Markdown

优点是透明、便携和易于人工维护。缺点是字段漂移、去重困难、无法稳定做项目级推荐。它适合作为阅读界面，不适合作为唯一数据模型。

### 4.2 向量数据库优先

优点是语义搜索灵活。缺点是召回不可完全解释，容易混淆论文原文、摘要和模型推断，还会引入模型、索引版本和额外依赖。当前知识规模不足以证明其复杂度合理。

### 4.3 分层混合知识库（采用）

YAML/JSONL 结构化目录和带来源定位的知识卡是唯一真源；Markdown 地图和手册提供人类阅读体验；本地确定性索引提供搜索和推荐。等经过核验的知识卡超过 100 张后，再单独评估可重建的本地向量索引。

## 5. 目录结构

```text
library/knowledge/
  catalog.yaml
  aliases.yaml
  cards/
    <source_id>.md
  maps/
    ai-for-science.md
    medical-ai.md
    reasoning-and-cot.md
    rag-and-evidence.md
    finetuning-quantization-rl.md
  playbooks/
    literature-search.md
    medical-ai-study.md
    llm-adaptation-study.md
    evaluation-and-ablation.md
  reporting-guidelines/
    applicability.yaml
    medical-ai-reporting.md
  seeds/
    v0.4-sources.txt
```

项目可以包含可选画像：

```text
projects/<slug>/knowledge-profile.yaml
```

旧课题不强制迁移。缺少画像时，`kb recommend` 返回通用方法学参考和一条明确的画像补全提示，但不会修改项目。

## 6. 数据模型

### 6.1 CatalogEntry

`catalog.yaml` 顶层字段固定为 `schema_version` 和 `entries`。每条 entry 必须包含：

```yaml
source_id: src-...
canonical: 10.1038/...
title: ...
authors: [ ... ]
year: 2025
source_type: paper
venue: Nature
topics: [medical-ai, diagnostic-reasoning]
methods: [llm, differential-diagnosis]
stages: [problem-definition, experiment-design, writing, review]
priority: core
verification:
  metadata: verified
  abstract: verified
  fulltext: unverified
reviewed_at: 2026-08-12
status: active
superseded_by: ""
access_url: https://...
license: unknown
notes: ""
```

约束：

- `source_id` 必须存在于 `library/sources.jsonl`。
- `canonical` 在目录中唯一，并与来源登记表一致。
- `topics`、`methods`、`stages` 必须来自受控词表。
- `priority` 只能是 `core / background / watch`。
- 三种 verification 只能是 `unverified / verified / unavailable`。
- `fulltext: verified` 必须存在知识卡且至少有一个页码、章节、表格或稳定网页小节定位。
- `status` 只能是 `active / superseded / retracted / inaccessible`。
- `superseded` 必须填写有效的 `superseded_by`；被替代规范不进入默认推荐。

### 6.2 Knowledge Card

卡片位于 `cards/<source_id>.md`，包含固定 YAML front matter 和下列正文区块：

1. 阅读范围；
2. 研究问题与设置；
3. 方法；
4. 已报告事实，每项带 locator；
5. 作者报告的限制；
6. 模型综合推断，明确标记 `method_inference`；
7. 可迁移方法建议；
8. 不应外推的结论；
9. 与其他来源的关系；
10. 人工备注保护区。

仅查看摘要时，卡片可以记录摘要明确报告的事实，但 locator 必须写为 `abstract`，且不能生成全文细节、实验表格数值或论文内部结论。

### 6.3 KnowledgeProfile

```yaml
schema_version: 1
domains: [medical-ai]
tracks: [diagnostic-reasoning, rag, finetuning]
study_type: offline-model-evaluation
data_modalities: [text]
reporting_context: [prediction-model, diagnostic-accuracy]
```

字段必须来自受控词表。画像不包含病例、数据集原文或任何个人信息。

## 7. 检索和推荐

### 7.1 CLI

```powershell
research-os kb search "external validation calibration" `
  --topic medical-ai --limit 10

research-os kb recommend --project medical-reasoning

research-os kb doctor
```

`kb search` 支持 `--topic`、`--method`、`--stage`、`--priority`、`--verified-scope`、`--limit` 和 `--format text|json`。相同输入和目录内容必须得到相同排序。

### 7.2 确定性排序

先应用显式过滤，再按下列权重排序：

- 标题精确词命中：8；
- alias 命中：6；
- topic 命中：5；
- method 命中：4；
- stage 命中：3；
- 卡片小节标题命中：2；
- 正文普通词命中：1。

同分时依次按 `priority`、`fulltext verification`、年份降序、`source_id` 升序排序。默认不返回 `retracted`；`superseded` 仅在显式请求历史版本时返回。

### 7.3 项目推荐

`kb recommend` 读取项目画像、当前 `guide` 阶段和知识目录，最多返回三项：

1. 当前阶段核心方法来源；
2. 最匹配的方法手册；
3. 医疗 AI 适用的报告或风险规范。

推荐结果包含“为什么推荐、核验范围、能用于什么、不能用于什么”。元数据未核验或状态为 watch 的条目不能作为核心推荐。

`guide` 增加“方法学参考”区块，但不改变 `NextAction` 数量。知识库损坏时，`guide` 仍能展示项目状态，不过方法学区块显示受阻，并推荐先运行 `kb doctor`；不得因知识库损坏自动改写项目文件。

## 8. 项目证据隔离

- 全局 catalog entry 和知识卡默认只是方法学线索。
- 只有已在目标 `project.yaml` 中显式关联的 `source_id` 才能进入该项目证据账本、外发上下文或论文引用。
- 从知识库选择来源时，系统输出明确的 `paper-intake` 登记/关联命令，不直接修改项目。
- 跨项目推荐可以共享方法卡，但不能共享项目 claim、人工笔记、候选 Idea 或结果。
- `manuscript-assistant` 只能引用项目已关联且满足阅读范围要求的来源；全局知识条目只能提示引用缺口。

## 9. 种子库构建

v0.4 首批验收规模为：

- 至少 24 条去重来源记录；
- 至少 16 张摘要或全文已核验知识卡；
- 其中至少 8 张全文或开放网页正文已核验卡；
- 5 张主题地图；
- 4 份方法手册；
- 1 份医疗 AI 报告规范适用性矩阵。

`seeds/v0.4-sources.txt` 每行一个 DOI、arXiv 或公开 URL。通过一次原子 `add-sources` 登记，不加 `--allow-external-api`，任一来源格式失败则整批不写入。登记后必须核对每个 catalog `source_id` 均存在于 `sources.jsonl`。

优先级：

- `core`：直接决定 Research OS 方法门禁或医疗安全边界；
- `background`：解释方法谱系和适用条件；
- `watch`：新近但尚未充分核验，不进入默认项目建议。

## 10. 主题地图与方法手册

主题地图回答“领域里有哪些方法、共识、冲突和空白”，不写单一最佳方法。每个结论链接到卡片及其核验范围。

方法手册回答“做这类研究时应该检查什么”，包括：

- 问题定义和目标人群；
- 数据来源、标签、泄漏和划分；
- 基线、消融、指标、校准和统计不确定性；
- 外部测试、亚组、公平性和分布漂移；
- 失败判据与不能支持的结论；
- 适用报告规范；
- 可交给 `experiment-advisor`、`mock-reviewer` 或 `manuscript-assistant` 的结构化问题。

手册不能把指南清单复制为受版权保护的长文本；只保存本系统的操作映射和原文链接。

## 11. 更新与过期策略

v0.4 不自动联网更新。`kb doctor` 做本地确定性检查：

- catalog schema、受控词表和重复 canonical；
- source registry 一致性；
- 卡片存在性和 locator 门禁；
- `superseded_by` 链是否有效且无环；
- `reviewed_at` 超过 365 天时警告；
- 报告规范状态和替代关系；
- 主题地图或手册引用的 source_id 是否存在；
- 路径 containment、符号链接和 reparse point。

网络可达性和最新版本核对由显式的人工维护流程完成，结果先进入 `watch`，通过核验后才能转为 `active`。

## 12. 写入与人工内容保护

- catalog、aliases 和机器生成区块使用原子写入。
- 不覆盖知识卡的人工备注保护区。
- 同一 canonical 再次登记只更新机器元数据和核验状态，不改变人工 notes。
- 写入前后验证知识库根目录身份，拒绝 junction、symlink 和目录替换。
- 批量种子登记、catalog 更新和派生地图生成分别事务化；其中一层失败不报告整体完成。
- 派生物必须能从 catalog 和 cards 重建，人工手册除外。

## 13. 错误处理

- catalog 损坏：`kb` 命令退出 2，不做部分搜索或猜测解析。
- 来源不存在或漂移：`kb doctor` fail，推荐结果排除该条目。
- 只有摘要却声明全文：fail，要求修正 verification 或补充可定位全文卡。
- 报告规范被替代：默认推荐新版本，同时保留历史关系。
- 项目画像损坏：`kb recommend` fail，不退化为从自由文本猜测医疗场景。
- 知识库无匹配：返回空结果和下一轮检索建议，不生成伪来源。
- 发现可识别健康信息：立即停止卡片生成和任何外发。

## 14. 测试设计

### 14.1 单元测试

- catalog、card 和 profile 严格 schema；
- canonical/source_id 去重；
- verification 与 locator 联动；
- supersession 无环；
- 确定性搜索权重和同分顺序；
- metadata-only 条目不能冒充全文证据；
- retracted/superseded 默认排除；
- 人工备注不被覆盖。

### 14.2 集成测试

- `kb search` 的 text/JSON 输出；
- `kb recommend` 根据医疗文本课题和阶段返回正确方法包；
- `guide` 保持恰好一个下一步动作，同时显示最多三项方法学参考；
- 全局知识卡不能绕过 project source_ids 进入证据账本或外发上下文；
- `kb doctor` 检出失效来源、卡片缺失、陈旧规范和目录逃逸；
- 旧工作区没有 knowledge profile 时仍可使用原有 doctor/guide。

### 14.3 端到端测试

从安装 wheel 后的源码外目录执行：

1. `doctor`；
2. `kb doctor`；
3. `kb search`；
4. 新建医疗 AI 课题并写入画像；
5. `kb recommend`；
6. `guide` 显示方法学参考但仍只有一个下一步；
7. 将选中来源显式关联项目后验证引用资格；
8. 最终 `doctor` 全部通过。

## 15. 验收标准

v0.4 只有在下列条件同时满足时完成：

1. 目录和三种 CLI 命令可从安装 wheel 使用；
2. 种子库达到第 9 节的数量和核验门槛；
3. 每项 reported fact 都有 source_id 和与阅读范围一致的 locator；
4. 至少一个医疗 AI 项目能获得正确的阶段化方法推荐；
5. 全局来源不能绕过项目关联门禁；
6. `guide` 仍只给一个下一步；
7. 默认不联网、不外发、不下载受限全文；
8. 全量测试、warnings-as-errors、compileall、pip check、diff check 和安装 wheel 旅程全部通过；
9. 独立代码审查没有未解决的 Critical 或 Important。

## 16. 后续版本

v0.5 可以在至少 100 张核验卡基础上评估：

- 可删除和重建的本地向量索引；
- Zotero 单向导入；
- 显式联网的版本检查；
- 主题订阅和每周新增文献分诊。

这些能力不得改变 v0.4 的真源、证据隔离和人工门禁。
