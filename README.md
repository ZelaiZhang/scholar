# Research OS

一个面向大模型研究生的、证据优先的 Codex 科研工作区。它帮助你从模糊方向走到文献综合、Idea 审查、实验设计、结果解释、论文写作、模拟审稿和返修，同时把来源、推断和人工判断分开保存。

它不运行训练、微调、量化或强化学习，也不处理真实病例或可识别病历。实验代码应放在独立仓库中。

## 已包含什么

- 本地 PDF、DOI、arXiv、URL 和研究笔记的登记与去重。
- 保留页码边界的 PDF 文本提取。
- 论文卡片、文献矩阵和证据账本模板。
- 对已核验事实强制要求来源定位的校验器。
- DeepSeek 等 OpenAI-compatible API 的可选适配层。
- 十个可以被 Codex 自动发现的仓库级科研技能。
- 公开资料边界、医疗安全规则和可追溯 provenance。

## 安装

项目要求 Python 3.11 或更高版本。当前工作区已经创建 `.venv`；在 PowerShell 中执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\research-os.exe --help
```

如果以后复制到新电脑：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## 五分钟开始

### 1. 创建课题

```powershell
.\.venv\Scripts\research-os.exe new-project `
  --title "医疗诊断大模型的可靠推理" `
  --slug medical-reasoning
```

课题会创建在 `projects/medical-reasoning/`。先填写 `00-research-brief.md`，尤其是研究问题、边界和失败判据。

### 2. 登记公开论文

本地 PDF：

```powershell
.\.venv\Scripts\research-os.exe add-source ".\inbox\paper.pdf" `
  --notes "导师推荐，优先精读"
```

DOI、arXiv 或网页：

```powershell
.\.venv\Scripts\research-os.exe add-source "doi:10.1000/example"
.\.venv\Scripts\research-os.exe add-source "arXiv:2401.01234"
.\.venv\Scripts\research-os.exe add-source "https://example.org/paper"
```

重复来源返回相同 `source_id`，不会覆盖首次保存的人工笔记。

### 3. 提取 PDF 文本

```powershell
.\.venv\Scripts\research-os.exe extract-pdf ".\inbox\paper.pdf" `
  --output ".\library\sources\paper.extracted.md"
```

输出使用 `<!-- page:N -->` 标记页边界。扫描版 PDF 会停止并提示先做 OCR，不会让模型猜正文。

### 4. 让 Codex 精读

在本仓库的新 Codex 任务中输入：

```text
$paper-deep-read 请精读 library/sources/paper.extracted.md，
source_id 是 src-xxxxxxxxxxxxxxxx，生成论文卡片。
```

Codex 从仓库根目录 `.agents/skills` 自动发现技能；若技能列表没有立即刷新，重启 Codex。仓库技能位置和显式 `$skill-name` 调用方式来自[官方 Codex 技能文档](https://developers.openai.com/codex/skills)。

### 5. 校验证据账本

```powershell
.\.venv\Scripts\research-os.exe validate-ledger `
  ".\projects\medical-reasoning\02-evidence-ledger.yaml" `
  --report ".\projects\medical-reasoning\artifacts\evidence-check.md"
```

返回码 `0` 表示通过；`1` 表示存在缺失来源、页码、状态或限制说明。

## 端到端技能

| 阶段 | 技能 | 示例请求 |
|---|---|---|
| 课题定义 | `$research-project-init` | 把“医疗大模型思维链”整理成一个可证伪课题 |
| 资料分诊 | `$paper-intake` | 登记 inbox 中的论文并按精读优先级分组 |
| 论文精读 | `$paper-deep-read` | 从全文生成带页码定位的论文卡片 |
| 文献综合 | `$literature-synthesis` | 综合这些卡片的共识、冲突和候选研究空白 |
| Idea 审查 | `$idea-review` | 对三个创新点做最严格的反向审查并排序 |
| 实验设计 | `$experiment-advisor` | 设计基线、消融、指标和失败判据，不运行实验 |
| 结果解释 | `$result-interpreter` | 检查这份实验表是否支持原假设，指出越界结论 |
| 论文写作 | `$manuscript-assistant` | 只根据已核验证据生成 Related Work 大纲 |
| 模拟审稿 | `$mock-reviewer` | 从方法、统计、复现和医疗安全四个视角审稿 |
| 周复盘 | `$research-weekly-review` | 根据本周文件和提交生成周报及三个下周行动 |

## DeepSeek 和其他外部模型

外部模型是可选项。Codex 仍负责工作区编排；低成本摘要、格式转换或独立审稿可以交给 OpenAI-compatible 服务。

DeepSeek 当前官方示例使用 `https://api.deepseek.com` 作为 `base_url`，再调用 `/chat/completions`；示例配置见 `config/providers.example.yaml`。[DeepSeek 官方 API 示例](https://api-docs.deepseek.com/guides/multi_round_chat/)

在当前 PowerShell 会话设置 Key：

```powershell
$env:DEEPSEEK_API_KEY="你的真实 Key"
```

不要把 Key 写入 `.env.example`、YAML、论文卡片或 Git。调用示例：

```powershell
.\.venv\Scripts\research-os.exe model-call `
  --base-url "https://api.deepseek.com" `
  --model "deepseek-v4-pro" `
  --api-key-env "DEEPSEEK_API_KEY" `
  --system ".\prompts\system.md" `
  --user ".\prompts\task.md" `
  --output ".\artifacts\model-output.json" `
  --allow-external-api
```

`--allow-external-api` 是硬门禁：不提供它就拒绝请求。只允许把公开资料或已确认脱敏的示例发送给外部服务。每次成功调用会生成同名 `.provenance.json`，其中记录模型、参数、时间、用量和提示词哈希，但不记录 API Key。

## 证据账本最小示例

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
    limitations: "单一公开数据集，尚不能说明临床效用"
```

允许的 `type` 是 `fact`、`inference`、`hypothesis`；允许的状态是 `unverified`、`partially_verified`、`verified`、`conflicted`。

## 推荐日常节奏

1. 新资料先进入 `inbox/`，登记后再阅读。
2. 每篇重要论文生成一张卡片，不把摘要等同于全文。
3. 每周更新一次文献矩阵和证据账本。
4. Idea 必须经过最近工作检索和最强反对意见检查。
5. 实验前写失败判据；实验后同时记录负结果和异常。
6. 写作前运行证据校验；投稿前运行多视角模拟审稿。
7. 用 Git 提交课题记录，提交信息说明新增了什么证据或修改了什么判断。

## 目录说明

```text
.agents/skills/   Codex 自动发现的科研技能
config/           隐私、证据和模型角色配置
inbox/            待处理公开资料；PDF 默认不进 Git
library/          来源登记、论文卡片和文献矩阵
projects/         每个研究课题的持久成果
templates/        各科研阶段的人工可读模板
src/research_os/  确定性 CLI 工具
tests/            自动测试
```

## 常见问题

- **中文帮助乱码**：先运行 `$env:PYTHONUTF8="1"`，再执行命令。
- **PDF 提示 OCR**：原文件没有文本层；先用可信 OCR 工具生成可搜索 PDF。
- **提示 Key 缺失**：在当前 PowerShell 会话设置配置中指定的环境变量。
- **外部 API 被拒绝**：确认材料是公开资料，再显式添加 `--allow-external-api`。
- **证据校验失败**：按报告补充 `source_id`、页码/章节、限制或正确状态，不要为了通过而伪造字段。
- **技能没有出现**：确认从仓库内启动 Codex，技能位于 `.agents/skills`，然后重启 Codex。

## 开发验证

```powershell
$env:PYTHONUTF8="1"
.\.venv\Scripts\python.exe -m pytest -q -W error
```

详细方案见 `docs/superpowers/specs/2026-08-12-research-os-design.md`，逐步实施记录见 `docs/superpowers/plans/2026-08-12-research-os.md`。

