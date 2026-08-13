# Research OS v0.7：证据绑定论文写作计划设计

## 1. 目标

新增只读命令 `research-os manuscript-plan`，把当前课题的核验证据、Idea、实验设计、结果解读和写作门禁整理为可执行的论文写作计划。它不直接生成论文正文，而是回答：哪些章节现在可以写、能使用哪些事实、哪些内容只能作为推断或假设、还缺什么，以及下一步只应补哪一个缺口。

这个功能服务于研究生日常写作减负：避免在证据账本、Idea archive、实验设计、结果分析和稿件模板之间反复复制，同时防止模型把“看起来合理”误写成“已有证据支持”。

## 2. 外部工作流启发与边界

- [Agent Laboratory](https://arxiv.org/abs/2501.04227) 把科研工作分成文献、实验和报告阶段，并在摘要中报告人工逐阶段反馈能提高质量。本设计保留阶段化和人工门禁，但不执行实验。
- [Google AI co-scientist](https://research.google/blog/accelerating-scientific-breakthroughs-with-an-ai-co-scientist/) 使用生成、反思、排序和 meta-review 等专门角色，同时明确把事实核验和外部工具交叉检查列为后续限制。本设计复用 Research OS 已有的独立评审、meta-review 和证据核验，不把自动评分当作真值。
- [一项 2026 年真实任务案例研究](https://www.biorxiv.org/content/10.64898/2026.01.05.697809v1.full) 的摘要报告，所测框架没有完成从文献理解到验证结果和论文写作的完整闭环，但特定子任务可能有价值。因此本轮聚焦可审计的写作准备子任务，不宣称“自动科研”或“自动论文”。

以上资料只用于系统设计判断，不会自动进入任何课题的可引用证据范围。

## 3. 方案比较

### 方案 A：证据绑定写作计划（采用）

复用 `meeting-brief` 的严格 claim 路由、Idea 快照和行动建议，再加入章节可写性门禁。优点是边界清晰、无需新增外部依赖、直接减少写作前整理工作；缺点是不会自动生成流畅正文。

### 方案 B：自动生成完整初稿

减负最明显，但当前账本没有逐句稿件映射，结果文件也只允许保守解读。直接生成全文容易越过证据边界、隐藏冲突或把离线指标写成临床效用，因此本轮不采用。

### 方案 C：优先做 BibTeX/引文格式化

对投稿有用，但当前来源登记表并不强制记录完整作者、题名、年份和期刊。自动补齐会增加伪造元数据风险，必须等未来引入可验证元数据模型后单独设计。

## 4. 命令契约

```powershell
research-os manuscript-plan `
  --project medical-reasoning `
  --as-of 2026-08-13 `
  --format markdown `
  --workspace .
```

参数：

- `--project`：必填课题 slug；
- `--as-of`：可选 ISO 日期，默认本地当天；
- `--format`：`markdown` 或 `json`，默认 Markdown；
- `--workspace`：工作区路径。

命令只写 stdout，不创建或覆盖稿件，不调用外部 API，不执行实验。相同工作区字节与相同 `--as-of` 必须产生相同输出。

## 5. 数据模型

### 5.1 ManuscriptPlan

- `schema_version=1`
- `as_of`
- `project`：标题、slug、当前阶段和状态
- `overall_status`：`blocked`、`partial` 或 `ready_for_outline`
- `sections`：固定八个论文章节的就绪状态
- `citation_candidates`：允许进入事实性写作的 claim
- `open_facts`：尚未核验或仅部分核验、不得进入正文事实候选的 fact
- `research_statements`：只能以 `inference` 或 `hypothesis` 身份出现的研究陈述
- `conflicts`：冲突 claim 及其支持、反对定位与限制
- `excluded_claims`：因账本问题被排除的 claim 和 issue code
- `next_action`：恰好一个安全行动
- `boundaries`：非临床决策、非自动论文、非实验执行声明

### 5.2 CitationCandidate

只有同时满足以下条件的 claim 才能进入：

1. `type=fact`；
2. `status=verified`；
3. 当前课题显式关联的每个 `source_id` 已核验；
4. claim 没有任何账本校验 issue；
5. 至少一个支持来源含非空 locator；
6. limitations 非空。

输出必须保留 `claim_id`、statement、confidence、全部支持定位、反对定位和 limitations。系统只称其为“事实性写作候选”，不自动决定最终引用或措辞。

### 5.3 ResearchStatement

`inference` 和 `hypothesis` 即使有来源，也不能升级为事实。输出保留原标签、状态、支持/反对定位和限制，供 Introduction、Methods 或 Discussion 的人工论证使用。

`fact` 若为 `unverified` 或 `partially_verified`，单独进入 `open_facts` 并生成补证缺口，不得混入 citation candidates 或 research statements。

### 5.4 SectionReadiness

固定章节与门禁：

| 章节 | `ready` 条件 |
|---|---|
| Abstract | 已选 Idea、结果解读完成、至少一个事实性写作候选 |
| Introduction | 研究简报完成、至少一个事实性写作候选 |
| Related Work | 文献综合完成、至少一个事实性写作候选 |
| Methods | 人工已选 Idea、实验设计完成 |
| Experiments | 实验设计完成、已导入外部聚合结果 |
| Results | 已导入外部聚合结果、结果解读完成 |
| Limitations and Ethics | 至少一个带 limitations 的可用 claim；医疗课题存在 active Idea 时还需显式医疗安全风险 |
| Conclusion | 已选 Idea、结果解读完成、至少一个事实性写作候选 |

状态为 `ready`、`partial` 或 `blocked`。每节输出稳定的 `reason_codes`、人工可读原因、可用 claim IDs 和依赖产物路径。没有逐章 claim 标签时，系统不猜某条事实属于哪个章节；只提供候选证据包和门禁结果。

“结果解读完成”不是单独查找 `result-complete` 字符串：`06-result-analysis.md` 还必须为当前已校验 manifest 的每个直接结果文件恰好绑定一次文件名与 SHA256。结果或 provenance 集合变化会退回进行中；同名同哈希的离线文件身份替换不单独推翻科学解释。

“人工已选 Idea”同时要求 active cycle 的状态为 `completed`。中断或降级到其他状态时，即使 archive 暂时保留 selected 记录，也不得投影为 Methods 就绪。

## 6. 状态来源与一致性

`dashboard` 当前已经在一次受控读取中调用 `guide`，因此内部快照增加完整 `stages`，但不改变 dashboard 的公开 JSON schema。`meeting-brief` 内部保留该阶段快照，公开 Markdown/JSON 也不新增未承诺字段。`manuscript-plan` 只消费已经完成一致性校验的 meeting brief，不再次从磁盘拼接另一时间点的数据。

阶段名称通过稳定内部 code 传递，不依赖中文显示文本匹配。若为兼容当前 `GuideReport` 需要先增加 code，则公开 guide 文本保持不变。

任何 project、ledger、cycle、Idea archive 或 cycle 产物的既有安全校验失败时，命令退出 2，不输出伪装为可用的计划。

## 7. 唯一下一步

优先级固定：

1. 修复账本或无效来源；
2. 完成研究简报与文献证据；
3. 完成人工 Idea 选择；
4. 完成实验设计；
5. 等待并导入独立实验仓库的聚合结果；
6. 保守完成结果解读；
7. 使用 `$manuscript-assistant` 基于本计划建立论文大纲。

优先复用 dashboard 已验证的第一行动；当全部上游门禁通过时，固定输出：

```text
$manuscript-assistant 基于 <slug> 的 manuscript-plan 和核验证据账本创建论文大纲，不补写缺失引用或结果
```

## 8. Markdown 输出

顺序固定：

1. 课题与总体状态；
2. 八章节写作就绪表；
3. 事实性写作候选；
4. 推断与假设；
5. 冲突与排除项；
6. 唯一下一步；
7. 医疗与证据边界。

所有自由文本作为文本显示，不进入 shell 命令。命令只由受控模板和已验证 slug 构成。

## 9. JSON 输出

公开 schema version 固定为 1，显式序列化，不直接暴露内部 dataclass、文件 identity 或 snapshot token。列表顺序固定：章节按论文顺序，claim 按账本顺序，issue 按 code/claim_id 稳定排序。

## 10. 错误与安全

- 不访问网络、不调用 provider；
- 不读取或输出原始病例，不接受真实可识别健康信息；
- 不把 knowledge base 方法卡自动当作课题引用；
- 不把 conflicted、partially_verified、unverified、inference 或 hypothesis 放入事实性写作候选；
- 不解析外部实验原始数据，不声称统计或临床意义；
- 不覆盖 `writing/`、证据账本或任何人工文件；
- 项目文件、目录或身份漂移继续失败关闭。

## 11. 文件边界

- 新建 `src/research_os/manuscript_plan.py`：纯模型、路由、章节门禁、renderer 与 payload；
- 修改 `src/research_os/dashboard.py`：在内部快照保留 guide stage codes/status；
- 修改 `src/research_os/meeting_brief.py`：内部携带同一阶段快照，不改变既有公开输出；
- 修改 `src/research_os/cli.py`：增加命令解析和分发；
- 新建 `tests/test_manuscript_plan.py` 与 `tests/test_manuscript_plan_cli.py`；
- 更新 README、开发交接、版本和安装 wheel 冒烟。

不把写作逻辑继续塞入已较大的 `cycle.py` 或 `cli.py`。

## 12. 测试策略

必须先失败后实现：

1. verified fact、inference、hypothesis、conflicted 和 invalid claim 的严格分流；
2. 八章节门禁在“只有证据”“已选 Idea”“有设计”“有结果”“完成解读”五个状态下正确变化；
3. 只有 eligible fact 进入 citation candidates；
4. 医疗安全风险缺失时 Limitations and Ethics 不得报告 ready；
5. 唯一下一步稳定且不拼接不可信 claim 文本；
6. Markdown/JSON 确定性、schema 和排序；
7. project/ledger/cycle/Idea identity 漂移失败关闭；
8. 命令只读，运行前后工作区字节一致；
9. 完整 wheel 安装后走通新课题到写作计划的用户旅程；
10. 全量测试、warnings-as-errors、compileall、pip check、doctor、kb doctor 和 diff check 通过。

## 13. 非目标

- 自动写完整论文；
- 自动生成 BibTeX、DOI、作者、年份或期刊信息；
- 自动判断投稿 venue；
- 自动执行实验、统计检验或图表生成；
- 自动批准 Idea、结论或临床有效性；
- 把方法知识库条目静默转为课题证据；
- 联网补文献或下载全文。

## 14. 验收标准

在一个医疗诊断推理课题中，输入包含 verified fact、inference、hypothesis、conflicted claim、人工 selected Idea、完成的实验设计和保守结果解读时，命令必须：

- 只把 verified fact 放入事实性写作候选；
- 为每个候选保留 source_id、locator、反对证据与 limitations；
- 不隐藏 inference、hypothesis、conflict 或 invalid claim；
- 正确报告八章节 ready/partial/blocked；
- 只输出一个可复制的安全下一步；
- 明确“不是临床决策支持、不执行实验、不自动定稿”；
- 只读、确定性、安装 wheel 后可用；
- 独立代码审查没有未解决的 Critical 或 Important。
