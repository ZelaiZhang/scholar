# Research Methods Knowledge Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, deterministic, evidence-scoped research methods knowledge base with strict validation, search, project recommendations, guide integration, and a professionally curated v0.4 seed library.

**Architecture:** `knowledge.py` owns immutable catalog/card/profile models and validation; `knowledge_search.py` owns pure deterministic ranking; `knowledge_recommend.py` maps project profiles and guide stages to at most three references. The CLI only parses/prints, while `guidance.py` consumes recommendations without changing its single-next-action contract. YAML/Markdown files under `library/knowledge` remain the auditable source of truth.

**Tech Stack:** Python 3.11+, dataclasses, pathlib, PyYAML, argparse, pytest, Markdown/YAML assets.

---

## File map

- Create `src/research_os/knowledge.py`: controlled vocabularies, strict schema loaders, card locator checks, profile loader, KB doctor report.
- Create `src/research_os/knowledge_search.py`: tokenization, aliases, filters, stable scoring, text/JSON result projection.
- Create `src/research_os/knowledge_recommend.py`: project-stage recommendation selection and explanations.
- Modify `src/research_os/cli.py`: `kb doctor`, `kb search`, and `kb recommend` parsers and handlers.
- Modify `src/research_os/guidance.py`: optional method-reference block while preserving exactly one `NextAction`.
- Modify `src/research_os/doctor.py`: report knowledge health without breaking legacy workspaces that have no KB.
- Create `library/knowledge/**`: catalog, aliases, cards, maps, playbooks, reporting applicability matrix, and seed manifest.
- Create `tests/test_knowledge.py`, `tests/test_knowledge_search.py`, `tests/test_knowledge_recommend.py`: unit and integration coverage.
- Modify `tests/test_cli.py`, `tests/test_guidance.py`, `tests/test_doctor.py`, `tests/installed_wheel_smoke.py`: CLI and installed journey coverage.
- Modify `README.md`, `docs/DEVELOPER-HANDOFF.md`, `pyproject.toml`: user/developer docs and v0.4 version.

### Task 1: Strict catalog, card, and profile models

**Files:**
- Create: `src/research_os/knowledge.py`
- Test: `tests/test_knowledge.py`

- [ ] **Step 1: Write failing schema tests**

```python
def test_load_catalog_rejects_unknown_key_and_duplicate_canonical(tmp_path):
    root = make_knowledge_root(tmp_path)
    write_catalog(root, entries=[entry("src-a"), entry("src-b", canonical="doi:a")])
    with pytest.raises(ValueError, match="duplicate canonical"):
        load_catalog(tmp_path)

def test_fulltext_verified_requires_card_locator(tmp_path):
    root = make_knowledge_root(tmp_path)
    write_catalog(root, entries=[entry("src-a", fulltext="verified")])
    write_card(root, "src-a", locator="")
    with pytest.raises(ValueError, match="locator"):
        load_knowledge_base(tmp_path)
```

- [ ] **Step 2: Run tests and confirm missing module failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_knowledge.py -q`

Expected: collection fails because `research_os.knowledge` does not exist.

- [ ] **Step 3: Implement immutable models and strict loaders**

Implement these public interfaces with exact-key checks and type validation:

```python
@dataclass(frozen=True)
class VerificationScope:
    metadata: str
    abstract: str
    fulltext: str

@dataclass(frozen=True)
class CatalogEntry:
    source_id: str
    canonical: str
    title: str
    authors: tuple[str, ...]
    year: int
    source_type: str
    venue: str
    topics: tuple[str, ...]
    methods: tuple[str, ...]
    stages: tuple[str, ...]
    priority: str
    verification: VerificationScope
    reviewed_at: str
    status: str
    superseded_by: str
    access_url: str
    license: str
    notes: str

@dataclass(frozen=True)
class KnowledgeProfile:
    schema_version: int
    domains: tuple[str, ...]
    tracks: tuple[str, ...]
    study_type: str
    data_modalities: tuple[str, ...]
    reporting_context: tuple[str, ...]

def load_catalog(workspace: Path) -> tuple[CatalogEntry, ...]:
    root = resolve_knowledge_root(workspace)
    return parse_catalog(root / "catalog.yaml", workspace / "library" / "sources.jsonl")

def load_profile(path: Path) -> KnowledgeProfile:
    return parse_profile(yaml.safe_load(path.read_text(encoding="utf-8")))

def load_card(workspace: Path, source_id: str) -> KnowledgeCard:
    root = resolve_knowledge_root(workspace)
    return parse_card(root / "cards" / f"{source_id}.md", expected_source_id=source_id)
```

Validate controlled vocabularies, unique source/canonical values, catalog-to-registry consistency, fulltext locator requirements, supersession targets/cycles, ISO dates, containment, symlinks, junctions, and reparse points.

- [ ] **Step 4: Run focused tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_knowledge.py -q -W error`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/research_os/knowledge.py tests/test_knowledge.py
git commit -m "feat: validate research knowledge assets"
```

### Task 2: Deterministic search and filtering

**Files:**
- Create: `src/research_os/knowledge_search.py`
- Test: `tests/test_knowledge_search.py`

- [ ] **Step 1: Write ranking/filter tests**

```python
def test_search_uses_documented_weights_and_stable_ties(kb):
    results = search_knowledge(kb, "calibration", limit=10)
    assert [item.entry.source_id for item in results] == ["src-title", "src-alias", "src-body"]

def test_search_excludes_retracted_and_superseded_by_default(kb):
    assert search_knowledge(kb, "diagnosis", limit=10) == ()
```

- [ ] **Step 2: Run tests and confirm missing module failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_knowledge_search.py -q`

- [ ] **Step 3: Implement pure search functions**

```python
@dataclass(frozen=True)
class SearchFilters:
    topic: str = ""
    method: str = ""
    stage: str = ""
    priority: str = ""
    verified_scope: str = ""
    include_history: bool = False

@dataclass(frozen=True)
class SearchResult:
    entry: CatalogEntry
    score: int
    matched_fields: tuple[str, ...]

def search_knowledge(
    kb: KnowledgeBase,
    query: str,
    *,
    filters: SearchFilters = SearchFilters(),
    limit: int = 10,
) -> tuple[SearchResult, ...]:
    filtered = apply_filters(kb.entries, filters)
    ranked = rank_entries(kb, filtered, query)
    return tuple(ranked[:limit])
```

Use case-folded Unicode word tokens and the exact 8/6/5/4/3/2/1 weights from the design. Sort ties by core/background/watch, fulltext verification, descending year, then source_id. Never use network calls, embeddings, random values, current time, or model inference.

- [ ] **Step 4: Run search tests and commit**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_knowledge_search.py -q -W error`

```powershell
git add src/research_os/knowledge_search.py tests/test_knowledge_search.py
git commit -m "feat: add deterministic knowledge search"
```

### Task 3: KB doctor and project recommendations

**Files:**
- Modify: `src/research_os/knowledge.py`
- Create: `src/research_os/knowledge_recommend.py`
- Test: `tests/test_knowledge.py`
- Test: `tests/test_knowledge_recommend.py`

- [ ] **Step 1: Write failing health/recommendation tests**

```python
def test_kb_doctor_warns_after_365_days_and_fails_stale_source(tmp_path):
    report = inspect_knowledge_base(tmp_path, today=date(2026, 8, 12))
    assert report.exit_code == 2
    assert any("hash drift" in issue.message for issue in report.issues)

def test_medical_text_project_gets_three_bounded_references(workspace):
    recommendations = recommend_for_project(workspace, "medical-reasoning", stage="experiment-design")
    assert len(recommendations) <= 3
    assert recommendations[0].entry.priority == "core"
    assert any(item.kind == "reporting-guideline" for item in recommendations)
```

- [ ] **Step 2: Run tests and confirm failures**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_knowledge.py tests/test_knowledge_recommend.py -q`

- [ ] **Step 3: Implement reports and recommendations**

```python
@dataclass(frozen=True)
class KnowledgeIssue:
    level: str
    message: str

@dataclass(frozen=True)
class KnowledgeHealthReport:
    issues: tuple[KnowledgeIssue, ...]
    entry_count: int
    card_count: int
    exit_code: int

@dataclass(frozen=True)
class KnowledgeRecommendation:
    kind: str
    title: str
    source_id: str
    reason: str
    verification_scope: str
    can_use_for: str
    cannot_use_for: str
    path: Path | None
```

`inspect_knowledge_base` must return deterministic PASS/WARN/FAIL findings for schema, registry, cards, locators, supersession, age, asset references, and path safety. `recommend_for_project` must require a strict profile when one exists, return a generic profile hint when absent, and never modify the project or imply evidence-link eligibility.

- [ ] **Step 4: Run tests and commit**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_knowledge.py tests/test_knowledge_recommend.py -q -W error`

```powershell
git add src/research_os/knowledge.py src/research_os/knowledge_recommend.py tests/test_knowledge.py tests/test_knowledge_recommend.py
git commit -m "feat: diagnose and recommend research methods"
```

### Task 4: Expose `kb` CLI

**Files:**
- Modify: `src/research_os/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI tests**

```python
def test_kb_search_json_is_deterministic(workspace, capsys):
    code = main(["kb", "search", "calibration", "--format", "json", "--workspace", str(workspace)])
    assert code == 0
    assert json.loads(capsys.readouterr().out)[0]["source_id"] == "src-calibration"

def test_kb_doctor_returns_two_for_corrupt_catalog(workspace):
    corrupt_catalog(workspace)
    assert main(["kb", "doctor", "--workspace", str(workspace)]) == 2
```

- [ ] **Step 2: Run focused tests and confirm parser failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_cli.py -q -k "kb_"`

- [ ] **Step 3: Add nested argparse commands**

Support these exact interfaces:

```text
research-os kb doctor [--workspace PATH]
research-os kb search QUERY [--topic VALUE] [--method VALUE] [--stage VALUE]
  [--priority core|background|watch] [--verified-scope metadata|abstract|fulltext]
  [--limit 1..50] [--format text|json] [--include-history] [--workspace PATH]
research-os kb recommend --project SLUG [--format text|json] [--workspace PATH]
```

Catalog/profile/input failures return 2; a valid empty search returns 0 with an explicit next-search hint. Text output must show score, verification scope, reason/boundary, and a `paper-intake` linkage hint rather than modifying `project.yaml`.

- [ ] **Step 4: Run CLI tests and commit**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_cli.py -q -W error`

```powershell
git add src/research_os/cli.py tests/test_cli.py
git commit -m "feat: expose knowledge base CLI"
```

### Task 5: Integrate recommendations into guide and doctor

**Files:**
- Modify: `src/research_os/guidance.py`
- Modify: `src/research_os/doctor.py`
- Modify: `tests/test_guidance.py`
- Modify: `tests/test_doctor.py`

- [ ] **Step 1: Write compatibility and integration tests**

```python
def test_guide_has_one_action_and_at_most_three_method_references(workspace):
    report = inspect_project(workspace, "medical-reasoning")
    assert report.next_action is not None
    assert len(report.method_references) <= 3

def test_legacy_workspace_without_knowledge_keeps_guide_behavior(workspace):
    report = inspect_project(workspace, "topic-a")
    assert report.method_references == ()
```

- [ ] **Step 2: Run tests and confirm missing field failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_guidance.py tests/test_doctor.py -q`

- [ ] **Step 3: Add optional method references**

Extend `GuidanceReport` with `method_references: tuple[KnowledgeRecommendation, ...] = ()`. A valid KB contributes at most three references. A corrupt KB contributes one non-actionable diagnostic note telling the user to run `kb doctor`; it must not replace or add a `NextAction`. `doctor` treats an absent `library/knowledge` as legacy-compatible and a present corrupt KB as FAIL.

- [ ] **Step 4: Run tests and commit**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_guidance.py tests/test_doctor.py -q -W error`

```powershell
git add src/research_os/guidance.py src/research_os/doctor.py tests/test_guidance.py tests/test_doctor.py
git commit -m "feat: surface method references in daily guidance"
```

### Task 6: Curate the v0.4 seed knowledge library

**Files:**
- Create: `library/knowledge/catalog.yaml`
- Create: `library/knowledge/aliases.yaml`
- Create: `library/knowledge/cards/*.md`
- Create: `library/knowledge/maps/*.md`
- Create: `library/knowledge/playbooks/*.md`
- Create: `library/knowledge/reporting-guidelines/applicability.yaml`
- Create: `library/knowledge/reporting-guidelines/medical-ai-reporting.md`
- Create: `library/knowledge/seeds/v0.4-sources.txt`
- Modify: `library/sources.jsonl`
- Test: `tests/test_knowledge.py`

- [ ] **Step 1: Add acceptance-count test**

```python
def test_bundled_v04_seed_library_meets_acceptance_floor(repo_root):
    kb = load_knowledge_base(repo_root)
    assert len(kb.entries) >= 24
    assert sum(e.verification.abstract == "verified" or e.verification.fulltext == "verified" for e in kb.entries) >= 16
    assert sum(e.verification.fulltext == "verified" for e in kb.entries) >= 8
    assert len(list((repo_root / "library/knowledge/maps").glob("*.md"))) == 5
    assert len(list((repo_root / "library/knowledge/playbooks").glob("*.md"))) == 4
```

- [ ] **Step 2: Register the seed manifest atomically**

Put at least 24 DOI/arXiv identifiers in `v0.4-sources.txt`, one per line. Run exactly one batch command without external authorization:

```powershell
.\.venv\Scripts\research-os.exe add-sources `
  ".\library\knowledge\seeds\v0.4-sources.txt" `
  --notes "Research OS v0.4 professional methods knowledge base" `
  --workspace .
```

Expected: every input returns a stable `source_id`; any bad line aborts the full batch.

- [ ] **Step 3: Add catalog and cards from verified primary sources**

Create at least 24 catalog entries and at least 16 cards. At least 8 cards must be based on full paper text or an official open webpage and contain concrete section/page/table locators. Abstract-only cards use `abstract` as locator and contain no invented internal details. Every reported fact carries a source ID and locator; `method_inference` is visibly separate. Do not reproduce guideline checklists or copyrighted long passages.

- [ ] **Step 4: Add maps, playbooks, and reporting applicability**

Create exactly the five maps and four playbooks named in the design. Every source reference uses a catalog source ID. The reporting matrix maps study/reporting contexts to current guidelines, status, replacement relationships, and official links. Human-authored operational advice must be labeled as such rather than attributed to a paper.

- [ ] **Step 5: Validate counts and commit**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_knowledge.py -q -W error`

```powershell
git add library/knowledge library/sources.jsonl tests/test_knowledge.py
git commit -m "data: seed the research methods knowledge base"
```

### Task 7: Installed journey, version, and documentation

**Files:**
- Modify: `tests/installed_wheel_smoke.py`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `docs/DEVELOPER-HANDOFF.md`

- [ ] **Step 1: Extend installed wheel smoke**

The installed journey must copy a minimal valid knowledge library into its temporary workspace, then assert `kb doctor`, text/JSON search, medical project recommendation, and `guide` method references all succeed without importing from the source checkout.

- [ ] **Step 2: Run wheel smoke before implementation and confirm failure**

Build/install the wheel into an isolated temporary virtual environment, change directory outside the repository, and run `tests/installed_wheel_smoke.py`. Expected before CLI packaging changes: `kb` is an invalid command.

- [ ] **Step 3: Update version and docs**

Set `pyproject.toml` version to `0.4.0`. Add a README quick-start for `kb doctor`, `kb search`, `kb recommend`, project profiles, verification scopes, and evidence-isolation boundaries. Update `docs/DEVELOPER-HANDOFF.md` so v0.4 is marked implemented and the module/CLI/test sections match reality.

- [ ] **Step 4: Run complete verification**

```powershell
$env:PYTHONUTF8="1"
.\.venv\Scripts\python.exe -m compileall -q src
.\.venv\Scripts\python.exe -m pytest -q -W error
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Expected: every command exits 0, all tests pass, and the wheel journey runs from outside the source tree.

- [ ] **Step 5: Commit**

```powershell
git add pyproject.toml README.md docs/DEVELOPER-HANDOFF.md tests/installed_wheel_smoke.py
git commit -m "docs: release the v0.4 knowledge workflow"
```

### Task 8: Final safety review

**Files:**
- Review all changes since this plan commit.

- [ ] **Step 1: Review for high-risk regressions**

Inspect catalog parsing, project evidence isolation, CLI writes, path containment, junction/symlink handling, time-of-check/time-of-use directory replacement, deterministic ranking, manual note protection, provider context construction, and guide's single-action invariant.

- [ ] **Step 2: Add regression tests for every confirmed issue**

Each confirmed Critical or Important issue gets a focused failing test, minimal fix, and focused plus full verification. Do not suppress or downgrade a finding to make the release pass.

- [ ] **Step 3: Re-run all release gates**

Run the complete Task 7 verification plus installed-wheel smoke and `git status --short`. Expected: zero failures, no diff-check output, and no uncommitted release files.

- [ ] **Step 4: Commit review fixes, if any**

```powershell
git add -A
git commit -m "fix: harden the research knowledge workflow"
```
