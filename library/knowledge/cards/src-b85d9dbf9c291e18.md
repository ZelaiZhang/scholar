---
schema_version: 1
source_id: src-b85d9dbf9c291e18
title: LoRA Low-Rank Adaptation of Large Language Models
reading_scope: abstract
locators: [abstract]
reviewed_at: 2026-08-12
---

# LoRA Low-Rank Adaptation of Large Language Models

## 阅读范围

仅核验 arXiv 元数据与摘要。

## 研究问题与设置

摘要研究如何在冻结预训练权重时减少下游适配所需的可训练参数和显存。

## 方法

在 Transformer 层中注入可训练的低秩分解矩阵，并与全参数微调和适配器比较。

## 已报告事实

- LoRA 冻结预训练权重并训练低秩更新矩阵（`src-b85d9dbf9c291e18`，abstract）。
- 摘要在当时的 RoBERTa、DeBERTa、GPT-2 与 GPT-3 设置报告参数和显存节省（同源，abstract）。

## 作者报告的限制

当前卡片未核验每个任务的秩、目标层、训练预算和显著性。

## 模型综合推断

`method_inference`：PEFT 的主要价值是资源约束下的可复现实验设计，不代表质量必然等同全量微调。

## 可迁移方法建议

报告目标层、rank、alpha、dropout、可训练参数、峰值显存、时间与全量/冻结基线。

## 不应外推的结论

摘要中的特定模型结果不能证明 LoRA 对所有架构、任务和数据规模都最优。

## 与其他来源的关系

`src-5324ffa2c26905b3` 在冻结 4-bit 基座上训练 LoRA，是相关但不同的预算方案。

## 人工备注

<!-- research-os:human-notes:start -->
实验设计应把质量和资源效率分成两个结论。
<!-- research-os:human-notes:end -->
