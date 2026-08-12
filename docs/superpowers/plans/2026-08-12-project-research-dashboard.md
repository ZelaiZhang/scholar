# Project Research Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, read-only `research-os dashboard` command that combines project workflow, evidence health, Idea state, methodology guidance, risk triggers, and at most three executable daily actions.

**Architecture:** Create `research_os.dashboard` as a pure aggregation boundary over existing project, guidance, evidence, cycle, source, and knowledge readers. Keep deterministic risk rules in `research_os.dashboard_risks`, and keep CLI parsing/rendering thin. The dashboard never writes workspace state or calls an external provider.

**Tech Stack:** Python 3.11+, frozen dataclasses, argparse, PyYAML-backed existing loaders, pytest, JSON/text rendering, hatchling wheel packaging.

---

## File Map

- Create `src/research_os/dashboard.py`: immutable snapshot models, stage normalization, project-scoped evidence/Idea aggregation, action selection, and the public builder.
- Create `src/research_os/dashboard_risks.py`: deterministic rules over structured dashboard facts; no filesystem access.
- Modify `src/research_os/cli.py`: `dashboard` parser, date validation, text/JSON rendering, and dispatch.
- Create `tests/test_dashboard.py`: unit and integration coverage for snapshot facts, risks, actions, isolation, and degraded states.
- Create `tests/test_dashboard_cli.py`: parser, text/JSON, determinism, errors, and read-only checks.
- Modify `tests/installed_wheel_smoke.py`: installed-wheel dashboard smoke and workspace byte-stability assertion.
- Modify `tests/test_workspace.py`: version and documentation assertions.
- Modify `README.md`: daily dashboard usage and safety boundary.
- Modify `docs/DEVELOPER-HANDOFF.md`: module/API/extension documentation.
- Modify `pyproject.toml` and `src/research_os/__init__.py`: release version bump.

### Task 1: Core Snapshot and Project-Scoped Evidence Health

**Files:**
- Create: `src/research_os/dashboard.py`
- Create: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing snapshot and evidence tests**

Add fixtures that create a project through `create_project`, register and link a local
source through `SourceRegistry`/`link_project_sources`, and write a valid ledger. Test
the public models and builder contract:

```python
def test_dashboard_reports_project_scoped_evidence(tmp_path: Path) -> None:
    workspace, slug, source_id = _ready_project(tmp_path)
    snapshot = build_project_dashboard(workspace, slug, as_of=date(2026, 8, 12))

    assert snapshot.schema_version == 1
    assert snapshot.as_of == "2026-08-12"
    assert snapshot.project.slug == slug
    assert snapshot.evidence.linked_sources == 1
    assert snapshot.evidence.verified_sources == 1
    assert snapshot.evidence.stale_or_unknown_source_ids == ()
    assert snapshot.evidence.claims == 1
    assert snapshot.evidence.support_links == 1
    assert snapshot.evidence.opposition_links == 0
    assert snapshot.evidence.claims_with_limitations == 1
    assert snapshot.evidence.validation_issues == ()
```

Create a second project with a second source and assert neither the second source nor
its ledger counts appear in the first project's snapshot. Add a stale linked source
case that retains the source ID in `stale_or_unknown_source_ids` and marks project
state blocked.

- [ ] **Step 2: Run tests and confirm the missing module failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -W error tests/test_dashboard.py -q
```

Expected: collection fails with `ModuleNotFoundError: research_os.dashboard`.

- [ ] **Step 3: Implement immutable models and evidence collection**

Create frozen models with explicit fields:

```python
@dataclass(frozen=True)
class ProjectStatus:
    title: str
    slug: str
    stage: str
    state: str
    blockers: tuple[str, ...]

@dataclass(frozen=True)
class EvidenceHealth:
    linked_sources: int
    verified_sources: int
    stale_or_unknown_source_ids: tuple[str, ...]
    claims: int
    support_links: int
    opposition_links: int
    conflicted_claims: int
    claims_with_limitations: int
    validation_issues: tuple[ValidationIssue, ...]

@dataclass(frozen=True)
class ProjectDashboard:
    schema_version: int
    as_of: str
    project: ProjectStatus
    evidence: EvidenceHealth
    idea: IdeaStatus
    recommendations: tuple[KnowledgeRecommendation, ...]
    risks: tuple[DashboardRisk, ...]
    actions: tuple[DashboardAction, ...]
```

`build_project_dashboard(workspace, slug, as_of)` must resolve the project through
`resolve_project_path`, load the manifest, derive the canonical stage from
`guide_project`, intersect verified registry IDs with `manifest.source_ids`, validate
the ledger against only that intersection, and count support/opposition lanes only
from well-formed list/dict structures. Keep tuple ordering deterministic.

- [ ] **Step 4: Run snapshot tests**

Run the Task 1 command. Expected: all Task 1 tests pass.

- [ ] **Step 5: Commit the core snapshot**

```powershell
git add src/research_os/dashboard.py tests/test_dashboard.py
git commit -m "feat: build project dashboard snapshot"
```

### Task 2: Idea State and Deterministic Risk Rules

**Files:**
- Create: `src/research_os/dashboard_risks.py`
- Modify: `src/research_os/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing Idea and risk tests**

Cover no-cycle, active-cycle, awaiting-human, and selected-Idea states. Use existing
cycle/archive fixture helpers rather than hand-building invalid internal objects.
Add pure risk tests such as:

```python
def test_risks_expose_observed_trigger_without_guessing() -> None:
    facts = RiskFacts(
        stale_source_ids=("src-stale",),
        ledger_issue_codes=("missing_locator",),
        project_state="blocked",
        project_blockers=("证据账本有 1 项校验问题",),
        knowledge_profile_present=False,
    )
    risks = evaluate_dashboard_risks(facts)

    assert [(risk.code, risk.state) for risk in risks] == [
        ("EVIDENCE_SOURCE_STALE", "observed"),
        ("EVIDENCE_LOCATOR_MISSING", "observed"),
    ]
    assert all(risk.trigger for risk in risks)
```

Assert that missing `knowledge-profile.yaml` produces an action/hint but does not
claim medical external-validation, leakage, or reference-standard defects. Assert
stable severity/code ordering.

- [ ] **Step 2: Run focused tests and observe missing risk API**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -W error tests/test_dashboard.py -q
```

Expected: new tests fail because `RiskFacts`, `DashboardRisk`, and Idea-state fields
do not exist.

- [ ] **Step 3: Implement Idea status**

Add this immutable contract:

```python
@dataclass(frozen=True)
class IdeaStatus:
    run_id: str
    cycle_state: str
    candidate_count: int
    selected_idea_ids: tuple[str, ...]
    human_decision_required: bool
    calls_used: int
    max_calls: int
```

Use `load_active_cycle`, `load_idea_archive`, and existing cycle validation. Candidate
count is limited to records whose `generated_by_run` matches the active run. A human
decision is required only for `awaiting_human_decision`. A selected Idea must match
the active run.

- [ ] **Step 4: Implement pure risk evaluation**

Create `RiskFacts`, `DashboardRisk`, and `evaluate_dashboard_risks`. Every risk has
`code`, `severity`, `state`, `message`, and `trigger`. Use an explicit rule table and
stable order. Initial rules cover stale sources, evidence validation/locator errors,
cycle corruption surfaced by the builder, and pending human approval. Emit
`MEDICAL_DESIGN_GATE_INCOMPLETE` only when `medical-ai` is present in the parsed
profile domains and the experiment-design stage is not complete. Emit
`MODEL_ADAPTATION_DESIGN_INCOMPLETE` only when parsed profile tracks include
`finetuning`, `quantization`, or `preference-optimization` and the experiment-design
stage is not complete. These two records use `missing_required`, name the exact
profile value and stage status in `trigger`, and do not claim a specific leakage,
metric, external-validation, or reference-standard defect.

- [ ] **Step 5: Run focused tests and commit**

Run the Task 2 command. Expected: all dashboard tests pass.

```powershell
git add src/research_os/dashboard.py src/research_os/dashboard_risks.py tests/test_dashboard.py
git commit -m "feat: add dashboard idea and risk status"
```

### Task 3: Method Guidance and Three-Action Prioritization

**Files:**
- Modify: `src/research_os/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing recommendation and action tests**

Test that recommendations equal the existing stage-aware
`recommend_for_project(..., stage=...)` contract and are capped at three. Test action
priority with a blocked project and with a healthy in-progress project:

```python
def test_actions_prioritize_repair_then_gate_then_methods(tmp_path: Path) -> None:
    workspace, slug = _project_with_stale_source_and_active_gate(tmp_path)
    snapshot = build_project_dashboard(workspace, slug, as_of=date(2026, 8, 12))

    assert len(snapshot.actions) <= 3
    assert snapshot.actions[0].category == "repair"
    assert snapshot.actions[1].category == "workflow"
    assert all(action.rationale and action.expected_artifact for action in snapshot.actions)
```

Assert commands are either exact commands already returned by `guide.next_action` or
fixed Research OS commands whose slug is validated by project resolution. Add a test
that an action command never includes ledger statements or source notes.

- [ ] **Step 2: Run focused tests and observe missing actions**

Run the dashboard test command. Expected: action/recommendation assertions fail.

- [ ] **Step 3: Implement deterministic action records**

Add:

```python
@dataclass(frozen=True)
class DashboardAction:
    code: str
    priority: int
    category: str
    rationale: str
    expected_artifact: str
    command: str
```

Generate candidates in fixed category order `repair`, `workflow`, `evidence`,
`methodology`; deduplicate by `code`; sort by `(priority, code)`; return the first
three. The workflow action wraps the canonical `GuideReport.next_action` without
changing its reason, target, command, or gate semantics. Repair actions derive only
from stable validation codes. Methodology actions may use `kb gaps` concepts but do
not mutate the knowledge base.

- [ ] **Step 4: Reuse stage-aware recommendations**

Call `recommend_for_project` once using the same controlled stage mapping as guide.
Return at most three recommendations. Preserve their `cannot_use_for` boundary in the
snapshot; never add their `source_id` to project evidence.

- [ ] **Step 5: Run tests and commit**

Run the dashboard test command. Expected: all dashboard tests pass.

```powershell
git add src/research_os/dashboard.py tests/test_dashboard.py
git commit -m "feat: prioritize daily research actions"
```

### Task 4: CLI, Stable Renderers, Determinism, and Read-Only Proof

**Files:**
- Modify: `src/research_os/cli.py`
- Create: `tests/test_dashboard_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Add parser and end-to-end tests:

```python
def test_dashboard_json_is_deterministic_and_read_only(tmp_path: Path, capsys) -> None:
    workspace, slug = _ready_project(tmp_path)
    before = _workspace_bytes(workspace)
    argv = [
        "dashboard", "--project", slug, "--workspace", str(workspace),
        "--as-of", "2026-08-12", "--format", "json",
    ]
    assert main(argv) == 0
    first = capsys.readouterr().out
    assert main(argv) == 0
    second = capsys.readouterr().out

    assert first == second
    assert json.loads(first)["schema_version"] == 1
    assert _workspace_bytes(workspace) == before
```

Test Chinese text headings, required `--project`, invalid `--as-of`, and JSON arrays in
stable order. Invalid date must return 2 and include `--as-of 必须是 YYYY-MM-DD 日期`.

- [ ] **Step 2: Run CLI tests and confirm parser failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -W error tests/test_dashboard_cli.py -q
```

Expected: parser rejects `dashboard` as an invalid choice.

- [ ] **Step 3: Add parser and dispatch**

Register:

```python
dashboard_parser = subparsers.add_parser(
    "dashboard", help="只读汇总课题状态、证据、风险和今日行动"
)
dashboard_parser.add_argument("--project", required=True, help="课题 slug")
dashboard_parser.add_argument("--as-of", default="", help="状态截止日期 YYYY-MM-DD")
dashboard_parser.add_argument("--format", choices=("text", "json"), default="text")
dashboard_parser.add_argument("--workspace", type=Path, default=Path.cwd())
```

Parse the date exactly as `kb gaps` does, call the builder, and select a renderer. Do
not create a cache or output file.

- [ ] **Step 4: Implement explicit JSON and Chinese text renderers**

Use explicit payload functions instead of recursive `asdict` for paths and future
schema control. JSON top-level order is `schema_version`, `as_of`, `project`,
`evidence`, `idea`, `recommendations`, `risks`, `actions`. Text sections are `课题状态`,
`证据健康度`, `Idea 与决策`, `方法学参考`, `风险雷达`, and `今日三个行动`.

- [ ] **Step 5: Run CLI and existing integration tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -W error tests/test_dashboard.py tests/test_dashboard_cli.py tests/test_cli.py tests/test_guidance.py tests/test_knowledge_recommend.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit CLI integration**

```powershell
git add src/research_os/cli.py tests/test_dashboard_cli.py
git commit -m "feat: expose project research dashboard"
```

### Task 5: Documentation, Version, and Installed Release Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/DEVELOPER-HANDOFF.md`
- Modify: `pyproject.toml`
- Modify: `src/research_os/__init__.py`
- Modify: `tests/test_workspace.py`
- Modify: `tests/installed_wheel_smoke.py`

- [ ] **Step 1: Write failing release assertions**

Change version assertions to `0.5.0`. Extend the installed smoke script to initialize
a project, run `dashboard` twice with fixed `--as-of`, compare exact JSON output, and
compare the workspace byte map before and after both invocations.

- [ ] **Step 2: Run release tests and observe old version/docs failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -W error tests/test_workspace.py -q
```

Expected: assertions fail while source/package metadata remain `0.4.1` and dashboard
documentation is absent.

- [ ] **Step 3: Update documentation and version metadata**

Document the command examples, six sections, deterministic `--as-of`, no-write/API
boundary, and extension points. Set both package version locations to `0.5.0` and keep
the handoff's module/command/test inventory current.

- [ ] **Step 4: Run the complete source verification suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -W error -q
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Expected: every command exits 0; pytest reports no failures or warnings; `pip check`
reports `No broken requirements found.`; `git diff --check` prints nothing.

- [ ] **Step 5: Run doctor and deterministic real-workspace checks**

Run:

```powershell
.\.venv\Scripts\research-os.exe doctor --workspace .
.\.venv\Scripts\research-os.exe kb doctor --workspace .
```

If the repository contains no project, create the smoke project only in a verified
temporary directory outside tracked workspace content. Run dashboard text and JSON
twice with `--as-of 2026-08-12` and compare exact bytes.

- [ ] **Step 6: Build and test an installed wheel outside the source tree**

Create a new verified fixed temporary directory under the workspace, build with:

```powershell
.\.venv\Scripts\python.exe -m pip wheel . --no-deps --no-build-isolation --wheel-dir .\.tmp-dashboard-wheel-smoke\wheelhouse
```

Install the resulting wheel into a new virtual environment, change to a sibling
directory that cannot import the source checkout, and run
`tests/installed_wheel_smoke.py`. Confirm installed metadata and
`research_os.__version__` both equal `0.5.0`. Remove only the exact temporary directory
after resolving and verifying it is the intended child of the workspace.

- [ ] **Step 7: Commit the release**

```powershell
git add README.md docs/DEVELOPER-HANDOFF.md pyproject.toml src/research_os/__init__.py tests/test_workspace.py tests/installed_wheel_smoke.py
git commit -m "release: document and verify Research OS v0.5.0"
```

### Task 6: Independent Review and Final Branch Verification

**Files:**
- Review only: all files changed since the design commit

- [ ] **Step 1: Request a read-only code review**

Use the requesting-code-review workflow with the design commit as base and current
HEAD as target. Require checks for project isolation, risk overclaiming, deterministic
output, command injection, read-only behavior, error boundaries, packaging, and test
quality. Fix every Critical or Important issue using systematic debugging and TDD.

- [ ] **Step 2: Re-run final verification after review fixes**

Repeat the full pytest, compileall, pip check, diff check, doctors, determinism, and
installed-wheel smoke commands from Task 5. Record exact outputs in the completion
summary.

- [ ] **Step 3: Confirm repository state**

Run:

```powershell
git status --short
git log -8 --oneline
```

Expected: no uncommitted files and a readable sequence of focused v0.5 commits.
