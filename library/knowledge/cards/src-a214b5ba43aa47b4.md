---
schema_version: 1
source_id: src-a214b5ba43aa47b4
title: Large language models encode clinical knowledge
reading_scope: fulltext
locators: ["Nature Main", "Human evaluation results", "Figures 4-6", "Discussion"]
reviewed_at: 2026-08-12
---

# Large language models encode clinical knowledge

## 阅读范围

核验 Nature 官方全文网页的研究设置、人工评价、结果与限制。

## 研究问题与设置

研究以 MultiMedQA 等医学问答任务评估通用与医学适配语言模型，并加入临床专家和普通用户评价。

## 方法

除自动题目得分外，研究让临床医生从科学一致性、错误、遗漏、潜在伤害和偏差等维度评价长回答。

## 已报告事实

- 长回答评价覆盖科学共识、错误、遗漏、伤害与偏差（`src-a214b5ba43aa47b4`，Figures 4-6）。
- 详细人工评价使用 140 个问题，每个回答由一位临床医生评价，并用 bootstrap 区间描述不确定性（`src-a214b5ba43aa47b4`，Human evaluation results）。

## 作者报告的限制

作者指出模型可能反映训练截止时的旧科学共识；详细人工评价样本和每题评审人数也限制推广。

## 模型综合推断

`method_inference`：医疗 LLM 评价不能只报告考试准确率，至少应覆盖错误严重性、伤害、遗漏、偏差和时间漂移。

## 可迁移方法建议

在实验设计中把技术性能、临床安全、用户感受和科学共识分成不同指标族。

## 不应外推的结论

医学问答表现不等同于真实诊断能力、临床效用或可部署性。

## 与其他来源的关系

与 `src-645320e6e9773efa` 和 `src-db68e44456743d0b` 共同构成从医学问答到诊断辅助与对话评价的证据链。

## 人工备注

<!-- research-os:human-notes:start -->
医疗 LLM 评价的核心背景卡。
<!-- research-os:human-notes:end -->
