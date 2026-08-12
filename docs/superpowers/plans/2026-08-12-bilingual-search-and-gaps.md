# Bilingual Knowledge Search and Gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Research OS 的本地知识库支持确定性中文检索，并提供把现有 17 张卡扩展到 100 张的只读维护队列。

**Architecture:** 在 `knowledge_search.py` 内集中处理 Unicode/CJK token，不改变既有权重和 schema；在 `knowledge_gaps.py` 中独立计算维护项，避免把维护策略塞入解析器或 CLI。CLI 只负责参数、序列化和渲染；知识目录仍是唯一真源，所有新能力默认只读。

**Tech Stack:** Python 3.11+、标准库 `unicodedata`/`datetime`、PyYAML、argparse、pytest。

---

### Task 1: Unicode and CJK tokenization

**Files:**
- Modify: `tests/test_knowledge_search.py`
- Modify: `src/research_os/knowledge_search.py`

- [ ] **Step 1: Write failing normalization and CJK tests**

Add tests proving that `诊断` matches a `诊断准确性` alias, `思维链` matches a longer Chinese alias, NFKC makes full-width Latin queries equivalent, and the existing English score order remains `[8, 6, 2, 1]`.

```python
def test_search_matches_shorter_cjk_query_inside_curated_alias():
    entry = _entry("src-0000000000000001", title="STARD-AI")
    kb = KnowledgeBase(
        root=Path("knowledge"),
        entries=(entry,),
        cards={},
        aliases={entry.source_id: ("诊断准确性报告",)},
    )
    result = search_knowledge(kb, "诊断", limit=10)
    assert result[0].matched_fields == ("alias",)

def test_search_normalizes_full_width_latin():
    entry = _entry("src-0000000000000001", title="QLoRA")
    kb = KnowledgeBase(root=Path("knowledge"), entries=(entry,), cards={}, aliases={})
    assert search_knowledge(kb, "ＱＬｏＲＡ", limit=10)[0].entry == entry
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_knowledge_search.py -q
```

Expected: new CJK substring and full-width tests fail because `_tokens` has no NFKC/CJK grams.

- [ ] **Step 3: Implement minimal deterministic tokenizer**

Use `unicodedata.normalize("NFKC", value).casefold()`. Extract Latin/numeric words and contiguous CJK runs. For a CJK run longer than one character, return the full run and overlapping bigrams; for a one-character run, return the character. Return a set so duplicate grams cannot inflate scores.

- [ ] **Step 4: Run search tests and commit**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_knowledge_search.py -q -W error
```

Expected: all search tests pass and old English scores are unchanged.

Commit:

```powershell
git add src/research_os/knowledge_search.py tests/test_knowledge_search.py
git commit -m "feat: support deterministic CJK knowledge search"
```

### Task 2: Curated bilingual aliases and real CLI regression

**Files:**
- Modify: `library/knowledge/aliases.yaml`
- Modify: `tests/test_knowledge_cli.py`

- [ ] **Step 1: Write failing bundled-library CLI tests**

Add a parameterized test against the repository knowledge base:

```python
@pytest.mark.parametrize(
    ("query", "expected_title"),
    [
        ("诊断准确性", "STARD-AI"),
        ("思维链", "Chain-of-Thought"),
        ("微调量化", "QLoRA"),
    ],
)
def test_bundled_kb_search_supports_chinese_queries(query, expected_title, capsys):
    code = main(["kb", "search", query, "--format", "json", "--workspace", str(ROOT)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert expected_title in payload[0]["title"]
    assert "alias" in payload[0]["matched_fields"]
```

- [ ] **Step 2: Run the three cases and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_knowledge_cli.py -q -k chinese
```

Expected: at least one result is empty or ranks the wrong source because Chinese aliases are absent.

- [ ] **Step 3: Add reviewed Chinese aliases for every seed entry**

Extend each `source_id` key in `aliases.yaml`; do not change catalog facts or card text. Include exact user vocabulary such as `医疗诊断`, `思维链`, `微调`, `量化`, `强化学习`, `偏好优化` and `AI科研自动化` only where semantically appropriate.

- [ ] **Step 4: Validate aliases and commit**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_knowledge.py tests/test_knowledge_search.py tests/test_knowledge_cli.py -q -W error
.\.venv\Scripts\python.exe -m research_os kb doctor --workspace .
```

Commit:

```powershell
git add library/knowledge/aliases.yaml tests/test_knowledge_cli.py
git commit -m "data: add curated Chinese research aliases"
```

### Task 3: Deterministic knowledge-maintenance queue

**Files:**
- Create: `src/research_os/knowledge_gaps.py`
- Create: `tests/test_knowledge_gaps.py`

- [ ] **Step 1: Write failing gap classification tests**

Define the wished-for API:

```python
gaps = find_knowledge_gaps(kb, as_of=date(2026, 8, 12))
assert [gap.kind for gap in gaps] == [
    "watch-review",
    "metadata-review",
    "missing-card",
    "abstract-review",
    "fulltext-upgrade",
    "stale-review",
]
assert all(gap.source_id.startswith("src-") for gap in gaps)
```

Add separate tests for topic/method/kind filters, stable tie order, no duplicate `(kind, source_id)`, `limit` range 1..100, and no filesystem mutation.

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_knowledge_gaps.py -q
```

Expected: import failure because `knowledge_gaps.py` does not exist.

- [ ] **Step 3: Implement the focused module**

Create frozen dataclasses:

```python
@dataclass(frozen=True)
class GapFilters:
    topic: str = ""
    method: str = ""
    kind: str = ""

@dataclass(frozen=True)
class KnowledgeGap:
    kind: str
    source_id: str
    title: str
    priority: int
    reason: str
    next_action: str
    access_url: str
```

Use fixed priority order: `watch-review`, `metadata-review`, `missing-card`, `abstract-review`, `fulltext-upgrade`, `stale-review`. Sort by priority, catalog priority (`core`, `background`, `watch`), oldest review date, then source ID. Generate multiple distinct actions for one source only when they require genuinely different work.

- [ ] **Step 4: Run focused tests and commit**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_knowledge_gaps.py -q -W error
```

Commit:

```powershell
git add src/research_os/knowledge_gaps.py tests/test_knowledge_gaps.py
git commit -m "feat: compute deterministic knowledge gaps"
```

### Task 4: Expose `kb gaps`

**Files:**
- Modify: `src/research_os/cli.py`
- Modify: `tests/test_knowledge_cli.py`

- [ ] **Step 1: Write failing parser, text, JSON, and error tests**

Require this interface:

```text
research-os kb gaps
  [--topic VALUE] [--method VALUE]
  [--kind watch-review|metadata-review|missing-card|abstract-review|fulltext-upgrade|stale-review]
  [--as-of YYYY-MM-DD] [--limit 1..100]
  [--format text|json] [--workspace PATH]
```

Assert JSON exposes `kind/source_id/title/priority/reason/next_action/access_url`; text starts with counts and contains actionable skill names. Invalid date/limit returns exit 2. The command must not change catalog, cards or project files.

- [ ] **Step 2: Run CLI gap tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_knowledge_cli.py -q -k gaps
```

Expected: argparse rejects `gaps` as an invalid `kb` subcommand.

- [ ] **Step 3: Add parser, payload and renderer**

Parse `--as-of` with `date.fromisoformat`; default to local `date.today()`. Call `load_knowledge_base` and `find_knowledge_gaps`; do not invoke network or write helpers. Empty results return exit 0 and say the selected maintenance scope has no open items.

- [ ] **Step 4: Run CLI tests and commit**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_knowledge_cli.py tests/test_knowledge_gaps.py -q -W error
```

Commit:

```powershell
git add src/research_os/cli.py tests/test_knowledge_cli.py
git commit -m "feat: expose knowledge maintenance queue"
```

### Task 5: Documentation, version and installed journey

**Files:**
- Modify: `README.md`
- Modify: `docs/DEVELOPER-HANDOFF.md`
- Modify: `pyproject.toml`
- Modify: `src/research_os/__init__.py`
- Modify: `tests/test_workspace.py`
- Modify: `tests/installed_wheel_smoke.py`

- [ ] **Step 1: Extend version and installed-wheel tests first**

Expect package and metadata version `0.4.1`. In the installed journey, run one Chinese JSON search and `kb gaps --format json --as-of 2026-08-12`; assert deterministic non-empty payloads and no project mutation.

- [ ] **Step 2: Run selected tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_workspace.py -q
```

Expected: version assertion fails while package remains `0.4.0`.

- [ ] **Step 3: Update version and usage documentation**

Document Chinese search examples, `kb gaps`, classification order, `--as-of`, read-only behavior and the separation between maintenance hints and project evidence. Update the developer handoff module/CLI/test counts.

- [ ] **Step 4: Run all release gates**

Run full pytest with warnings-as-errors, compileall, pip check, diff check, workspace doctor, KB doctor, repeated JSON determinism comparison, and the outside-source installed-wheel journey.

- [ ] **Step 5: Commit**

```powershell
git add README.md docs/DEVELOPER-HANDOFF.md pyproject.toml src/research_os/__init__.py tests/test_workspace.py tests/installed_wheel_smoke.py
git commit -m "release: document and verify Research OS v0.4.1"
```

### Task 6: Final review

**Files:**
- Review every commit after `57ae820`.

- [ ] **Step 1: Review correctness and safety**

Inspect CJK false positives, deterministic ordering, aliases schema, status/history leakage, date handling, path safety, read-only guarantees, project evidence isolation and installed packaging.

- [ ] **Step 2: Add a failing regression test for each confirmed Critical/Important issue**

Use RED-GREEN before any production fix. Do not downgrade findings to finish the release.

- [ ] **Step 3: Re-run all release gates and confirm a clean worktree**

Expected: all commands exit 0, fixed JSON is byte-identical across two runs, wheel journey passes outside the repository, and `git status --short` is empty.
