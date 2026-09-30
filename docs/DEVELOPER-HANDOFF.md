# Research OS 开发交接与功能说明

> 最后核对：2026-09-30；包版本：`0.7.1`；功能基线以本文档所在提交为准。
>
> 本文把“已经实现”和“规划中”分开记录。除非明确标注为规划，否则下文功能均可在当前仓库中找到代码与测试。

## 1. 项目定位

Research OS 是一个面向大模型方向研究生的本地、证据优先科研工作区。它把模糊研究方向逐步整理成可复核的文献证据、候选 Idea、实验设计、结果解释、论文草稿和模拟审稿材料。

当前系统的核心边界：

- 提供科研指导、资料整理和流程减负；
- 不在本仓库执行训练、微调、量化、强化学习或集群实验；
- 不把模型输出当成事实，事实必须回到已登记来源和原文定位；
- 不允许模型自行批准最终 Idea，关键决策保留给研究者；
- 不处理真实可识别病例、原始病历或个体诊疗请求；
- 外部大模型是可选能力，默认完全本地运行。

适用方向包括医疗 AI 诊断与推理、医学大模型、思维链可靠性、文本处理，以及微调、量化和 RL 相关的方法调研与实验规划。

## 2. 当前完成度

当前维护版本是 `v0.7.1`，已经完成：

1. 科研课题工作区和标准模板；
2. 文献来源登记、去重、课题关联和批量原子导入；
3. PDF 文本提取与页码边界保留；
4. 证据账本及严格来源校验；
5. 每日科研导航 `guide`；
6. 11 个 Codex 科研技能；
7. 有预算、可恢复、可审计的 AI Co-Researcher Idea 循环；
8. Novelty、Methods、Medical Safety 三路独立评审和 meta-review；
9. 研究者人工批准门禁；
10. OpenAI-compatible API 接入，包括自定义 DeepSeek 配置；
11. 调用授权、来源授权、敏感医疗字段拦截和 provenance；
12. 哈希链研究日志、产物哈希、并发保护和失败回滚；
13. 源码安装、wheel 安装和关键用户旅程测试；
14. 结构化科研方法知识库、确定性搜索和课题推荐；
15. 28 条专业种子来源、17 张知识卡、5 张主题地图和 4 份方法手册；
16. 医疗 AI 报告规范路由和知识库完整性检查；
17. NFKC/CJK 词片和人工双语别名驱动的中文知识检索；
18. 只读、可固定日期的知识维护缺口队列。
19. 确定性、只读的课题研究驾驶舱，聚合课题、证据、Idea、方法、风险和最多三个今日行动。
20. 证据绑定的组会研究决策简报，逐条保留结论定位、冲突、限制、Idea 失败边界和人工理由。

2026-09-30 的本地 macOS/Python 3.12.14 回归为 `400 passed`（warnings-as-errors）；v0.7.1 wheel 从源码目录外的独立环境完成用户旅程。跨平台 CI 已配置，Linux/Windows 的远端运行结果另行核对。后续代码提交仍必须重跑本文第 13 节的命令和 wheel 冒烟，不能沿用本次结果。

v0.7.1 重点修复证据字段类型、重复 YAML 键、读取中原位修改、来源表重复身份、单次 provider 参数与医疗输入检查、生成输出并发覆盖，以及论文规划中的失效路径。详情见 [维护复核](2026-09-30-maintenance-review.md)，Mac 操作见 [MACOS.md](MACOS.md)。

## 3. 系统总览

```mermaid
flowchart LR
    U["研究者"] --> D["doctor：只读自检"]
    D --> G["guide：唯一下一步"]
    D --> B["dashboard：全局状态与三个行动"]
    B --> M["meeting-brief：证据绑定的组会决策简报"]
    M --> P["manuscript-plan：八章节证据门禁"]
    G --> S["Codex 科研技能"]
    G --> C["Research OS CLI"]
    S --> P["课题文件与人工判断"]
    C --> R["来源登记表与证据账本"]
    C --> K["科研方法知识库"]
    C --> X["有界 Research Cycle"]
    R --> P
    K --> G
    K --> B
    R --> B
    X --> B
    X --> P
    P --> G
    X -. "显式双重授权后可选" .-> API["DeepSeek / OpenAI-compatible API"]
```

系统不是一个无限自主代理。正常使用方式是：先运行 `doctor`，再让 `guide` 检查真实产物并只给出一个下一步；Codex 技能或 CLI 完成该步骤后，再次运行 `guide`。

## 4. 仓库结构

```text
.
├─ .agents/skills/             # 11 个 Codex 科研技能
├─ config/
│  ├─ research.yaml            # 工作区基础配置
│  └─ providers.example.yaml   # 外部模型角色示例
├─ docs/
│  └─ superpowers/
│     ├─ specs/                # 已批准或待批准的设计规格
│     └─ plans/                # 对应实施计划
├─ inbox/                      # 用户待登记材料
├─ library/
│  ├─ sources.jsonl            # 全局来源登记表
│  ├─ sources/                 # 提取文本等来源副本
│  ├─ papers/                  # 结构化论文卡片
│  ├─ knowledge/               # 目录、知识卡、地图、手册与报告规范
│  └─ literature-matrix.csv    # 课题文献比较矩阵
├─ projects/<slug>/            # 各课题严格隔离的工作区
├─ src/research_os/            # Python 包和 CLI
└─ tests/                      # 单元、回归与 wheel 冒烟测试
```

`library` 是全局资料库，但一个课题只能使用自己 `project.yaml` 中显式关联的 `source_id`。全局存在某篇论文不代表所有课题都可以自动引用它。

## 5. 一个课题包含什么

`new-project` 创建的核心结构如下：

| 文件或目录 | 作用 |
|---|---|
| `START-HERE.md` | 新课题的最短使用入口 |
| `project.yaml` | 课题标题、slug、创建时间和显式关联的 `source_ids` |
| `00-research-brief.md` | 研究问题、范围、假设、约束和失败判据 |
| `01-search-log.md` | 数据库、检索式、日期、纳排标准和下一轮检索 |
| `02-evidence-ledger.yaml` | 可核验事实、推断、假设、支持、反证和限制 |
| `03-literature-review.md` | 共识、冲突、方法差异和研究空白 |
| `04-idea-candidates.md` | 人类可读的候选 Idea 与反向审查 |
| `05-experiment-design.md` | 基线、数据划分、消融、统计、预算和失败判据 |
| `06-result-analysis.md` | 外部实验结果的保守解释 |
| `ideas/archive.yaml` | 机器可校验的 Idea 状态、来源和人工选择 |
| `cycles/<run_id>/` | 每次有界科研循环的状态与产物 |
| `research-journal.jsonl` | 追加式、哈希链研究事件日志 |
| `artifacts/` | 外部实验仓库导出的脱敏聚合结果 |
| `writing/` | 稿件、大纲和图表说明 |
| `reviews/` | 模拟审稿和返修材料 |

文件存在不等于阶段完成。`guide` 会检查完成标记、结构、来源、哈希和先决条件；随手修改一个字符只会被视为“进行中”。

## 6. CLI 功能

安装后入口是 `research-os.exe`，也可使用 `python -m research_os`。

| 命令 | 作用 | 是否写文件 | 是否联网 |
|---|---|---:|---:|
| `doctor` | 检查 Python、目录、技能、来源、课题、循环和日志 | 否 | 否 |
| `guide` | 显示当前阶段、阻塞原因和唯一下一步 | 否 | 否 |
| `dashboard` | 汇总课题、证据、Idea、方法、风险和最多三个今日行动 | 否 | 否 |
| `meeting-brief` | 生成带定位、冲突、限制、Idea 边界和讨论问题的组会简报 | 否 | 否 |
| `manuscript-plan` | 生成八章节论文就绪度、严格证据分栏和唯一下一步 | 否 | 否 |
| `new-project` | 创建标准课题目录和模板 | 是 | 否 |
| `add-source` | 登记、去重并可选关联单条来源 | 是 | 否 |
| `add-sources` | 从 UTF-8 清单原子批量登记来源 | 是 | 否 |
| `extract-pdf` | 提取带 `<!-- page:N -->` 边界的 PDF 文本 | 是 | 否 |
| `validate-ledger` | 校验证据类型、状态、定位和来源范围 | 否 | 否 |
| `cycle` | 创建或恢复有界科研循环 | 是 | 默认否；显式授权后可调用 API |
| `approve-idea` | 由研究者批准当前 run 的入围 Idea | 是 | 否 |
| `model-call` | 发起一次受控 OpenAI-compatible API 调用 | 是 | 是，必须显式授权 |
| `kb doctor` | 检查目录、卡片、来源、定位、替代关系和资产引用 | 否 | 否 |
| `kb search` | 按固定权重执行本地可解释检索 | 否 | 否 |
| `kb gaps` | 确定性列出缺卡、核验、全文升级和过期复核任务 | 否 | 否 |
| `kb recommend` | 根据课题画像和 guide 阶段返回最多三项参考 | 否 | 否 |

日常入口：

```powershell
.\.venv\Scripts\research-os.exe doctor
.\.venv\Scripts\research-os.exe guide --project medical-reasoning
.\.venv\Scripts\research-os.exe dashboard --project medical-reasoning --as-of 2026-08-12
.\.venv\Scripts\research-os.exe meeting-brief --project medical-reasoning --as-of 2026-08-12
.\.venv\Scripts\research-os.exe manuscript-plan --project medical-reasoning --as-of 2026-08-13
```

`guide` 负责唯一下一步，`dashboard` 负责全局研究快照，`meeting-brief` 负责把已经通过证据和 Idea 门禁的内容整理成导师可讨论的研究决策简报，`manuscript-plan` 再把同一快照映射为八个论文章节门禁。四者复用同一阶段与门禁；JSON 是未来接入受控语言润色的稳定边界，但当前命令不联网、不写文件，也不允许模型改变事实、风险、讨论问题或行动优先级。

批量登记来源：

```powershell
.\.venv\Scripts\research-os.exe add-sources `
  ".\inbox\sources.txt" `
  --project medical-reasoning
```

清单一行失败时整批失败，来源登记表和课题关联均会回滚。不要把失败清单降级成逐行导入，否则会破坏全有或全无语义。

启动或恢复科研循环：

```powershell
.\.venv\Scripts\research-os.exe cycle `
  --project medical-reasoning `
  --max-ideas 4 `
  --max-calls 6
```

默认 `cycle` 不调用外部模型。只有同时提供 `--provider-role` 和 `--allow-external-api`，且所有进入上下文的来源均已授权、哈希未漂移，才允许外发。

知识库日常入口：

```powershell
.\.venv\Scripts\research-os.exe kb doctor
.\.venv\Scripts\research-os.exe kb search "诊断准确性" --topic medical-ai
.\.venv\Scripts\research-os.exe kb gaps --as-of 2026-08-12 --limit 20
.\.venv\Scripts\research-os.exe kb recommend --project medical-reasoning
```

全局知识条目只提供方法学线索。推荐命令不会改写 `project.yaml`；需要引用时仍必须用 `paper-intake` 显式关联到目标课题。

## 7. 11 个 Codex 科研技能

| 技能 | 使用阶段 | 核心输出 |
|---|---|---|
| `research-project-init` | 新方向或开题 | 可证伪研究简报 |
| `paper-intake` | 接收论文或清单 | 去重来源和课题关联 |
| `paper-deep-read` | PDF 精读 | 带 `source_id` 和原文定位的论文卡片 |
| `literature-synthesis` | 多论文综合 | 共识、冲突、差异、空白和下一轮检索 |
| `research-cycle` | 有界 Idea 循环 | 候选、新颖性记录、三审和 meta-review |
| `idea-review` | 单个 Idea 深审 | 新颖性、可行性和最强反对意见 |
| `experiment-advisor` | 实验规划 | 基线、消融、指标、统计和失败判据 |
| `result-interpreter` | 外部实验完成后 | 支持与不支持的结论、异常和负结果 |
| `manuscript-assistant` | 写作 | 基于证据账本的稿件和引用缺口 |
| `mock-reviewer` | 投稿前 | 方法、统计、复现和医疗安全审查 |
| `research-weekly-review` | 每周复盘 | 证据变化、阻塞与下周三个行动 |

技能位于 `.agents/skills/<skill>/SKILL.md`。修改技能时必须保持“事实—模型推断—研究者判断”分离，并同步更新 `tests/test_skills.py`。

## 8. 证据模型

### 8.1 来源登记表

`library/sources.jsonl` 的每条记录包含：

- 稳定的 `source_id`；
- 来源类型与规范化标识；
- 本地文件内容哈希；
- 导入时间和人工笔记；
- 是否允许发送到外部 API。

本地文件移动后重新登记同一内容会复用 ID 并刷新当前路径。内容变化会被视为哈希漂移，在重新登记前不能作为已核验证据或外发来源。

### 8.2 证据账本

`02-evidence-ledger.yaml` 把 claim 分为：

- `fact`：可由已登记来源直接核验；
- `inference`：模型或研究者从事实推导出的解释；
- `hypothesis`：待实验验证的研究假设。

已核验事实必须带当前课题已关联的 `source_id` 和页码、章节、表格或可复核段落定位。账本还保存反证、置信度和局限，避免只收集支持性证据。

## 9. AI Co-Researcher 状态机

```mermaid
stateDiagram-v2
    [*] --> candidate_generation
    candidate_generation --> novelty_check: 候选结构通过
    novelty_check --> independent_review: 真实检索记录完成
    independent_review --> meta_review: Novelty / Methods / Medical Safety 三审齐全
    meta_review --> awaiting_human_decision: 汇总并冻结入围候选
    awaiting_human_decision --> completed: 研究者执行 approve-idea
    completed --> [*]
```

每个 `run` 保存：

- `manifest.yaml`：状态、预算、调用次数、产物哈希和最后错误；
- `work-packet.md`：给 Codex 技能的阶段工作包；
- `context.md` 或带哈希后缀的上下文快照；
- `candidates.yaml`：结构化 Idea；
- 三份独立评审 JSON；
- `meta-review.json`；
- provider 输出和 `.provenance.json`；
- 对应的哈希链 journal 事件。

重要约束：

- Provider 可以生成候选、评审和汇总，但不能伪造真实 novelty 检索；
- 三份评审必须对应当前 `run_id` 和同一组 Idea；
- 模型只能给出排序建议，不能写入最终 `selected`；
- `approve-idea` 必须由研究者提供批准理由，并原子完成 run；
- 重跑 `cycle` 会从已校验产物恢复，只有 `--new-run` 才新建循环；
- 不保存隐藏思维链，只保存简洁理由、证据位置、冲突、哈希和 provenance。

## 10. 外部模型与 DeepSeek

复制示例配置，不要提交真实配置或 Key：

```powershell
Copy-Item .\config\providers.example.yaml .\config\providers.yaml
$env:DEEPSEEK_API_KEY="你的真实 Key"
```

`config/providers.yaml` 中的角色是路由别名，可为每个角色指定 OpenAI Chat Completions 兼容的 `base_url`、`model`、`api_key_env`、温度和超时。模型名称会随服务商变化，使用前应以服务商当前官方文档为准。

外发采用双重授权：

1. 命令必须带 `--allow-external-api`；
2. 每个参与上下文的底层来源在登记时也必须允许外发。

此外还会校验本地文件哈希、课题关联、账本 claim 的来源范围和潜在可识别医疗字段。API Key 只从环境变量读取，不写入配置、日志或 provenance。Provider 响应上限为 1 MiB。

## 11. 可靠性与安全不变量

后续开发不得绕过以下约束：

1. **课题证据隔离**：B 课题不能引用只关联 A 课题的来源。
2. **真实来源门禁**：未知、漂移或未授权的来源不能进入已核验事实或外发上下文。
3. **人工产物优先**：网络等待期间用户新建的文件不得被 provider 覆盖。
4. **路径安全**：`projects`、`library` 和 run 目录不得通过符号链接、Windows junction 或中途目录替换写到工作区外。
5. **原子变更**：来源登记、课题关联、manifest、Idea 档案和 journal 的跨文件变更失败时必须回滚。
6. **有界调用**：调用前占用预算；网络错误和坏响应同样消耗一次，防止无限重试。
7. **并发安全**：provider 调用预算使用跨平台 advisory lock，陈旧 lock 不能永久阻塞后续运行。
8. **Create-only 提交**：provider 产物只填补缺失阶段文件，提交前再次校验目录身份与目标不存在。
9. **可审计恢复**：manifest 状态、产物哈希、当前 run、三审、selected Idea 和 journal 必须相互一致。
10. **医疗安全**：不接收可识别医疗数据，当前关键词拦截只是最低防线，不等同于完整 DLP。
11. **无隐藏 CoT**：持久化简洁判断依据，不要求或保存模型内部思维链。
12. **逐事实可定位**：每条“已报告事实”必须独立带当前 `source_id` 和与阅读范围一致、已在卡片声明的 locator；摘要卡只能使用 `abstract`。
13. **规范版本路由**：doctor 必须严格解析报告规范适用矩阵；旧规范由 `superseded_by` 路由到已核验的 active 版本。

## 12. 代码模块索引

| 模块 | 职责 | 后续开发注意点 |
|---|---|---|
| `cli.py` | 参数解析、退出码和事务编排 | 保持错误码和批量原子语义 |
| `project.py` | 工作区/课题创建、manifest、路径约束 | Windows reparse point 与目录身份是高风险区 |
| `sources.py` | 来源规范化、去重、哈希、授权 | 不能静默覆盖人工 notes |
| `pdf.py` | PDF 文本提取和页码边界 | 无文本层时应停止并提示 OCR |
| `evidence.py` | 证据账本加载和严格校验 | 不要自动修补或猜测 source_id |
| `guidance.py` | 阶段判断和唯一下一步 | 文件已编辑不等于质量门禁已过 |
| `ideas.py` | Idea schema、状态迁移、人工选择 | `selected` 只能来自人工批准路径 |
| `review.py` | 三路评审和 meta-review schema | 必须绑定当前 run 和 Idea 集合 |
| `cycle_context.py` | 构建可外发的最小上下文 | 所有 claim 逐条校验授权和归属 |
| `cycle.py` | run 状态机、provider 阶段、预算与恢复 | 当前约 1773 行，是未来拆分候选，但拆分前先补回归测试 |
| `provider_config.py` | Provider 角色配置校验 | 配置不保存 Key |
| `provider.py` | OpenAI-compatible 调用和 provenance | 维持 HTTPS、大小限制和显式授权 |
| `journal.py` | 追加式哈希链研究日志 | journal 损坏必须阻断状态推进 |
| `doctor.py` | 只读工作区完整性检查 | 任何数据损坏都应转为可读 FAIL，而不是异常崩溃 |
| `io.py` | 原子写入和 create-only 基元 | 不要退化为普通覆盖写 |
| `knowledge.py` | catalog/card/profile schema、来源和路径校验、KB doctor | 阅读范围和 locator 门禁不能放宽 |
| `knowledge_search.py` | Unicode/CJK token、固定权重检索和稳定排序 | 禁止引入随机、联网或不可解释排序 |
| `knowledge_gaps.py` | 纯函数式知识维护分类、过滤和稳定排序 | 必须只读；固定日期应产生相同结果 |
| `knowledge_recommend.py` | 课题画像、阶段、手册和报告规范推荐 | 最多三项，绝不自动关联项目证据 |
| `dashboard.py` | 课题快照、证据/Idea 汇总和最多三个行动 | 只能编排既有严格 reader；不得写文件或调用 provider |
| `dashboard_risks.py` | 对结构化事实执行稳定风险规则 | 不读文件、不解析自由文本、不把 unknown 当 observed |
| `meeting_brief.py` | 逐条路由有效/冲突/待核验/排除 claim，投影 active Idea 并生成组会问题 | 必须保留 locator、limitations、Idea 失败判据和人工理由；不得自动改写事实 |
| `manuscript_plan.py` | 将稳定简报投影为八章节就绪度、五类证据分栏和一个动作 | 公共 schema 必须显式序列化；不得生成全文、升级 claim 或泄漏内部 identity/token |

## 13. 开发与验证

首次安装：

macOS/Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m compileall -q src scripts
python -m pytest -q -W error
python -m pip check
python scripts/verify_wheel.py
git diff --check
```

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

每次修改后至少运行：

```powershell
$env:PYTHONUTF8="1"
.\.venv\Scripts\python.exe -m compileall -q src
.\.venv\Scripts\python.exe -m pytest -q -W error
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

发布或修改打包配置时，还应从临时目录安装 wheel，并运行 `tests/installed_wheel_smoke.py` 覆盖源码目录之外的真实安装路径。构建示例：

首选跨平台命令 `python scripts/verify_wheel.py`，它自动构建、安装、断开源码导入路径并运行完整用户旅程。单独构建示例：

```powershell
.\.venv\Scripts\python.exe -m pip wheel . --no-deps --no-build-isolation --wheel-dir dist
```

测试目录按领域拆分：CLI、课题、来源、证据、PDF、指导、Idea、评审、循环、上下文、provider、doctor、技能与工作区。修复缺陷时先添加能稳定复现问题的测试，再改实现。

## 14. 设计和提交脉络

主要设计文档：

- `docs/superpowers/specs/2026-08-12-research-os-design.md`：初始 Research OS；
- `docs/superpowers/specs/2026-08-12-research-os-daily-driver-design.md`：每日驾驶舱；
- `docs/superpowers/specs/2026-08-12-research-os-co-researcher-design.md`：有界 AI Co-Researcher；
- `docs/superpowers/specs/2026-08-12-research-methods-knowledge-base-design.md`：v0.4 专业知识库设计；
- `docs/superpowers/plans/2026-08-12-research-methods-knowledge-base.md`：v0.4 TDD 实施计划；
- `docs/superpowers/specs/2026-08-12-bilingual-knowledge-search-design.md`：v0.4.1 中文检索与维护队列；
- `docs/superpowers/plans/2026-08-12-bilingual-search-and-gaps.md`：v0.4.1 TDD 实施计划。
- `docs/superpowers/specs/2026-08-12-project-research-dashboard-design.md`：v0.5 课题研究驾驶舱；
- `docs/superpowers/plans/2026-08-12-project-research-dashboard.md`：v0.5 TDD 实施计划。
- `docs/superpowers/specs/2026-08-12-evidence-meeting-brief-design.md`：v0.6 证据绑定组会简报；
- `docs/superpowers/plans/2026-08-12-evidence-meeting-brief.md`：v0.6 TDD 实施计划。
- `docs/superpowers/specs/2026-08-13-evidence-manuscript-plan-design.md`：v0.7 证据绑定论文就绪计划；
- `docs/superpowers/plans/2026-08-13-evidence-manuscript-plan.md`：v0.7 TDD 实施计划。

关键提交脉络：

| 提交 | 内容 |
|---|---|
| `2f197d8` | 防篡改研究日志 |
| `cd0aaa6` | 证据绑定 Idea 档案 |
| `130e749` | 三路独立评审校验 |
| `2a26815` | 有界科研循环编排 |
| `e692934` | 显式授权的外部 provider |
| `ed71b62` | 暴露 cycle CLI |
| `2683e96` | `guide` 接入科研循环 |
| `23e0a8c` | 并发、回滚、上下文和人工文件保护加固 |
| `d21554b` | provider 预算锁崩溃恢复 |
| `8bd3cde` / `3ac6907` | v0.4 专业知识库设计及整理 |
| `bfcc833` | 知识目录、卡片和画像严格校验 |
| `71c2c9a` | 确定性知识检索 |
| `3bb4e9c` | 课题方法推荐 |
| `4b5c6f8` | `kb` CLI |
| `f7aa067` | `guide` 和 `doctor` 集成 |
| `bc0b34b` | v0.4 专业种子知识库 |
| `9e836b5` | Unicode/NFKC 与 CJK 确定性检索 |
| `b5dee43` | 28 条种子来源的人工双语别名 |
| `0bf1500` | 纯函数式知识维护缺口分类 |
| `9ff5f8c` | `kb gaps` 只读 CLI |
| `d3d03ae` | 课题级证据健康快照 |
| `ddf15ec` | Idea 状态与结构化风险规则 |
| `455c9d4` | 方法学参考和去重行动优先级 |
| `0f7ebe8` | `dashboard` CLI、JSON 与只读确定性测试 |
| `331178a` | 允许上层编排复用同一个项目目录身份 |
| `902d999` | 严格路由组会简报中的证据 claim |
| `6ac09c2` / `6408b4b` | active Idea 决策上下文与显式人工门禁 |
| `24c93e2` | `meeting-brief` Markdown/JSON CLI |
| `b3567bf` | 简报绑定完整 cycle 与 Idea archive 快照 |
| `da7b794` | cycle 评审产物的直接文件与目录身份校验 |
| `3957288` | dashboard 到简报之间贯穿 cycle 产物身份向量 |
| `03cbe1a` | manifest 与 Idea archive 身份绑定及末尾稳定复读 |

## 15. 已知限制与技术债

- 本仓库不执行实验，只把流程推进到严谨实验设计并接收外部聚合结果；
- 当前没有向量数据库、embedding 检索或知识图谱服务；
- 当前没有自动在线刷新论文和指南，来源仍需登记和核验；
- 当前知识库有 28 条种子来源和 17 张卡；`kb gaps` 已能列出缺卡、摘要升级和过期复核任务，但实际原文核验仍需人工完成；
- 医疗敏感字段拦截是保守关键词检查，不可替代机构数据治理和伦理审批；
- `cycle.py` 体积较大，未来可按状态阶段、事务和 provider 提交拆分，但必须保持现有恢复/并发测试；
- 自动评审是研究质量辅助信号，不能替代导师、同行评审、统计复核或临床验证；
- 软件尚未承诺稳定公共 Python API，现阶段优先保持 CLI 和文件格式兼容。
- 风险雷达只报告当前结构化 schema 能证明的条件；它不是临床风险管理、伦理审批或完整实验审计的替代品。

## 16. v0.4.1 专业知识库：已实现

> **实现状态：CLI、严格数据模型、确定性检索、推荐、guide/doctor 集成与种子资产均已存在。**

v0.4 的 Research Methods Knowledge Base 不是简单堆 PDF，当前包含：

- `library/knowledge/catalog.yaml` 统一目录；
- 方法卡、主题地图、场景 playbook 和医学报告规范；
- `kb search`、`kb gaps`、`kb recommend`、`kb doctor`；
- 28 条医疗 AI、推理、RAG、LoRA/QLoRA、DPO/RLHF、量化、评测与报告指南来源；
- 17 张知识卡，其中 10 张标记为全文/官方开放网页正文核验；
- 5 张主题地图、4 份方法手册和 1 份医疗 AI 报告规范矩阵；
- 可选的课题 `knowledge-profile.yaml`；
- 中英双语确定性检索、只读维护队列、来源分级、版本/失效日期和课题证据隔离。

完整规格见 `docs/superpowers/specs/2026-08-12-research-methods-knowledge-base-design.md`。后续重点是全文核验、版本维护与真实课题走查；达到至少 100 张核验卡前，不引入向量数据库。

## 17. v0.5 课题研究驾驶舱：已实现

> **实现状态：快照模型、证据隔离、Idea 状态、确定性风险、行动优先级、文本/JSON CLI 与只读测试均已存在。**

核心数据流：

1. `dashboard.py` 通过安全路径解析读取目标 `project.yaml`；
2. `SourceRegistry.verified_source_ids()` 与课题 `source_ids` 取交集，形成唯一允许的证据范围；
3. 证据账本用该范围重新严格校验，统计支持、反对、冲突和限制；
4. active cycle 与 Idea archive 必须通过原有 schema、run 绑定和来源校验；
5. 方法学参考直接复用 `guide` 已计算的最多三项推荐；
6. `dashboard_risks.py` 只接受不可变结构化事实，输出带稳定 code、severity、state 和 trigger 的风险；
7. 行动固定按 repair、workflow、evidence、methodology 排序，并按完整命令去重后截取前三项；
8. CLI 显式序列化 schema version 1，避免内部 dataclass 变化悄悄破坏 JSON。

发布复审后的加固：

- 来源 ID 必须是小写字母数字与单连字符组成的安全标识，不能把 shell 语法带入可复制命令；
- project manifest、账本、知识画像、ideas 目录与 archive 都必须是课题内真实直接文件/目录，链接和 reparse point 失败关闭；
- 方法知识库存在但损坏时 dashboard 返回错误码 2 和 `kb doctor` 提示，不静默伪装为“暂无推荐”；
- 只有没有 claim 级校验问题的证据才进入健康统计；
- Idea archive 必须同时绑定当前 project slug 与 active run；
- 候选生成、新颖性、独立评审和 meta-review 四个门禁只有在 `validate_cycle_artifacts` 验证冻结哈希、review run_id 和 selected Idea 后才标记完成。
- dashboard 在任何业务读取前只捕获一次当前课题目录身份，并将它贯穿 manifest、ledger、guide、knowledge profile、Idea archive 和 active cycle 读取；预检后或中途的同名目录替换会失败关闭；
- manifest、ledger、Idea archive 和知识 YAML 使用同一稳定直接读取原语：打开前后复核文件与父目录身份，拒绝 symlink/reparse，并在解析前确认读取期间未被替换；新颖性门禁还会逐个验证候选的 checked 状态、检索式、最近来源和差异说明。

新增或修改风险规则时，必须先在 `tests/test_dashboard.py` 写出可复现的结构化触发和 unknown 反例。不得扫描研究简报、claim statement 或模型输出关键词后声称发现医疗缺陷。新增行动命令必须来自现有受控 CLI/技能契约，不能把来源 notes、claim 文本或其他不可信内容拼进 shell 命令。

完整规格和计划分别见 `docs/superpowers/specs/2026-08-12-project-research-dashboard-design.md` 与 `docs/superpowers/plans/2026-08-12-project-research-dashboard.md`。

## 18. v0.6 组会研究决策简报：已实现

> **实现状态：严格 claim 路由、active Idea 投影、讨论问题、Markdown/JSON CLI、只读确定性和 wheel 用户旅程均已存在。**

`meeting-brief` 面向每周组会、导师一对一和开题准备，解决“系统知道状态，但研究者还要手工拼汇报”的缺口：

1. 捕获一次当前 project identity，并贯穿 dashboard、manifest、ledger、Idea archive 和 active cycle 读取；
2. 用当前课题已核验 source_id 重新运行 `validate_ledger`；
3. 只有完全通过 claim 级校验的记录能进入主体；`verified`、`conflicted` 和 open 分栏保留，不能互相升级；
4. 每条主体 claim 必须保留 statement、type、status、confidence、支持/反对的 `source_id + locator` 和 limitations；
5. 有问题的 claim 进入排除区，显示 issue code 和原因，不会在汇报正文中“消失”或伪装健康；
6. Idea 只来自当前 active run，复用冻结哈希、三审、meta-review、project/run 归属和 selected 校验；
7. 简报显式显示 cycle state、人工门禁、已选 Idea、失败判据、外部实验边界和人工批准理由；
8. 导师问题按阻塞、人工 Idea 决策、证据冲突/缺口和方法风险排序，最多三个；行动直接复用 dashboard 的安全命令，最多三个；
9. Markdown/JSON 输出稳定，只写 stdout；固定 `--as-of` 且工作区字节不变时输出一致。
10. dashboard 与简报二次读取之间以完整 cycle manifest 和 Idea archive 内容指纹绑定；审批、状态或候选内容中途变化时拒绝混合快照并要求重生成。
11. manifest、Idea archive、candidates、三份独立评审和 meta-review 必须来自真实直接文件；run、reviews 目录及各状态/产物的身份向量会跨 dashboard 和简报二次读取贯穿，并在输出前稳定复读，目录联接、reparse point、同内容替换和读取期间的同名目录替换都会失败关闭。

命令示例：

```powershell
.\.venv\Scripts\research-os.exe meeting-brief `
  --project medical-reasoning `
  --as-of 2026-08-12 `
  --format markdown
```

该简报是研究决策辅助，不是临床决策支持。它不能把公开基准结果外推为临床效用，也不能替代导师、统计复核、伦理审批或真实实验。

完整规格和计划分别见 `docs/superpowers/specs/2026-08-12-evidence-meeting-brief-design.md` 与 `docs/superpowers/plans/2026-08-12-evidence-meeting-brief.md`。

## 19. v0.7 证据绑定论文就绪计划：已实现

> **实现状态：严格 claim 路由、八章节门禁、单一下一步、Markdown/JSON、只读确定性和 wheel 用户旅程均已接入。**

`manuscript-plan` 解决“材料很多，但不知道哪些内容已经足以安全进入哪一节”的问题。它不生成全文，而是调用 `build_meeting_brief()` 获得经过项目路径、证据账本、active cycle 和 Idea archive 稳定性校验的同一快照，然后执行纯函数投影：

1. `fact + verified` 且通过当前课题 `source_id + locator` 校验的记录进入 `citation_candidates`；
2. 未完全核验事实进入 `open_facts`，inference/hypothesis 进入 `research_statements`，冲突与结构问题分别进入 `conflicts` 和 `excluded_claims`；任何分组都不改变原 claim 类型或状态；
3. 固定输出 Abstract、Introduction、Related Work、Methods、Experiments、Results、Limitations and Ethics、Conclusion 八节，每节只依据稳定阶段 code、人工 selected Idea、结果输入和证据候选计算 `ready/partial/blocked`；
4. 有排除项时只建议修复账本；上游门禁未完成时复用 dashboard 已校验动作；研究简报、文献综合、人工 Idea 和引用候选就绪后，才给出一次 `$manuscript-assistant` 大纲动作；
5. 医疗 Idea 必须显式包含 `medical_safety_risks` 才能通过伦理边界要求；离线结果不被解释为临床效用；
6. 公共 JSON schema version 1 逐字段序列化，不使用 `asdict`，因此不会随内部 dataclass 扩展泄漏 snapshot token、目录/文件 identity；
7. 固定 `--as-of` 且输入字节不变时 Markdown/JSON 完全确定，命令执行前后工作区字节不变。
8. `artifacts/results-manifest.yaml` 是结果输入的唯一登记边界；条目必须给出直接子文件、支持的文本格式、SHA256、`source_repository` 和 `generated_at`。任意 README/日志/未登记文件不得推进 Results，清单、结果或阶段文档在快照期间变化会失败关闭。

命令：

```powershell
.\.venv\Scripts\research-os.exe manuscript-plan `
  --project medical-reasoning `
  --as-of 2026-08-13 `
  --format json
```

模块与测试归属：

- `src/research_os/manuscript_plan.py`：数据契约、严格分流、章节门禁、显式序列化与 Markdown；
- `src/research_os/cli.py`：只负责日期解析、调用和输出选择；
- `tests/test_manuscript_plan.py`：claim 不升级、章节状态、医疗安全、动作和 schema；
- `tests/test_manuscript_plan_cli.py`：真实课题、只读、确定性、错误码；
- `tests/installed_wheel_smoke.py`：从安装 wheel 完成 evidence → cycle → human approval → manuscript plan 用户旅程。

规格和计划分别见 `docs/superpowers/specs/2026-08-13-evidence-manuscript-plan-design.md` 与 `docs/superpowers/plans/2026-08-13-evidence-manuscript-plan.md`。

## 20. 安全扩展流程

新增功能建议遵循：

1. 先写或更新设计规格，明确用户旅程、非目标和失败语义；
2. 编写可逐步执行的实施计划；
3. 先写失败测试，再做最小实现；
4. 运行领域测试和完整回归；
5. 做静态审查，重点检查证据越界、目录替换、并发和中断恢复；
6. 运行 wheel 用户旅程；
7. 更新 README、本交接文档和版本号。

任何新自动化都应回答四个问题：

- 它使用的事实能否定位到来源？
- 它会不会跨课题泄漏证据？
- 中途失败或并发运行会留下什么？
- 哪个决定必须由研究者确认？

## 21. 新开发者从这里开始

```powershell
# 1. 阅读约束与产品说明
Get-Content .\AGENTS.md -Encoding utf8
Get-Content .\README.md -Encoding utf8
Get-Content .\docs\DEVELOPER-HANDOFF.md -Encoding utf8

# 2. 检查当前工作区
.\.venv\Scripts\research-os.exe doctor
git status --short

# 3. 建立可信基线
$env:PYTHONUTF8="1"
.\.venv\Scripts\python.exe -m pytest -q -W error

# 4. 再选择一项设计规格或缺陷开始开发
```

如果只记住一条原则：Research OS 的价值不在“替你多生成文字”，而在于让每一步都知道证据来自哪里、哪些只是推断、什么时候必须停止并交还给研究者。
