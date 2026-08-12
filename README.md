# Research OS

面向大模型研究生的本地科研驾驶舱：帮助你从模糊方向走到文献、Idea、实验设计、结果解读、论文写作和模拟审稿，同时把事实、模型推断和研究者判断分开保存。

它提供科研指导和整理减负，不执行训练、微调、量化、强化学习或集群任务；也不处理真实病例、可识别病历或个体诊疗请求。

## 每天只记一个命令

```powershell
.\.venv\Scripts\research-os.exe guide --project medical-reasoning
```

`guide` 会显示当前课题做到哪一步、哪里受阻，并且只给一个下一步以及可直接复制到 Codex 的技能指令。它不会调用模型猜进度，而是检查课题模板、显式关联的来源、论文卡片、证据账本和写作产物。

编辑文件只会让阶段变为“进行中”。对应 Codex 技能完成质量门禁并保留人工确认后，才写入阶段完成标记并允许 `guide` 推荐下一阶段；因此随手改一个字符不会被误判为完成。

## v0.5 课题研究驾驶舱

需要一次看清课题全局状态时，运行只读驾驶舱：

```powershell
.\.venv\Scripts\research-os.exe dashboard `
  --project medical-reasoning `
  --as-of 2026-08-12
```

`dashboard` 汇总六个区域：课题状态、证据健康度、Idea 与人工决策、方法学参考、风险雷达和最多三个今日行动。它复用 `guide` 的阶段与门禁，不建立第二套状态机；Idea 区显式给出候选生成、新颖性、独立评审和 meta-review 四个已校验门禁；行动按“修复阻塞 → 当前门禁 → 证据补全 → 方法增强”排序，并去除重复命令。

机器可读输出：

```powershell
.\.venv\Scripts\research-os.exe dashboard `
  --project medical-reasoning `
  --as-of 2026-08-12 `
  --format json
```

相同工作区字节、课题和 `--as-of` 会得到相同输出。命令只读、不联网、不调用 DeepSeek/OpenAI、不创建缓存，也不修改课题、证据账本、科研循环或知识库。风险只由结构化事实触发；无法确认的医疗或实验条件不会伪装成已发现问题。全局方法条目不会自动成为当前课题引用证据。

若知识库损坏、科研循环产物哈希不一致、Idea 档案属于其他课题，或 project/ledger/archive 被替换成链接，命令会以错误码 2 关闭，不输出看似健康的部分报告。无效 claim 仍会显示校验问题，但不会计入健康证据数量。

## 第一次使用

要求 Python 3.11 或更高版本。在当前仓库打开 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\research-os.exe doctor
```

`doctor` 是只读检查，不修改文件。它会检查 Python、工作区目录、11 个科研技能、来源登记表、本地来源哈希、课题完整性、Idea 档案、科研循环日志和中文终端。

创建课题并进入驾驶舱：

```powershell
.\.venv\Scripts\research-os.exe new-project `
  --title "医疗诊断大模型的可靠推理" `
  --slug medical-reasoning

.\.venv\Scripts\research-os.exe guide --project medical-reasoning
```

新课题位于 `projects/medical-reasoning/`，包含：

- `START-HERE.md`：三十秒入口；
- `project.yaml`：课题身份与显式关联的 `source_id`；
- `00-research-brief.md`：研究问题、边界和失败判据；
- `01-search-log.md`：检索与纳排记录；
- `02-evidence-ledger.yaml`：支持、反对、冲突和限制；
- `03` 至 `06`：综述、Idea、实验设计和结果解读；
- `writing/`、`reviews/`、`artifacts/`：稿件、审稿与外部聚合结果。

接着把 `guide` 输出的 `$research-project-init ...` 指令交给 Codex。

## 批量收论文：推荐入口

建立 UTF-8 清单，例如 `inbox/sources.txt`：

```text
# 每行一个公开来源
doi:10.1000/example
arXiv:2401.01234
https://example.org/paper
./paper.pdf
```

相对文件路径以清单所在目录为基准。一次性登记并关联到课题：

```powershell
.\.venv\Scripts\research-os.exe add-sources `
  ".\inbox\sources.txt" `
  --project medical-reasoning `
  --notes "第一轮种子文献"
```

批量导入采用全有或全无语义：坏一行会报告清单行号，`library/sources.jsonl` 和 `project.yaml` 都不会留下本批半成品。重复来源复用原 `source_id`，不覆盖首次人工笔记。

单条来源仍可登记：

```powershell
.\.venv\Scripts\research-os.exe add-source `
  "doi:10.1000/example" `
  --project medical-reasoning
```

多课题时务必传 `--project`。系统只统计课题在 `project.yaml` 中显式关联的来源，不把全局文献擅自归给其他课题。

## PDF 精读

先登记 PDF，再提取保留页码边界的文本：

```powershell
.\.venv\Scripts\research-os.exe add-source `
  ".\inbox\paper.pdf" `
  --project medical-reasoning

.\.venv\Scripts\research-os.exe extract-pdf `
  ".\inbox\paper.pdf" `
  --output ".\library\sources\paper.extracted.md"
```

提取文本使用 `<!-- page:N -->` 标记页面。扫描版 PDF 没有文本层时，命令会停止并提示 OCR，不会猜测正文。随后让 `guide` 给出 `$paper-deep-read` 指令。

## 端到端工作流

| 阶段 | Codex 技能 | 核心产物 |
|---|---|---|
| 课题定义 | `$research-project-init` | 可证伪研究简报 |
| 资料分诊 | `$paper-intake` | 已去重且关联课题的来源 |
| 论文精读 | `$paper-deep-read` | 带 source_id 和页码定位的论文卡片 |
| 文献综合 | `$literature-synthesis` | 共识、冲突、矩阵和研究空白 |
| Idea 循环 | `$research-cycle` | 候选档案、新颖性检索、三路独立评审与人工 shortlist |
| 单次 Idea 反审 | `$idea-review` | 最强反对意见、新颖性与可行性 |
| 实验设计 | `$experiment-advisor` | 基线、消融、统计和失败判据 |
| 结果解读 | `$result-interpreter` | 能支持与不能支持的结论 |
| 论文写作 | `$manuscript-assistant` | 基于核验证据的稿件与引用缺口 |
| 模拟审稿 | `$mock-reviewer` | 方法、统计、复现和医疗安全审查 |
| 周复盘 | `$research-weekly-review` | 证据变化、阻塞和三个下周行动 |

Codex 从仓库根目录的 `.agents/skills` 发现这些技能。如果技能列表未刷新，重启 Codex 并重新打开本仓库。

## 有界 AI Co-Researcher 循环

证据账本和文献综合就绪后，启动或恢复同一个 run：

```powershell
.\.venv\Scripts\research-os.exe cycle `
  --project medical-reasoning `
  --max-ideas 4 `
  --max-calls 6
```

默认不联网、不调用外部模型，也不外发任何文件。首次运行会创建 `run_id`、`work-packet.md`、空 Idea 档案和哈希链研究日志，然后只返回一个动作。把输出中的指令交给 Codex，例如：

```text
$research-cycle 推进 medical-reasoning 的当前 run，只处理工作包指定阶段
```

循环固定经过：候选生成 → 真实文献新颖性检索 → Novelty / Methods / Medical Safety 三路独立评审 → meta-review → 等待研究者。每次重新运行 `cycle` 都从已校验产物恢复，不重复已完成阶段；`--new-run` 才会保留旧 run 并新建一个。

模型或技能都不能写入 `selected`。只有研究者在当前 run 已通过候选冻结、三审和 meta-review 后，才能执行：

```powershell
.\.venv\Scripts\research-os.exe approve-idea `
  --project medical-reasoning `
  --idea idea-0003 `
  --reason "证据充分、资源可控，并保留明确失败判据"
```

系统不保存隐藏思维链，只保存简洁理由、证据定位、冲突、哈希和 provenance。模型自评分只是排序建议，不能证明科学真实性或临床效用。

## 实验边界

Research OS 会把流程推进到 `05-experiment-design.md`，然后明确等待独立实验仓库的结果，不会在本仓库执行训练。

完成外部实验和人工复核后，只把公开或脱敏的聚合结果放到：

```text
projects/<slug>/artifacts/
```

再次运行 `guide`，它会推荐 `$result-interpreter`。不要把真实病例、姓名、住院号、联系方式或原始可识别健康数据放进本工作区。

## 证据账本

事实、推断和假设分别使用 `fact`、`inference`、`hypothesis`。已核验事实必须有登记过的 `source_id` 和页码、章节或可复核段落：

```yaml
claims:
  - claim_id: C001
    statement: "论文报告方法 A 在公开数据集 B 上优于基线 C"
    type: fact
    status: verified
    support:
      - source_id: src-0123456789abcdef
        locator: "p. 6, Table 2"
    opposition: []
    confidence: medium
    limitations: "单一公开数据集，不能说明临床效用"
```

校验命令：

```powershell
.\.venv\Scripts\research-os.exe validate-ledger `
  ".\projects\medical-reasoning\02-evidence-ledger.yaml" `
  --workspace .
```

退出码 `0` 表示通过，`1` 表示证据问题，`2` 表示输入或工作区错误。`guide` 发现账本损坏、未知来源或本地文件哈希漂移时会阻止进入 Idea 和写作阶段。

## 可选 DeepSeek / OpenAI-compatible API

外部 API 不是必需项。默认禁止把任何来源发给外部模型；API Key 只从环境变量读取。

以 DeepSeek 为例，复制本地配置（`config/providers.yaml` 已被 Git 忽略），再在当前 PowerShell 会话设置 Key：

```powershell
Copy-Item .\config\providers.example.yaml .\config\providers.yaml
$env:DEEPSEEK_API_KEY="你的真实 Key"
```

示例的 `economy` 使用 `https://api.deepseek.com` 和 `deepseek-v4-flash`，`quality` 使用 `deepseek-v4-pro`。模型名可能变化，使用前应核对服务商官方文档。任何其他实现 OpenAI Chat Completions 的 HTTPS 端点也可作为自定义 role。

让外部 provider 推进当前可自动化阶段：

```powershell
.\.venv\Scripts\research-os.exe cycle `
  --project medical-reasoning `
  --provider-role economy `
  --max-calls 6 `
  --max-ideas 4 `
  --allow-external-api
```

外部模式要求命令级 `--allow-external-api`，并要求当前课题的每个底层来源在登记时都带有 `--allow-external-api` 且哈希未漂移。系统先生成精确 `context.md` 快照并登记其哈希，再发送同一字节内容；疑似可识别医疗字段会阻断外发。

预算采用调用前计费：请求发出前先原子增加 `calls_used`，网络失败或坏 JSON 也消耗一次，避免无限重试。三路独立评审开始前会检查剩余预算足够完成全部缺失角色，不够时一个都不调用。provider 不得替代真实文献检索。

保留的底层 `model-call` 命令适合一次性、显式授权的 OpenAI-compatible 调用。以两个已登记 prompt 文件为例：

把实际发送的 system 和 user 文件分别登记，并明确允许外发：

```powershell
.\.venv\Scripts\research-os.exe add-source ".\prompts\system.md" --allow-external-api
.\.venv\Scripts\research-os.exe add-source ".\prompts\task.md" --allow-external-api
```

记下两个 `source_id` 后调用：

```powershell
.\.venv\Scripts\research-os.exe model-call `
  --base-url "https://api.deepseek.com" `
  --model "你实际可用的模型名" `
  --api-key-env "DEEPSEEK_API_KEY" `
  --system ".\prompts\system.md" `
  --user ".\prompts\task.md" `
  --output ".\artifacts\model-output.md" `
  --source-id "src-system文件的ID" `
  --source-id "src-task文件的ID" `
  --allow-external-api
```

命令同时检查调用级许可、来源级许可和当前文件哈希。成功后生成同名 `.provenance.json`，记录模型、参数、时间、用量和提示词哈希，但不记录 Key。配置参考 `config/providers.example.yaml`。

## v0.4.1 专业科研方法知识库

知识库不是随意堆积的 PDF 或模型记忆。`library/knowledge/catalog.yaml` 和带阅读范围、locator 的知识卡是唯一真源；主题地图与方法手册提供阅读和操作入口。当前种子库包含医疗 AI、诊断推理、CoT、RAG、LoRA/QLoRA、量化、DPO/RLHF、AI 科研自动化和医疗报告规范。

先做只读自检：

```powershell
.\.venv\Scripts\research-os.exe kb doctor
```

确定性搜索，相同目录和参数会得到相同排序：

```powershell
.\.venv\Scripts\research-os.exe kb search `
  "diagnostic accuracy" `
  --topic medical-ai `
  --verified-scope abstract `
  --limit 5
```

中文查询会经过本地 Unicode 规范化和 CJK 词片匹配，并优先使用人工维护的双语专业别名：

```powershell
.\.venv\Scripts\research-os.exe kb search "诊断准确性" --limit 5
.\.venv\Scripts\research-os.exe kb search "思维链" --limit 5
.\.venv\Scripts\research-os.exe kb search "微调量化" --limit 5
```

查看知识库维护缺口：

```powershell
.\.venv\Scripts\research-os.exe kb gaps `
  --as-of 2026-08-12 `
  --limit 20
```

`kb gaps` 按 `watch-review → metadata-review → missing-card → abstract-review → fulltext-upgrade → stale-review` 排序。它只输出维护建议，不联网、不改 catalog、卡片、核验状态或课题文件；`--as-of` 可固定复核日期，便于重复得到相同 JSON。

为课题生成最多三项阶段化方法参考：

```powershell
.\.venv\Scripts\research-os.exe kb recommend `
  --project medical-reasoning
```

项目可选 `knowledge-profile.yaml`：

```yaml
schema_version: 1
domains: [medical-ai]
tracks: [diagnostic-reasoning, rag]
study_type: diagnostic-accuracy-study
data_modalities: [text]
reporting_context: [diagnostic-accuracy]
```

缺少画像时系统给通用方法和补全提示，不会从自由文本猜测医疗场景。`metadata / abstract / fulltext` 三种核验范围严格分开；摘要卡不会冒充全文证据。全局知识条目默认只是方法学线索，只有经 `$paper-intake` 显式关联到目标 `project.yaml` 的 `source_id` 才能进入该课题证据账本、外发上下文或论文引用。

`guide` 会在保持唯一“下一步”的同时显示最多三项“方法学参考”。知识库损坏时，课题状态仍可读取，但参考区会提示先运行 `kb doctor`。

## 旧课题与升级

第一版课题没有 `project.yaml` 时，`guide` 可以从目录名和研究简报标题回退读取，但不会猜它用了哪些全局来源。之后执行带 `--project` 的 `add-source` 或 `add-sources`，系统会创建元数据并补充明确关联。

已有手工文件不会被自动覆盖；`guide` 只读。重新生成内容前仍应由 Codex 遵守 `AGENTS.md` 的文件保护规则。

## 常见问题

- **先运行什么？** 执行 `.\.venv\Scripts\research-os.exe doctor`，然后执行 `guide`。
- **中文帮助乱码？** `research-os.exe` 会在 Windows 自动配置 UTF-8；若直接运行其他 Python 脚本，可先设置 `$env:PYTHONUTF8="1"`。
- **批量导入失败？** 按错误中的清单行号修复，重新运行原命令；不要拆成循环导入。
- **PDF 提示 OCR？** 原 PDF 没有可搜索文本层，先用可信 OCR 工具生成可搜索副本。
- **证据校验失败？** 修复 source_id、原文定位、状态或限制说明，不要为了通过而伪造字段。
- **`guide` 要求显式课题？** 工作区有多个课题；添加 `--project <slug>`。
- **技能没有出现？** 从仓库根目录重启 Codex，确认 `.agents/skills` 存在。
- **外部 API 被拒绝？** 只有公开或确认脱敏的材料才能显式授权；文件修改后必须重新登记。

## 全部 CLI

```text
doctor            只读工作区自检
guide             课题驾驶舱与唯一下一步
dashboard         课题全局状态、证据风险与最多三个今日行动
cycle             创建或恢复有界科研循环
approve-idea      研究者批准当前 run 的入围 Idea
new-project       创建课题
add-source        登记单条来源
add-sources       原子批量登记来源
extract-pdf       提取带页码边界的 PDF 文本
validate-ledger   校验证据账本
model-call        调用显式授权的外部模型
kb doctor         检查知识目录、卡片、来源与引用
kb search         确定性本地方法学检索
kb gaps           只读列出知识核验与卡片维护缺口
kb recommend      按课题画像和阶段推荐最多三项参考
```

## 开发验证

```powershell
$env:PYTHONUTF8="1"
.\.venv\Scripts\python.exe -m compileall -q src
.\.venv\Scripts\python.exe -m pytest -q -W error
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

## v0.4 恢复、证据与并发安全

- 调用额度通过 `provider-budget lock` 原子占位，并对陈旧 manifest 做并发校验；网络失败和无效响应仍计入额度。
- provider 产物使用 `create-only commit`：调用等待期间若研究者写入候选、评审或 meta-review，系统拒绝覆盖人工文件。
- 外发前逐条校验证据账本的 claim/source_id；上下文变化时保留原 `context.md`，新快照写入 `context-<sha256前16位>.md`。
- `approve-idea` 会原子完成 run；批准成功后直接运行 `guide`，下一步进入 `$experiment-advisor`，无需再补一次 `cycle`。
- `doctor` 校验 run 状态、冻结产物哈希、三路评审、人工 selected Idea，以及 journal 中引用的 run 和产物是否真实存在。
- `kb doctor` 校验 catalog schema、来源登记、阅读范围、全文 locator、替代关系、陈旧复核、知识资产引用和路径安全。
- `kb search` 使用可解释固定权重，不依赖联网、embedding、随机数或当前时间；`kb recommend` 永不自动关联项目来源。
- `kb search` 使用 NFKC、CJK 二元词片和人工双语别名支持中文术语；`kb gaps` 只读生成确定性维护队列。
- `dashboard` 以版本化 JSON 聚合课题、证据、Idea、方法、风险和行动；固定 `--as-of` 后可复现且执行前后工作区字节不变。
- 每条“已报告事实”都必须独立携带当前 `source_id` 和范围一致的 locator；摘要卡不能借正文定位越级。
- 报告规范适用矩阵采用严格 schema，并在旧规范有 `superseded_by` 时自动路由到已核验的 active 新版。

日常导航设计见 `docs/superpowers/specs/2026-08-12-research-os-daily-driver-design.md`，v0.5 课题研究驾驶舱设计见 `docs/superpowers/specs/2026-08-12-project-research-dashboard-design.md`。有界 Co-Researcher 设计见 `docs/superpowers/specs/2026-08-12-research-os-co-researcher-design.md`。知识库设计见 `docs/superpowers/specs/2026-08-12-research-methods-knowledge-base-design.md`，开发交接见 `docs/DEVELOPER-HANDOFF.md`。
