# Mac 上使用 Research OS

在仓库根目录操作，Python 版本必须为 3.11 或更高。Research OS 的日常命令默认在本地读取资料，不需要模型 API Key。

## 安装与自检

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
research-os doctor
research-os kb doctor
```

以后每次打开终端，进入仓库并运行 `source .venv/bin/activate`。也可以直接调用 `.venv/bin/research-os`，无需激活。

## 建立课题

下面是命令示例，标题和 slug 由研究者确定：

```bash
research-os new-project --title "你的研究问题" --slug your-topic
research-os guide --project your-topic
```

编辑 `projects/your-topic/00-research-brief.md`，再按 `guide` 返回的技能指令推进。质量标记应在完成门禁并保留人工确认后写入，文件存在本身不代表科研阶段完成。

## 登记资料和读取论文

```bash
research-os add-sources inbox/sources.txt --project your-topic
research-os add-source inbox/paper.pdf --project your-topic
research-os extract-pdf inbox/paper.pdf --output library/sources/paper.extracted.md
research-os validate-ledger projects/your-topic/02-evidence-ledger.yaml
research-os guide --project your-topic
```

`sources.txt` 每行一个 DOI、arXiv、公开 URL 或本地路径。相对路径以清单所在目录为基准。扫描 PDF 需要先获得可搜索的 OCR 副本；系统不会猜测正文。原始资料和人工笔记应保留。

只登记公开资料、公开数据说明、脱敏示例和研究笔记。真实可识别病历不进入本仓库。外发来源需来源级授权和调用级授权。

## 查看状态与准备写作

```bash
research-os dashboard --project your-topic --as-of 2026-09-30
research-os meeting-brief --project your-topic --as-of 2026-09-30
research-os manuscript-plan --project your-topic --as-of 2026-09-30
research-os kb search "思维链" --limit 5
research-os kb gaps --as-of 2026-09-30 --limit 20
research-os cycle --project your-topic --max-ideas 4 --max-calls 6
```

固定 `--as-of` 用于复现同一日期的报告；日常查看可以省略。`cycle` 默认不调用模型。研究者批准 Idea 后才进入实验设计；实际训练和评测在独立实验仓库执行，按 README 的 `results-manifest.yaml` 契约导入聚合结果。

## 开发验证

```bash
python -m compileall -q src scripts
python -m pytest -q -W error
python -m pip check
python scripts/verify_wheel.py
git diff --check
```

`verify_wheel.py` 需要开发依赖中的 `build`。它在临时目录构建 wheel、建立独立环境并走完来源登记、证据、科研循环、人工批准和论文就绪计划；成功或失败后均清理临时目录。构建与安装依赖可能需要联网，科研自检和冒烟中的工作流不调用外部模型。

GitHub Actions 在 `main`、`mac` 的 push 和 pull request 时运行同样的验证。支持的运行组合为 Linux/Python 3.11、macOS/Python 3.12、Windows/Python 3.12。
