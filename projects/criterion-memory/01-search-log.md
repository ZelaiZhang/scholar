# criterion-memory：检索日志

<!-- research-os:generated:start -->
检索日期：2026-09-30。目的：主动检查知识树、回退、条件证据和学习记忆是否已有高度相近工作。
检索工具：网页搜索与论文/作者官方页面；没有下载任何病例或运行作者代码。

| 查询/直接核对 | 得到的重点材料 | 已读范围 |
|---|---|---|
| SCID-5 official FAQ | Columbia SCID-5 FAQ | What is the SCID-5? 与版本说明 |
| SCID-5 hierarchical state machine context tree / PsyCoTalk | arXiv:2510.25232v2 | 引言、§4.1、§4.2、§5（局部正文，非全文精读） |
| structured knowledge-guided memory psychiatric diagnosis | ProAI, arXiv:2502.20689v1 | §3.2，尤其 §3.2.2 |
| reinforcement learning context folding / learned memory | Context-Folding v1; Memory-R1 v5 | 摘要与版本元数据 |
| DSM-grounded diagnostic benchmark | MentalBench v2 与作者仓库 README | 摘要/公开说明；未读数据内容 |
| psychiatric context management reinforcement learning | arXiv:2607.15202v1 | 摘要、§III-A/III-B（局部正文） |
| diagnostic memory criterion LLM context 2026 | MHM v1; STITCH | 官方摘要；未全文精读 |
| PsyCoTalk license github | PsyCo-Diagnosis README | 数据说明与用途；许可尚未确立 |

登记清单：`public-sources.txt`；精确 source_id 和定位在证据账本及文献矩阵中。
检索命中不能证明创新空白。OpenReview 页面曾无法正常访问，未规避访问限制；使用公开 arXiv 正文核对方法，不据搜索片段认定会议录用状态。

## 下一轮补检索

1. 精读 ProAI、PsyCoTalk 的状态更新、上下文保留与停止机制。
2. 精读 Memory-R1、Context-Folding、MHM、STITCH 的算法和计算成本，判断可复现基线。
3. 检索 claim/evidence revision、belief tracking、temporal/negation-preserving summarization、constrained memory policies。
4. 核对 PsyCoTalk、MentalBench 的完整数据使用条件、病例组键与生成模板；没有许可不能启动数据实验。
5. 持续排查 2026 年精神科多轮评测工作；检索覆盖仍不充分，不能将未发现视为不存在。
<!-- research-os:generated:end -->
