# criterion-memory：从这里开始

<!-- research-os:generated:start -->
当前是候选课题 v0.1；已开始设计与写作，尚未批准最终选题，也没有研究实验结果。

1. 先看 [研究问题](00-research-brief.md) 和 [最接近工作/反对意见](03-literature-review.md)。
2. 看 [方法契约](notes/method-spec.md) 与 [完整实验协议](05-experiment-design.md)。
3. 阅读 [英文论文初稿](writing/manuscript-v0.1.md)；事实引用对应 [claim map](writing/claim-map.md) 与证据账本。
4. 按 [执行路线](notes/execution-roadmap.md) 在独立实验库推进，真实结果回来后再改结果章节。

```bash
.venv/bin/research-os validate-ledger projects/criterion-memory/02-evidence-ledger.yaml
.venv/bin/research-os dashboard --project criterion-memory --as-of 2026-09-30
.venv/bin/research-os manuscript-plan --project criterion-memory --as-of 2026-09-30
```

manuscript-plan 保留上游科学门禁，不能因为草稿文件存在就把课题标记为完成。本轮没有运行自动循环或代签 approve-idea。
后续编辑保留生成区块外的人工笔记；来源外发授权保持关闭。产物版本与哈希见 `artifacts/draft-provenance.json`。
<!-- research-os:generated:end -->
