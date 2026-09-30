# 条件证据记忆：方法契约 v0.1

<!-- research-os:generated:start -->
> 全文为 `hypothesis / proposed design`，未实现、未验证。简称 CPM 只是工作名称。

## 1. 从树到可审核条件

保留用户已有树作为候选规则骨架，先为节点增加稳定 criterion_id、知识版本、模块、阈值/时间约束、前置与排除条件和有向依赖。扫描/OCR 得到的节点必须逐条检查否定、比较符、跳转和时间范围；错误结构不能由模型流畅补齐。
树不是全部记忆。跨分支共用的条件用 ID 关联，避免重复或相互覆盖；无法无环表示的结构保留显式依赖，不强行变成单一路径。

## 2. 证据与知识分开

知识 K 是固定的条件规则；病例历史 H_t 是截至当前轮的输入；审计存储 A_t 是只追加的历史记录；工作记忆 M_t 是模型当前可见内容。
每条证据记录建议含：

```text
criterion_id, assertion_id, observed_turn, event_time_scope,
polarity: supports | refutes,
source_span: [turn_id, start, end], extractor_version,
supersedes_assertion_id: null | earlier_id,
confidence, revision_reason
```

条件状态为 supported/refuted/unknown/conflicted。这里是条件证据状态，不等同于疾病确诊。unknown 不等于 absent；相反表述只有在条件和事件时间兼容时才构成冲突。新增支持和反对证据都追加；经审核的明确更正用 supersedes 链失活旧 assertion，原记录仍可审计。
抽取器不得看到未来轮次、隐藏病例标签或测试金标准。invalid span 和无文本依据的状态更新被拒绝，并计入错误统计。

## 3. 确定性最小策略

记忆操作包括 retain、compress、retrieve、defer；问诊扩展再加入 ask、revisit、stop。语义压缩后仍必须保留条件 ID、方向、时间、有效修订和可定位原始证据；这是一项待测试契约，不是对模型正确性的保证。

优先级从高到低：尚未解决的关键冲突/更正 → 当前分支的关键排除/否定/时间条件 → 决策依赖的已观察条件 → 其他活动条件 → 一般叙述。类别内按稳定条件 ID/轮次排序，预算不足时采取 defer 或 abstain，不能丢弃限制后装作已满足。
最低必需表示装不进预算时，记为 infeasible/insufficient-context。需要原文时从 A_t 检索，并把返回 token 计入预算；其余方法也允许相同历史存储访问。

伪代码（仅设计）：

```text
for each incoming turn u_t:
    candidates = frozen_extractor(u_t, visible_knowledge)
    validate spans, timestamps, allowed criterion IDs
    append valid assertions and explicit revision links to A_t
    recompute affected criterion states from active assertions
    invalidate decisions that depend on revised conditions
    construct M_t with deterministic priority under total input budget B
    if essential evidence cannot fit: defer/abstain and log failure
    predict labels using the frozen reasoner and M_t
```

删除工作记忆内容不删除审计记录；回访被更正的依赖节点，不能仅从旧路径继续走。诊断器的输出仍需评估，规则过滤不是临床可靠性的证明。

## 4. 学习扩展与可证伪边界

可选的部分可观察管理策略 π(a|M_t, current input, active conditions, budget) 只训练管理动作，冻结抽取器和诊断器。与确定性策略使用同一访问权限和可行性过滤器，不让策略凭隐藏最终标签决策。
候选优化目标：最大化任务质量，满足开发阶段锁定的关键证据损失与成本约束。

\[
\max_\pi \mathbb{E}[Q],\quad
\mathbb{E}[C]\leq C_{\max},\quad
\mathbb{E}[L_{\mathrm{critical}}]\leq\delta.
\]

Q 可采用逐病例标签 F1，C 为全系统累计计算/token 成本，L 为关键已观察证据损失。δ 和权重须在开发阶段确定；约束不保证逐例正确或医疗安全。
若采用 GRPO/PPO，奖励候选为终端 Q 减成本、无依据状态、关键遗漏的惩罚；仅使用训练/开发标注。用保持条件语义的环境检查器过滤非法动作，并记录被拒次数。算法与训练超参数属于外部实验库，当前没有实现。
H02 失败时不继续宣称 RL 有价值；可以保留训练免除的研究问题与分析。

## 5. 工程与科学风险

证据抽取可能已经丢失条件；证据 ID 正确不代表内容准确；规则可能来自错误 OCR；更新策略可能奖励保守拒答；金标准可能由同一模拟器制造；额外抽取调用可能解释全部收益。这些分别通过共享抽取器、金证据参考、知识审核、覆盖率、独立标注和完整计费控制。
<!-- research-os:generated:end -->
