# 大模型适配研究手册

## 比较矩阵

统一底座、tokenizer、训练数据、清洗、序列长度、优化步数和评价预算，比较 prompt-only、SFT、LoRA/QLoRA、量化后推理以及需要时的 DPO/PPO 路径。

## 必报资源

可训练参数、峰值 GPU 显存、GPU 型号与数量、训练时间、吞吐、推理延迟、量化 kernel/库版本、checkpoint 大小和失败/OOM。

## 质量与安全

分别评价任务质量、事实性、校准、鲁棒性、长度偏差、拒答、安全和分布外表现。自动 judge 至少用盲法人工样本复核。

## 证据入口

LoRA `src-b85d9dbf9c291e18`；QLoRA `src-5324ffa2c26905b3`；DPO `src-3bdad22db8b074df`；InstructGPT/RLHF `src-81125c1bcbaa0fea`；GPTQ/AWQ/int8 `src-0d1e60374ee440ce`、`src-95c4b65eb758c2cc`、`src-842dd0204d45dd71`。

## 失败判据

预算不一致、只报单一平均分、缺少训练/推理资源、自动评审无人工校准时，不比较“更高效”或“更好”。
