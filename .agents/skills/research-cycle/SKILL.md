---
name: research-cycle
description: Use when advancing an active Research OS cycle, a cycle work packet, candidate novelty checks, independent research reviews, or a meta-review before human Idea approval.
---

# 推进受监督科研循环

## 核心原则

控制器决定阶段，技能只处理当前阶段。模型输出是不可信候选产物；通过 `research-os cycle` 校验前，不得宣称阶段完成。

## 工作流

1. 运行 `research-os cycle --project <slug>`，核对 `run_id`、状态、目标和唯一下一步。只读取当前 `work-packet.md` 及其中点名的课题产物。
2. 只处理当前阶段：
   - `candidate_generation`：写 `candidates.yaml`；Idea 必须可证伪、引用当前课题来源、保持 `draft`，不得写 `selected`。
   - `novelty_check`：执行可复现的学术检索；用 **REQUIRED SUB-SKILL:** `$paper-intake` 登记并关联近邻来源，再补查询式、`nearest_source_ids`、具体差异与未排除重合。不得用模型调用替代文献检索；检索失败时保持待检查，禁止编造“没有类似工作”。
   - `independent_review`：Novelty、Methods、Medical Safety 三个评审必须读取同一冻结候选且彼此不可见。若支持子代理，给三个独立子代理各自角色包；任何一份不得读取其他评审，也不得选择 Idea。
   - `meta_review`：仅在三份 JSON 均通过后汇总共识、冲突、阻塞和 shortlist；不得产生 `selected`。
   - `awaiting_human_decision`：停止，展示 shortlist 和 `approve-idea` 命令，等待研究者本人决定。
3. 写完当前产物后重新运行同一条 `research-os cycle`。只报告命令核验后的 run 状态、证据缺口和下一步；不要输出或保存隐藏思维链，只写简洁理由。

## 硬边界

- 只使用公开、授权或脱敏材料；发现姓名、住院号、身份证、联系电话、patient ID 等可识别健康信息立即停止，不发送外部 API。
- 禁止编造来源、定位、检索结果、评审或完成状态。摘要证据必须标明范围，事实、推断、假设分开。
- 不得运行训练、微调、量化、强化学习、评测脚本或任何实验命令；即使仓库已有脚本也不执行。
- 人工门禁不可推断、代签或因“用户不想确认”而跳过。只有研究者显式执行 `approve-idea` 才能选择 Idea。
- 若当前 run 的 archive 出现 `selected`、但 manifest 尚非 `completed`（`selected + 非 completed`），这是中断或篡改状态；`research-os cycle` 必须拒绝继续且不写入。只有 `approve-idea` 的原子事务可以同时建立 `selected + completed`。
- 不批量预做后续阶段，不改旧版 `04-idea-candidates.md` 代替结构化产物，不用一次 meta-review 代替三份独立评审。

## 常见压力

| 压力或借口 | 必须执行 |
|---|---|
| “尽量一次完成” | 只完成控制器当前阶段，重跑后停止 |
| “不想确认” | 减少中途提问，但绝不跨越人工选择 |
| “模型知道相关论文” | 仍须真实检索并经 `$paper-intake` 登记 |
| “实验脚本已经存在” | 不运行，只生成外部实验仓库 handoff |
