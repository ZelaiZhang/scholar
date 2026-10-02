# 研究者材料转录：既有诊断树系统与复判

> 来源登记用研究者笔记，2026-10-02。以下仅记录研究者已提供的图示和文字；不证明代码、实验配置或机制已经独立核验。未复制扫描书、病例文本或原图片。Image 编号对应原对话，图片内容哈希见 reinspection-review-v0.2.provenance.json。

## M1：树与历史表示的文字说明

研究者说明：树的知识基础来自 SCID-5 的一本扫描 PDF，版本和使用许可待确认。树保存每轮对话；历史改为带轮次的 JSON，并包括节点判断或诊断条件状态。去除重复提问的功能曾干扰节点判断，JSON 格式组织是研究者对此的修复。此观察未附受控消融计数，不能量化为已证实的 JSON 收益。

## M2：Image #3，面板 a 与 b

图示标题为 Adaptive Diagnostic Interviewing Jointly Driven by Diagnostic Criteria and Structured Evidence。实线表示已实现，虚线表示计划。

面板 a：知识来源列为 DSM-5 Criteria、SCID-5 Questions、Clinical Coding Rules。标准化包含复合条件拆解、时间和阈值抽取、排除条件和逻辑关系。结构化树列出 ID、Criterion、Question、Count、Diagnosis/Exclusion nodes。

面板 b：访谈前记录和症状类别用于组织候选树。Current experiment 为 run all trees in the same category。Deployment extension: screening → ranking → Top-K 使用虚线，尚为计划。

## M3：Image #3，面板 c

当前条件、完整对话历史、症状笔记、已评估条件进入条件级访谈推理。步骤为拆解条件（临床目标、时间范围、决策条件）、检索相关问答、结构化证据判断、判断是否可决定。

Same-turn evidence 列出 Doctor-question quote、Patient-response quote、Observed fact、Support / Refute / Insufficient。Evidence validation 列出 Valid turn、Quotes from the same turn、Relation matches label。

可决定时记录条件判断；不确定时识别缺失信息、生成或改写追问、接收回答并继续循环。Dual-Memory Update 包括控制树遍历的 Criterion state 与跨节点复用的 Symptom notes。图中说明完整对话历史仍是首要证据来源。

## M4：Image #3，面板 d 与 e

面板 d 的实线树内推理包括条件分支、计数与阈值判断、分支回溯；终点为当前疾病诊断、候选树排除或证据不足需复查。保护措施列为最多三轮追问、无效输出重试、二值回退、保留推理轨迹。何时使用回退、具体回溯行为及其是否修订旧节点，需代码核验。

面板 e 的跨树验证标为 Planned：汇总候选树结果、比较证据覆盖、独立 DSM-5 / ICD-11 验证，以及必要时补充访谈/测试/临床医生复核。不将这个计划面板等同于研究者后来增加的最终独立复判。

## M5：复判版本与方式的文字回复

针对“Qwen 表中 Ours 从 110/132 变成 117/132，是否来自同一批病例、同一模型，只增加了复检”的问题，研究者回复：**“只增加了复检，其余设置相同”**。

针对复检具体复查内容，研究者回复：**“对树输出做最终独立复判”**。

这是研究者对版本差异的确认，不是配置文件逐字段核对；“独立”描述流程角色，未确认模型、提示、证据可见范围、是否隐藏原输出或随机种子独立。

## M6：本轮写作诉求与指标关注

研究者指出正确树的正确率较高，但由于正类条数少，少判对一个会使该指标下降较多；要求围绕已有材料写一篇论文，强调树式方法已有表现。

原文：“但是其实我的正确树的正确率都蛮好的所以虽然错误树排除了但是正确树少了一个他的指标就很难看了”。随后：“围绕我给你的这些内容你能不能写一篇论文，毕竟走树我的效果指标还是不错的”。

## M7：尚未收到的元数据

132 项树判断对应多少源病例、病例与候选树配对方式，仍未确认。Direct/CoT/ICL 的准确提示、候选知识公平性、数据来源与标签获得方式、临床人员参与、训练测试划分、运行配置、成本及逐例配对改判均未提供。不补写这些信息为事实。
