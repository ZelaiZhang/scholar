---
schema_version: 1
source_id: src-3bdad22db8b074df
title: Direct Preference Optimization Your Language Model is Secretly a Reward Model
reading_scope: abstract
locators: [abstract]
reviewed_at: 2026-08-12
---

# Direct Preference Optimization Your Language Model is Secretly a Reward Model

## 阅读范围

仅核验 arXiv 元数据与摘要。

## 研究问题与设置

摘要研究能否把带 KL 约束的 RLHF 目标重参数化为直接使用成对偏好数据的分类损失。

## 方法

DPO 不显式训练奖励模型，也不在微调期间从策略采样，直接优化偏好对上的目标。

## 已报告事实

- 摘要将 DPO 描述为比标准 RLHF 管线更简单的偏好优化方法（`src-3bdad22db8b074df`，abstract）。
- 摘要报告其在情感控制、摘要和单轮对话设置中的比较结果（`src-3bdad22db8b074df`，abstract）。

## 作者报告的限制

当前卡片未核验偏好数据来源、beta 敏感性、参考模型、长度偏差和完整评价。

## 模型综合推断

`method_inference`：简化优化器不能修复偏好标注偏差、覆盖不足或医学安全评价缺失。

## 可迁移方法建议

与 SFT、PPO-RLHF 和无参考/不同 beta 设定比较，并单独评价 win-rate、事实性、安全与长度。

## 不应外推的结论

摘要中的任务表现不能证明 DPO 普遍优于所有在线或离线偏好优化方法。

## 与其他来源的关系

`src-81125c1bcbaa0fea` 提供经典 SFT + 奖励模型 + PPO 管线背景。

## 人工备注

<!-- research-os:human-notes:start -->
医疗对齐课题必须有临床专家与伤害维度评价。
<!-- research-os:human-notes:end -->
