# criterion-memory：文献矩阵与反向证据

<!-- research-os:generated:start -->
> 事实仅见 `02-evidence-ledger.yaml` 的 F01–F10；矩阵是索引，不扩展未读内容。

| 材料与来源 | claim | 定位/阅读范围 | 与设计的关系（`inference`） |
|---|---|---|---|
| [SCID-5 FAQ](https://www.columbiapsychiatry.org/research/research-labs/diagnostic-and-assessment-lab/structured-clinical-interview-dsm-disorders-12), src-7199934b02d27442 | F01 | 官方定义与版本说明 | 知识版本要先确认 |
| [PsyCoTalk](https://arxiv.org/html/2510.25232v2), src-19423ffa02550e36 | F02/F03 | §4.1/§4.2，局部正文 | 最接近的 SCID 访谈框架；必须比较 |
| [ProAI](https://arxiv.org/html/2502.20689v1), src-d2e6f1d33876e3e2 | F04 | §3.2.2，局部正文 | 树与 back 动作已有，回退本身不是充分贡献 |
| [Context-Folding](https://arxiv.org/abs/2510.11967v1), src-c3d3cd48bfcbb549 | F05 | 摘要 | RL+上下文不构成独立新颖性证明 |
| [Memory-R1](https://arxiv.org/abs/2508.19828v5), src-3e94ac1d06aae1ba | F06 | 摘要 | 学习策略需超越通用记忆管理 |
| [MentalBench](https://arxiv.org/abs/2602.12871v2), src-b6fbe2aa2943f0f7 | F07 | 摘要与作者 README | 作为候选外部静态评测，不能直接冒充交互数据 |
| [MHM](https://arxiv.org/abs/2607.01523v1), src-470574fbc9fa78bf | F08 | 摘要 | 必须纳入强训练免除记忆对照 |
| [Human-Centered Annotation](https://arxiv.org/html/2607.15202v1), src-2f83aace052c9b5f | F09 | §III，局部正文 | 条件证据与专家修订也有先行工作 |
| [STITCH](https://aclanthology.org/2026.findings-acl.584/), src-6c0bd0be26ab9066 | F10 | 官方摘要 | 检索不能只有弱关键词基线 |

## 支持动机与最强反对意见

`inference I01`：已有工作使树、回退、证据槽和 RL 都不能单独作为主要创新。候选问题需要研究预算下的信息保持和修订机制，并给出充分对照。
`hypothesis H01/H02`：差异是否有用尚无证据。本库没有诊断实验结果，不采用其他论文的数字作为我们的预期提升。

| 议题 | 相关证据 | 冲突/限制 | 当前判断 |
|---|---|---|---|
| 未记录是否等于否定 | F03 的模拟规则与本方案的 unknown 状态 | 模拟设定与不完整记录任务的语义不同；并非同一实验的冲突结果 | 将 unknown→absent 作为待测错误类别，不指称原文临床结论错误 |
| 回退有没有新颖性 | F04 | 仅增加 back 动作与已有结构重合 | 需要比较修订后的依赖失效、证据恢复及成本 |
| RL 是否必要 | F05/F06 与 F08 | 有学习和训练免除两条路线；不同任务结果不可直接比较 | H02 必须独立通过，否则保留简单策略 |
| 条件证据是否新 | F09 | 已有条件级标注/专家反馈 | 主张预算控制与多轮修订需进一步检索与实验证明 |
| 数据是否足够长、足够独立 | F07 与作者公开说明 | 许可、组键和原始长度分布未核实；合成病例不能代表临床分布 | 先做数据审计与最小回放，不预设结论 |

## 候选空白与缺口

候选空白是“同一预算、同一输入下，可修订条件证据是否改善诊断与记忆保持”，并非已经证实无人研究。
还缺：基线全文核对、数据许可、树版本与质量审核、标注协议、外部模型/来源复验。
没有写入 synthesis-complete 标记；本轮是定向初筛。
<!-- research-os:generated:end -->
