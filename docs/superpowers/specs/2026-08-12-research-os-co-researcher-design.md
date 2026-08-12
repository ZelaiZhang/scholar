# Research OS v0.3 人类监督的 AI Co-Researcher 设计

日期：2026-08-12  
状态：设计已获用户方向批准，等待书面规格复核

## 1. 设计依据

Nature 论文 *Towards end-to-end automation of AI research*（`source_id: src-92920c311599e7a4`）展示了由 Idea 生成、文献新颖性筛查、实验、写作和自动审稿构成的端到端 AI Scientist。对 Research OS 最有价值的机制是：持续生长的结构化 Idea 档案、迭代文献查询、研究日志、受预算约束的循环、独立评审集成和 meta-review。

本设计不照搬全自动科研。论文只在三篇投稿中得到一篇达到高接收率 workshop 的门槛，并报告了朴素 Idea、方法不严谨、实现错误和不准确引用等失败。Research OS 的目标仍是帮助研究者做出更好的判断，不是替研究者做最终判断。

## 2. 目标与非目标

### 2.1 目标

把当前“确定性 `guide` + 十个独立技能”的线性驾驶舱升级为可暂停、可恢复、可审计的研究循环：

1. 围绕一个已经定义的课题生成和维护多个候选 Idea，而不是过早收敛到单个方案。
2. 要求每个候选 Idea 经历可复核的新颖性反证、证据检查和多视角反审。
3. 让 Codex 默认可完成本地工作包；用户也可显式启用 DeepSeek 或其他 OpenAI-compatible API。
4. 用调用次数、候选数、循环轮数和停止原因约束自动化，避免无限代理循环。
5. 把每次输入快照、模型输出、评分、淘汰原因、人工决定和 provenance 写入追加式研究日志。
6. 保持现有证据、医疗安全、人工门禁和不执行实验的边界。

### 2.2 非目标

- 不训练、微调、量化、强化学习或执行 GPU/集群任务。
- 不修改或运行独立实验仓库。
- 不自动决定 Idea 成立、实验设计通过、论文结论成立或允许投稿。
- 不处理真实病例、可识别健康信息或个人诊疗请求。
- 不把 LLM 自评分、文献语义相似度或自动审稿分数当成科学真实性证明。
- v0.3 不实现开放式无限探索；只实现有研究简报约束的 focused mode。
- 不保存模型隐藏思维链，只保存简洁理由、证据引用、反对意见和决策摘要。

## 3. 方案比较

### 方案 A：复制完整 AI Scientist

自动生成 Idea、执行实验、写论文并自审。自动化程度最高，但直接违反本仓库不执行实验和保留人工判断的边界；论文报告的实现错误、引用幻觉和方法薄弱也会被放大。因此不采用。

### 方案 B：只增强现有技能文本

给 `idea-review`、`mock-reviewer` 增加更多检查项。实现成本低且风险小，但没有可恢复状态、候选档案、预算、独立评审产物或可审计循环，无法真正减少研究管理负担。因此只作为兼容层，不作为主方案。

### 方案 C：有界 Co-Researcher 循环（采用）

增加确定性循环控制器、结构化 Idea 档案、检索任务、三审一汇总、哈希链日志和显式人工批准。默认由 Codex 技能执行，外部 provider 是可选加速层。它吸收论文中有效的代理组织方式，同时把失败风险收敛在可查看、可停止、可恢复的本地产物内。

## 4. 用户体验

### 4.1 默认 Codex 模式

```powershell
research-os cycle --project medical-reasoning
```

首次运行创建一个不可变 `run_id`、本地上下文快照和工作包，不调用外部 API。输出只包含当前循环目标、预算、缺失证据、唯一下一步，以及可交给 Codex 的指令：

```text
$research-cycle 执行 medical-reasoning 的 run-20260812-...，只处理工作包指定阶段
```

再次运行相同命令时，控制器恢复未完成 run，不重复生成候选或重复消费模型调用。`--new-run` 必须显式指定，且旧 run 保留。

### 4.2 可选外部 provider 模式

```powershell
research-os cycle `
  --project medical-reasoning `
  --provider-role economy `
  --max-calls 6 `
  --max-ideas 4 `
  --allow-external-api
```

provider 从不提交版本库的 `config/providers.yaml` 读取。调用前命令必须：

1. 显示并写入本轮最大调用数、模型角色和上下文来源；
2. 验证所有进入上下文的 claim 均来自当前课题显式关联且通过核验的 `source_id`；
3. 要求这些底层来源均已显式授权外发；
4. 生成精确上下文快照，登记其哈希和外发许可，再发送同一字节快照；
5. 要求同时出现命令级 `--allow-external-api`，缺一项即 fail closed；
6. 把每次请求的模型、参数、时间、提示词哈希、输入 source_id、用量和响应哈希写入 run provenance，不记录 API Key。

provider 只处理构思、结构化反审和 meta-review，不执行联网文献搜索。没有检索记录时，Idea 只能进入 `needs_novelty_check`，不能被判定为新颖。

### 4.3 人工批准

```powershell
research-os approve-idea `
  --project medical-reasoning `
  --idea idea-0003 `
  --reason "证据充分，资源范围可控，保留明确失败判据"
```

这是 Idea 从 `shortlisted` 进入 `selected` 的唯一合法路径。命令记录时间、Idea 内容哈希、理由和 `actor: researcher`。模型和技能没有调用该状态转换的权限。选择后 `guide` 才会推荐 `$experiment-advisor`；Research OS 仍只生成设计与独立实验仓库 handoff。

## 5. 文件与数据模型

每个新旧课题按需创建，不强制迁移已有人工文件：

```text
projects/<slug>/
  ideas/
    archive.yaml
  cycles/
    run-<UTC timestamp>-<short hash>/
      manifest.yaml
      context.md
      work-packet.md
      candidates.yaml
      novelty-queue.yaml
      reviews/
        novelty.json
        methods.json
        medical-safety.json
        meta-review.json
      provenance/
        call-001.json
  research-journal.jsonl
```

### 5.1 IdeaRecord

`ideas/archive.yaml` 使用 schema version 1。每条 Idea 至少包含：

- `idea_id`、`parent_ids`、标题、科学问题、可证伪假设和候选贡献；
- 当前课题内的 `evidence_source_ids`；
- 新颖性状态、检索式、最接近工作、差异与仍未排除的重合；
- `interestingness`、`novelty`、`feasibility`、`evidence_support` 四个 1–10 建议分；
- 方法风险、医疗安全风险、失败判据和所需外部实验；
- `draft / needs_evidence / needs_novelty_check / reviewed / shortlisted / rejected / selected` 状态；
- 生成 run、模型 provenance、内容哈希与人工决定。

建议分只用于排序。任何高分都不能跳过证据、新颖性和人工批准门禁。

### 5.2 Research Journal

`research-journal.jsonl` 是机器管理的追加式事件流。每行包括 `sequence`、`event_type`、`run_id`、UTC 时间、`actor`、产物相对路径、产物哈希、前一事件哈希和当前事件哈希。事件只记录输入输出摘要和决策依据，不记录隐藏思维链。

`doctor` 验证序号、哈希链、run 引用和产物路径；损坏时阻止 cycle 继续，但不自动修复或截断日志。

### 5.3 Run Manifest

`manifest.yaml` 记录：课题 slug、focused mode、状态、候选数上限、调用上限、实际调用数、provider role、输入 source_id、当前阶段、停止原因、创建和更新时间。状态变化使用原子写入和现有目录身份保护。

## 6. 循环状态机

固定状态顺序如下：

```text
prepared
  -> candidate_generation
  -> novelty_check
  -> independent_review
  -> meta_review
  -> awaiting_human_decision
  -> completed
```

任意阶段还可进入 `blocked` 或 `budget_exhausted`。恢复时从最后一个已经校验、已写日志的状态继续。

### 6.1 Candidate generation

每轮最多生成 `max_ideas` 个候选。候选必须可证伪、不能只是替换模型/数据/提示词，并必须说明与当前证据的关系。缺失字段或引用课题外 source_id 时整批候选拒绝，不部分导入。

### 6.2 Novelty check

控制器生成最多十轮的检索队列，但不把搜索结果数量等同于新颖性。`$research-cycle` 使用可用的学术搜索和 `$paper-intake` 登记候选近邻工作。每个 `reviewed` Idea 至少需要：

- 一条可复现检索式和日期；
- 至少一个已登记近邻来源，或明确记录检索失败；
- “已有工作做了什么 / 本 Idea 真正不同在哪里 / 哪些重合尚未排除”；
- 新颖性审稿人的反对意见。

没有全文时必须标记摘要范围。检索失败只能保持 `needs_novelty_check`，不能生成“未发现类似工作”的肯定结论。

### 6.3 三审一汇总

三个评审读取相同冻结快照并独立输出结构化 JSON：

- Novelty Reviewer：伪创新、遗漏近邻工作、贡献边界；
- Methods Reviewer：可证伪性、基线、数据划分、消融、统计和资源可行性；
- Medical Safety Reviewer：技术性能与临床效用混淆、数据泄漏、亚组、公平性、部署和隐私风险。

Meta-review 只汇总共识、冲突、阻塞问题和 shortlist 建议，不产生最终 `selected` 状态。provider 调用失败、JSON schema 无效或评审缺失时保持 `blocked`，不使用剩余评审猜测共识。

## 7. 组件边界

- `cycle.py`：状态机、预算、恢复与 work packet；不实现 provider、来源登记或具体审稿逻辑。
- `ideas.py`：Idea schema、合法状态转换、排序和人工批准。
- `journal.py`：追加、哈希链和只读验证。
- `review.py`：评审角色 schema、独立输出校验和 meta-review 输入组装。
- `provider_config.py`：严格解析 provider role，复用 `OpenAICompatibleProvider`；禁止 Key 写盘。
- `cycle_context.py`：从当前课题快照构建最小上下文，执行课题来源隔离和外发许可预检。
- `guidance.py`：只读取 cycle 状态并继续只推荐一个动作。
- `.agents/skills/research-cycle/`：在 Codex 中执行候选、检索和评审工作包；调用现有 paper-intake、idea-review、experiment-advisor 和 mock-reviewer，而不复制其职责。

## 8. 错误、安全与恢复

- 任何结构化输出必须先完整校验，再原子提交；不导入半批 Idea 或半套评审。
- 预算在请求发出前递增并写日志，网络失败也计入调用，防止不受控重试。
- 每个 run 的上下文和产物默认不可覆盖；恢复只写缺失的下一阶段文件。
- 所有相对路径必须解析在当前课题和 run 目录内，并复用现有 symlink、junction 和目录身份保护。
- provider 响应被视为不可信输入：限制大小、要求 UTF-8、解析固定 JSON schema、拒绝额外状态转换指令。
- 检测到疑似可识别医疗信息时停止构建上下文；该检测是附加防线，不能替代研究者确认。
- 不自动运行生成的 shell、Python、训练或实验命令。
- 不自动访问投稿系统、发送邮件、创建账号或发布 AI 生成稿件。

## 9. `guide` 与兼容性

没有 cycle 的课题保持 v0.2 行为。Idea 阶段开始后，`guide` 优先显示当前 run、预算、候选状态、阻塞和唯一动作：

- 无 run：推荐 `research-os cycle --project <slug>`；
- 等待检索：推荐 `$research-cycle` 完成 novelty queue；
- 等待评审：推荐执行缺失评审；
- 等待人类：显示 shortlist 和 `approve-idea` 示例；
- 已选择：恢复现有 `$experiment-advisor` 路径。

旧 `04-idea-candidates.md` 保留为人类可读视图，由技能从结构化 archive 的已校验生成区块更新；不覆盖研究者笔记。旧课题不要求立即创建 archive 或 journal。

## 10. 测试策略

严格使用 TDD：

1. Idea schema、状态机和课题来源隔离；
2. journal 追加、哈希链、损坏检测和并发/中断保护；
3. cycle 新建、恢复、预算耗尽和幂等性；
4. 三个独立评审及缺失/无效 JSON 的 fail-closed 行为；
5. provider role 解析、精确快照授权、调用计数和无 Key provenance；
6. `approve-idea` 是唯一 `selected` 转换；
7. `guide` 与 legacy project 兼容；
8. Windows junction、同名目录替换和事务回滚回归；
9. wheel 安装后模板、技能、cycle、doctor 和 guide 冒烟；
10. 端到端测试只使用 fake transport，不产生真实 API 费用。

## 11. 验收标准

- 一条 `cycle` 命令能创建或恢复本地研究循环，并只给一个下一步。
- 默认运行不联网、不调用模型、不外发内容。
- 外部 provider 必须同时通过调用级、来源级和精确快照许可。
- 同一 run 重复执行不会重复生成候选或重复计费。
- 每个候选均有可追踪证据、新颖性状态、独立评审和淘汰/保留理由。
- 模型不能把任何 Idea 改成 `selected`；只有显式 `approve-idea` 可以。
- 研究日志能验证完整哈希链，损坏时 doctor 明确失败。
- 实验设计之后仍等待独立实验仓库，不执行实验。
- 所有 v0.2 命令和旧课题继续工作。
- 全量测试、技能校验、diff 检查和安装后 wheel 冒烟全部通过。
