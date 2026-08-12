# 微调、量化与偏好优化方法地图

## 参数高效适配

- LoRA：`src-b85d9dbf9c291e18`。
- 4-bit 基座 + LoRA：`src-5324ffa2c26905b3`。

## 量化

- LLM.int8：`src-842dd0204d45dd71`。
- GPTQ：`src-0d1e60374ee440ce`。
- AWQ：`src-95c4b65eb758c2cc`。

## 偏好与强化学习

- 人类轨迹偏好：`src-73d0f49d618fabfa`。
- PPO：`src-673242e41cbe2b4c`。
- SFT + reward model + PPO 的 InstructGPT 管线：`src-81125c1bcbaa0fea`。
- 直接偏好优化：`src-3bdad22db8b074df`。

## 比较原则

把“训练质量”“资源可行性”“推理部署”“偏好数据质量”和“安全”分开。统一底座、数据、步数和评测预算；报告峰值显存、吞吐、延迟、能耗代理、质量退化和 OOM/不稳定失败。
