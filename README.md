# Research OS

面向大模型研究生的本地科研驾驶舱：帮助你从模糊方向走到文献、Idea、实验设计、结果解读、论文写作和模拟审稿，同时把事实、模型推断和研究者判断分开保存。

它提供科研指导和整理减负，不执行训练、微调、量化、强化学习或集群任务；也不处理真实病例、可识别病历或个体诊疗请求。

## 每天只记一个命令

```powershell
.\.venv\Scripts\research-os.exe guide --project medical-reasoning
```

`guide` 会显示当前课题做到哪一步、哪里受阻，并且只给一个下一步以及可直接复制到 Codex 的技能指令。它不会调用模型猜进度，而是检查课题模板、显式关联的来源、论文卡片、证据账本和写作产物。

## 第一次使用

要求 Python 3.11 或更高版本。在当前仓库打开 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\research-os.exe doctor
```

`doctor` 是只读检查，不修改文件。它会检查 Python、工作区目录、10 个科研技能、来源登记表、本地来源哈希、课题完整性和中文终端。

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
| Idea 审查 | `$idea-review` | 最强反对意见、新颖性与可行性 |
| 实验设计 | `$experiment-advisor` | 基线、消融、统计和失败判据 |
| 结果解读 | `$result-interpreter` | 能支持与不能支持的结论 |
| 论文写作 | `$manuscript-assistant` | 基于核验证据的稿件与引用缺口 |
| 模拟审稿 | `$mock-reviewer` | 方法、统计、复现和医疗安全审查 |
| 周复盘 | `$research-weekly-review` | 证据变化、阻塞和三个下周行动 |

Codex 从仓库根目录的 `.agents/skills` 发现这些技能。如果技能列表未刷新，重启 Codex 并重新打开本仓库。

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

以 DeepSeek 为例，在当前 PowerShell 会话设置：

```powershell
$env:DEEPSEEK_API_KEY="你的真实 Key"
```

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
new-project       创建课题
add-source        登记单条来源
add-sources       原子批量登记来源
extract-pdf       提取带页码边界的 PDF 文本
validate-ledger   校验证据账本
model-call        调用显式授权的外部模型
```

## 开发验证

```powershell
$env:PYTHONUTF8="1"
.\.venv\Scripts\python.exe -m compileall -q src
.\.venv\Scripts\python.exe -m pytest -q -W error
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

设计规格见 `docs/superpowers/specs/2026-08-12-research-os-daily-driver-design.md`，实施计划见 `docs/superpowers/plans/2026-08-12-research-os-daily-driver.md`。
