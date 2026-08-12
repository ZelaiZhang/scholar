---
name: research-project-init
description: 创建证据优先的新科研课题工作区。用于用户提出新方向、选题、开题、研究问题或希望把模糊想法整理为可验证课题时。
---

# 初始化科研课题

## 输入

- 获取课题标题、英文 slug、初步方向和已知约束。
- 读取根目录 `AGENTS.md`、`config/research.yaml` 与 `src/research_os/templates/research-brief.md`。

## 流程

1. 检查输入是否包含真实病例或其他可识别健康信息；发现后立即停止。
2. 把方向改写为可证伪的问题，明确对象、任务、比较对象、结果和边界。
3. 运行 `python -m research_os new-project --title "标题" --slug slug`。
4. 填写 `00-research-brief.md`，记录关键词、资源约束、风险和停止条件。
5. 把推测标记为 hypothesis，把未知信息留空，不用流畅文本掩盖缺口。
6. 展示生成文件和下一步建议，等待人工确认研究问题后再进入检索。

## 输出

- 只创建 `projects/<slug>/` 下的标准课题文件。
- 不覆盖已存在课题，不替用户决定最终选题。

## 质量门禁

- 禁止编造论文、数据、基线或创新性结论。
- 明确区分事实、推断与假设。
- 确认未处理可识别健康信息。
- 确认 `00-research-brief.md` 含失败判据和人工确认项。
