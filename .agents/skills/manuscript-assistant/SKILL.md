---
name: manuscript-assistant
description: 基于核验证据账本辅助论文写作。用于生成论文大纲、相关工作、方法描述、结果段落、摘要、图表说明或检查引用缺口时。
---

# 基于证据辅助论文写作

## 先过门禁

- 读取目标要求、已有人工文字、证据账本和结果解读；依次运行以下只读门禁，阻塞时只报告缺口，不起草：

```powershell
.\.venv\Scripts\research-os.exe manuscript-plan --project <slug> --as-of YYYY-MM-DD --format markdown
.\.venv\Scripts\research-os.exe validate-ledger projects/<slug>/02-evidence-ledger.yaml --workspace .
```

- 发现可识别健康信息立即停止；只处理公开或脱敏资料。

## 起草规则

每个起草的正文块前必须紧邻放一个精确的隐藏注释；不得用 `【fact｜...】` 等可见伪标签替代：

```markdown
<!-- research-os:kind=fact; claims=C001 -->
<!-- research-os:kind=inference; claims=I001 -->
<!-- research-os:kind=hypothesis; claims=H001 -->
<!-- research-os:kind=limitation; claims=L001 -->
<!-- research-os:kind=method; idea=idea-0001 -->
<!-- research-os:kind=result; artifacts=aggregate-results.csv -->
```

- `fact` 仅绑定可引用的已核验 claim；`inference`、`hypothesis` 必须与账本类型完全一致；`limitation` 必须绑定有效局限；`method` 只绑定 active cycle 已经 `completed` 后投影的研究者 selected Idea；`result` 只绑定已登记的聚合结果 artifact，且 `06-result-analysis.md` 的逐文件 name+sha256 绑定必须与当前结果清单完全一致。
- 注释绑定 provenance，不建立语义蕴含、统计正确性或临床效用；研究者必须逐句核对。
- artifact 文件名使用跨平台直接文件语法，不得使用路径分隔符、Windows ADS/设备名、非 ASCII、尾随点或空格，也不得用大小写别名指向同一结果。
- 示例不是证据。删除未使用示例；除非对应 ID 或 artifact 真实存在，不得把 `C001`、`I001`、`H001`、`L001`、`idea-0001` 或 `aggregate-results.csv` 当作真实依据。
- 按用户指定部分起草，不扩张贡献、结果或适用范围，并标记引用缺口、术语不一致和过度声明。

## 收尾与边界

- 写入 `writing/` 的新文件或明确生成区块，绝不覆盖人工文字；最后运行：

```powershell
.\.venv\Scripts\research-os.exe manuscript-audit --project <slug> --draft projects/<slug>/writing/<draft>.md --as-of YYYY-MM-DD --format markdown
```

- 退出码 `0` 表示结构与 provenance 门禁通过；退出码 `1` 表示发现问题；退出码 `2` 表示不安全或损坏输入。审计不能证明科学、统计或临床正确性。
- 不得把未核验事实写成论文陈述，禁止编造引用、结果、伦理审批、数据许可或临床结论。
- 不得运行训练；不得运行实验、微调、量化、强化学习或集群任务；不提供个人诊疗建议。
