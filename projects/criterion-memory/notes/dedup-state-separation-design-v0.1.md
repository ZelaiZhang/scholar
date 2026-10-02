# 去重与节点判断分离：可接入现有 JSON 的设计 v0.1

<!-- research-os:generated:start -->
> 2026-10-02。全文为 hypothesis / proposed implementation design。用于独立实验仓库中的脱敏或模拟任务，未接入用户树代码、未调用模型、未验证效果；不代表选题批准或临床能力。

定位：这是排查去重干扰的工程参考，不作为论文主要贡献或新颖性声明。研究候选复审见 [04-idea-candidates-v0.2.md](../04-idea-candidates-v0.2.md)。

## 1. 建议先做的最小改动

保留已有 JSON 和逐轮记录，分别维护“问题是否问过”和“证据支持什么”。节点判断使用证据，提问策略使用问题记录。去重不能删除判断所需的回答，不能把已问过直接转换成节点满足、否定或完成。

hypothesis：去重指令、过程状态与节点证据混在同一输入时，可能发生干扰；这不是已确认的用户故障原因。以下分离设计旨在先隔离这一因素。

两个逻辑阶段可使用同一个冻结模型，但构建不同输入：

1. NodeJudge：读取固定节点定义及有原文定位的已观察证据，输出条件证据状态和缺失项。
2. QuestionPlanner：读取经校验的状态、缺失项和已问记录，决定不提问、提出新问题、澄清或延后。

树的跳转由经过审核的规则执行；QuestionPlanner 不得修改节点判定。若需要两个模型调用，额外调用必须计入成本。

可复制的提示词：

- [节点判断提示词](../artifacts/node-judge-prompt-v0.1.txt)
- [提问选择提示词](../artifacts/question-planner-prompt-v0.1.txt)

## 2. 建议的数据结构

以下仅为字段示意，无真实病例内容，也不复述扫描书籍中的规则：

~~~json
{
  "dialogue_log": [
    {"turn_id": 1, "role": "assistant", "content": "<模拟问题>"},
    {"turn_id": 2, "role": "user", "content": "<模拟回答>"}
  ],
  "question_ledger": [
    {
      "question_id": "Q_DEMO_1",
      "intent_id": "INTENT_DEMO",
      "criterion_ids": ["C_DEMO"],
      "facet_id": "FACET_DEMO",
      "event_time_scope": "EPISODE_DEMO",
      "asked_turn": 1,
      "answer_turns": [2],
      "status": "answered"
    }
  ],
  "evidence_store": [
    {
      "evidence_id": "E_DEMO_1",
      "criterion_id": "C_DEMO",
      "turn_id": 2,
      "source_text": "<模拟回答>",
      "event_time_scope": "EPISODE_DEMO",
      "supersedes_evidence_id": null
    }
  ],
  "node_states": {
    "C_DEMO": {
      "status": "unknown",
      "evidence_ids": ["E_DEMO_1"],
      "missing_facets": ["FACET_DEMO"],
      "updated_turn": 2
    }
  }
}
~~~

answered 只表示收到回答，不表示回答充分，也不表示条件满足。支持、反驳、未知和冲突描述条件证据，不等同于疾病确诊。缺失信息不能自动变成否定信息。

question_ledger 的状态可包括 asked_unanswered、answered、clarification_needed、declined；语义和转换规则由实现固定。问题实际送达后才记录 asked；失败的提问调用不能冒充已完成。

原始对话只追加。抽取记录和模型生成的节点状态保留版本，不能覆盖原文，也不能将模型旧判断充当原始证据。抽取遗漏会影响后续阶段，必须单独评估。

## 3. 明确输入边界

NodeJudge 输入白名单：

~~~text
current_turn
criterion: {criterion_id, knowledge_version, definition, allowed_facets}
evidence: [{evidence_id, turn_id, source_text, event_time_scope,
            supersedes_evidence_id}]
evidence_scope: {selection_rule_version, coverage_known}
~~~

第一版不输入 question_ledger、dedup_enabled、禁止重复提问的指令或旧节点判断。JSON 中分成两个字段但仍把所有字段交给同一判断调用，不能验证这种输入隔离。

证据选择按固定规则覆盖节点相关的支持、反驳、时间、排除和更正信息。不能只保留最近回答或阳性信息。若选择/预算造成覆盖不足，应输出 unknown 或请求复核，不能声称条件一定满足。选择器可以使用冻结抽取器，但不得依赖去重开关。

QuestionPlanner 输入白名单：

~~~text
validated_node_judgment
question_ledger
allowed_question_bank
current_event_time_scope
clarification_attempts
max_clarifications
~~~

规划器可以读取判断引用的证据；不得删除或改写该证据，不得修改状态以迁就去重要求。

## 4. 执行流程与去重规则

伪代码，仅供独立实验仓库实现：

~~~text
append received turn to dialogue_log
update source-linked evidence using a fixed extractor
judge_input = build_judge_input_from_whitelist()
judge_output = NodeJudge(judge_input)
validate output schema, criterion ID, allowed facets and source references
if validation fails:
    log failure and defer; do not default to a positive/negative branch
else:
    commit a versioned node state
    if the state is supported/refuted and the tree's audited rule permits:
        route using that rule; question planning cannot change the state
    else:
        proposal = QuestionPlanner(state, question_ledger, allowed_questions)
        validate proposal and enforce clarification limit
        deliver an allowed question or defer
~~~

已问过且已有充分证据时，复用证据并更新判定，不再次提问。已问过但回答不完整时，针对具体缺失项澄清；明确拒答或达到预定澄清次数后延后，不能凭空补全。同一事件的冲突优先检查现有记录，仍无法解决时提出有理由的澄清。另一时间段的信息不自动撤销旧观察。

建议去重键使用经过审核的 intent_id、facet_id 和 event_time_scope，并保留 criterion_ids 对应关系。不能仅因句子相似就删掉问题；不同时间范围或不同缺失项可能需要分别确认。第一版优先使用带稳定 ID 的问题库；开放生成问题的语义匹配需另行验证并计入成本。

## 5. 建议先检查的程序不变量

这些是结构检查建议，不是已经执行的实验：

- 固定同一对话前缀及知识，开启/关闭去重时，NodeJudge 的完整序列化输入及其哈希应相同。
- 更新 question_ledger 不直接改变 node_states；状态只能由经校验的判断结果写入。
- 任何去重操作均不删除原始回答；所有返回 evidence_id 都能定位到已出现的原文。
- “已问但没有回答”仍是证据不足，不自动转为 supported 或 refuted。
- 去重键相同但缺失项未解决时，允许受次数约束的澄清；不把必要澄清一律计为坏重复。
- schema、引用校验或预算失败不默认推进树分支；记录并延后。

输入不变量只验证固定前缀下的直接隔离，不能保证所有模型输出正确；交互中不同提问还会改变后续可见信息。结构化输出和真实引用存在，也不保证证据语义推断成立。

## 6. 逐步验证效果

先复现 [v0.3 四条件设计](dedup-node-judgment-clarification-v0.3.md)，再加入“同样 JSON + 输入分离”的方案。共享节点定义、证据抽取器、对话和冻结诊断模型。

分别消融：只改判断提示但不改输入、真正排除去重字段、增加证据引用校验、按缺失项澄清。主比较至少包括用户现有 JSON 方法；不得把更好的抽取器或额外调用的作用全归于分离机制。

固定回放比较节点判断、未知/冲突处理及输入不变量；交互任务比较不必要重复、必要澄清、访谈轮数和最终标签质量。全部计入两阶段调用成本。保留配对病例组、失败、拒答和合法延后；主要指标、预算、样本数及统计规则在测试前确认。

如果只降低重复而节点判断变差，不能认为方案成功。如果只在固定回放有效，不能宣称交互访谈也有效。没有稳定优于已有 JSON 基线的结果，不主张新增机制带来改善。

## 7. 阅读范围与待审核项

本轮只阅读下列官方摘要，借鉴状态与下游策略、历史预测误差的研究问题，不将论文方法声称为已忠实复现，也不外推其任务成绩：

- source_id: public-dst-incremental-2021-abstract；locator: 官方 Abstract 第 1—2 段。[Dialogue State Tracking with Incremental Reasoning](https://aclanthology.org/2021.tacl-1.34/)
- source_id: public-correctable-dst-2022-abstract；locator: 官方 Abstract 第 1—3 段。[Correctable-DST](https://aclanthology.org/2022.emnlp-main.56/)

待审核：用户树代码、JSON schema、去重实现、树跳转规则、证据抽取与覆盖、问题库和澄清限额。没有真实实验结果，未改写论文事实账本或 Results，未批准最终研究主线。
<!-- research-os:generated:end -->
