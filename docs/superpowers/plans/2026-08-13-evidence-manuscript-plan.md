# Evidence-Bound Manuscript Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, read-only `research-os manuscript-plan` command that converts one validated project snapshot into section readiness, citation candidates, open facts, research statements, conflicts, exclusions, and exactly one safe next action.

**Architecture:** `guide_project` will expose stable internal stage codes and progress values; dashboard and meeting brief will carry these without changing their public JSON. A new focused `manuscript_plan.py` module will consume only one already-validated `MeetingBrief`, apply pure routing and readiness rules, and render explicit Markdown/JSON. The CLI remains a thin adapter and never writes a manuscript.

**Tech Stack:** Python 3.11+, dataclasses, argparse, PyYAML-backed existing evidence model, pytest, setuptools wheel smoke.

---

### Task 1: Add stable stage facts to the internal snapshot

**Files:**
- Modify: `src/research_os/guidance.py`
- Modify: `src/research_os/dashboard.py`
- Modify: `src/research_os/meeting_brief.py`
- Test: `tests/test_guidance.py`
- Test: `tests/test_dashboard.py`
- Test: `tests/test_meeting_brief.py`

- [ ] **Step 1: Write failing tests for stage codes and internal-only serialization**

Add assertions equivalent to:

```python
report = guide_project(tmp_path, "topic-a")
assert [stage.code for stage in report.stages] == [
    "problem_definition",
    "source_intake",
    "paper_deep_read",
    "evidence_synthesis",
    "idea_review",
    "experiment_design",
    "result_interpretation",
    "manuscript_writing",
    "mock_review",
]
assert all(stage.progress in {"blocked", "unstarted", "in_progress", "complete"} for stage in report.stages)

snapshot = build_project_dashboard(tmp_path, "topic-a", as_of=date(2026, 8, 13))
assert snapshot.stages == report.stages
assert "stages" not in _dashboard_payload(snapshot)

brief = build_meeting_brief(tmp_path, "topic-a", as_of=date(2026, 8, 13))
assert brief.stages == snapshot.stages
assert "stages" not in meeting_brief_payload(brief)
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_guidance.py tests/test_dashboard.py tests/test_meeting_brief.py
```

Expected: failures because `StageView.code`, `StageView.progress`, `ProjectDashboard.stages`, and `MeetingBrief.stages` do not exist.

- [ ] **Step 3: Extend `StageView` without changing rendered guide text**

Use the exact stable model:

```python
@dataclass(frozen=True)
class StageView:
    code: str
    name: str
    progress: str
    status: str
    detail: str
```

Populate all nine stages with the codes listed in Step 1. Convert existing derived statuses into `progress` before translating them through `_progress_status`. For source intake, evidence synthesis, Idea review, result interpretation, writing, and review, compute the same four progress codes rather than reverse-parsing Chinese display labels.

- [ ] **Step 4: Carry stages through dashboard and meeting brief internally**

Add:

```python
class ProjectDashboard:
    schema_version: int
    as_of: str
    project: ProjectStatus
    evidence: EvidenceHealth
    idea: IdeaStatus
    recommendations: tuple[KnowledgeRecommendation, ...]
    risks: tuple[DashboardRisk, ...]
    actions: tuple[DashboardAction, ...]
    stages: tuple[StageView, ...]

class MeetingBrief:
    schema_version: int
    as_of: str
    project: ProjectStatus
    supported_claims: tuple[BriefClaim, ...]
    conflicted_claims: tuple[BriefClaim, ...]
    open_claims: tuple[BriefClaim, ...]
    excluded_claims: tuple[ExcludedClaim, ...]
    idea_state: BriefIdeaState
    ideas: tuple[BriefIdea, ...]
    questions: tuple[DiscussionQuestion, ...]
    recommendations: tuple[KnowledgeRecommendation, ...]
    risks: tuple[DashboardRisk, ...]
    actions: tuple[DashboardAction, ...]
    stages: tuple[StageView, ...]
```

Set `stages=guide.stages` in `build_project_dashboard` and `stages=snapshot.stages` in `build_meeting_brief`. Do not add the field to `_dashboard_payload`, `meeting_brief_payload`, or existing Markdown renderers.

- [ ] **Step 5: Run focused tests and commit**

Run the Step 2 command; expect all selected tests to pass.

```powershell
git add src/research_os/guidance.py src/research_os/dashboard.py `
  src/research_os/meeting_brief.py tests/test_guidance.py `
  tests/test_dashboard.py tests/test_meeting_brief.py
git commit -m "refactor: expose stable research stage facts"
```

### Task 2: Build strict manuscript claim routing

**Files:**
- Create: `src/research_os/manuscript_plan.py`
- Create: `tests/test_manuscript_plan.py`

- [ ] **Step 1: Write a failing pure-routing test**

Construct a `MeetingBrief` fixture containing:

- one `fact/verified` supported claim;
- one `fact/partially_verified` open claim;
- one `inference/verified` supported claim;
- one `hypothesis/unverified` open claim;
- one conflicted claim;
- one excluded invalid claim.

Assert:

```python
plan = manuscript_plan_from_brief(brief)
assert [item.claim_id for item in plan.citation_candidates] == ["C001"]
assert [item.claim_id for item in plan.open_facts] == ["C002"]
assert [item.claim_id for item in plan.research_statements] == ["C003", "C004"]
assert [item.claim_id for item in plan.conflicts] == ["C005"]
assert [item.claim_id for item in plan.excluded_claims] == ["C006"]
assert plan.citation_candidates[0].support[0].locator == "p. 7, Results"
assert plan.citation_candidates[0].limitations == "Single public benchmark."
```

- [ ] **Step 2: Run the routing test and verify RED**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_manuscript_plan.py::test_routes_claims_without_status_promotion
```

Expected: import failure because `research_os.manuscript_plan` does not exist.

- [ ] **Step 3: Define focused immutable models**

Create `src/research_os/manuscript_plan.py` with:

```python
@dataclass(frozen=True)
class SectionReadiness:
    code: str
    title: str
    status: str
    reason_codes: tuple[str, ...]
    reasons: tuple[str, ...]
    claim_ids: tuple[str, ...]
    artifact_paths: tuple[str, ...]

@dataclass(frozen=True)
class ManuscriptAction:
    code: str
    reason: str
    target: str
    command: str

@dataclass(frozen=True)
class ManuscriptPlan:
    schema_version: int
    as_of: str
    project: ProjectStatus
    overall_status: str
    sections: tuple[SectionReadiness, ...]
    citation_candidates: tuple[BriefClaim, ...]
    open_facts: tuple[BriefClaim, ...]
    research_statements: tuple[BriefClaim, ...]
    conflicts: tuple[BriefClaim, ...]
    excluded_claims: tuple[ExcludedClaim, ...]
    next_action: ManuscriptAction
    boundaries: tuple[str, ...]
```

Implement `manuscript_plan_from_brief(brief)` with stable input order and no filesystem access. Route only `type=fact,status=verified` from `supported_claims` into citation candidates. Never promote inference, hypothesis, open, conflicted, or excluded claims.

- [ ] **Step 4: Run the routing test and commit**

Expected: PASS.

```powershell
git add src/research_os/manuscript_plan.py tests/test_manuscript_plan.py
git commit -m "feat: route manuscript evidence safely"
```

### Task 3: Implement eight section gates and one next action

**Files:**
- Modify: `src/research_os/manuscript_plan.py`
- Modify: `tests/test_manuscript_plan.py`

- [ ] **Step 1: Write failing parametrized section tests**

Cover at least these five snapshots:

```python
@pytest.mark.parametrize(
    ("stage_progress", "selected", "expected"),
    [
        ({"problem_definition": "complete", "evidence_synthesis": "complete"}, False,
         {"introduction": "ready", "methods": "blocked", "results": "blocked"}),
        ({"problem_definition": "complete", "evidence_synthesis": "complete",
          "idea_review": "complete"}, True,
         {"methods": "partial", "abstract": "partial"}),
        ({"experiment_design": "complete", "result_interpretation": "unstarted"}, True,
         {"methods": "ready", "experiments": "partial", "results": "blocked"}),
        ({"experiment_design": "complete", "result_interpretation": "in_progress"}, True,
         {"experiments": "ready", "results": "partial"}),
        ({"experiment_design": "complete", "result_interpretation": "complete"}, True,
         {"abstract": "ready", "results": "ready", "conclusion": "ready"}),
    ],
)
def test_section_readiness_is_deterministic(
    stage_progress: dict[str, str],
    selected: bool,
    expected: dict[str, str],
) -> None:
    brief = _brief_with_stage_progress(stage_progress, selected=selected)
    plan = manuscript_plan_from_brief(brief)
    actual = {section.code: section.status for section in plan.sections}
    assert {code: actual[code] for code in expected} == expected
```

Also assert that an active Idea with empty `medical_safety_risks` prevents `limitations_ethics` from becoming `ready`.

- [ ] **Step 2: Run section tests and verify RED**

Expected: the placeholder section tuple or missing gate function fails assertions.

- [ ] **Step 3: Implement pure gate helpers**

Use fixed order:

```python
SECTION_ORDER = (
    "abstract", "introduction", "related_work", "methods",
    "experiments", "results", "limitations_ethics", "conclusion",
)
```

Build a `progress_by_code` dictionary from `brief.stages`. Treat `result_interpretation == "in_progress"` as “aggregated result inputs exist but interpretation is incomplete”; `complete` means both inputs and interpretation exist. Apply the exact requirements in the design. `ready` means every requirement passes; `partial` means at least one prerequisite exists; otherwise `blocked`.

Set `overall_status` as:

```python
if not citation_candidates or any(brief.excluded_claims):
    overall = "blocked"
elif intro_ready and related_ready and bool(brief.idea_state.selected_idea_ids):
    overall = "ready_for_outline"
else:
    overall = "partial"
```

- [ ] **Step 4: Write failing next-action tests**

Assert exactly one action and this priority:

```python
assert plan.next_action.code in {
    "REPAIR_EVIDENCE", "ADVANCE_UPSTREAM_GATE", "DRAFT_EVIDENCE_OUTLINE"
}
assert "claim statement from fixture" not in plan.next_action.command
assert plan.next_action.command == (
    "$manuscript-assistant 基于 topic-a 的 manuscript-plan 和核验证据账本"
    "创建论文大纲，不补写缺失引用或结果"
)
```

When exclusions exist, emit `REPAIR_EVIDENCE`. Before all upstream gates pass, convert `brief.actions[0]` into `ADVANCE_UPSTREAM_GATE`. Only when result interpretation is complete emit `DRAFT_EVIDENCE_OUTLINE` from the fixed slug template.

- [ ] **Step 5: Run manuscript-plan tests and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q tests/test_manuscript_plan.py
git add src/research_os/manuscript_plan.py tests/test_manuscript_plan.py
git commit -m "feat: assess manuscript section readiness"
```

### Task 4: Add explicit Markdown/JSON and CLI

**Files:**
- Modify: `src/research_os/manuscript_plan.py`
- Modify: `src/research_os/cli.py`
- Create: `tests/test_manuscript_plan_cli.py`

- [ ] **Step 1: Write failing renderer and payload tests**

Assert JSON schema and absence of internals:

```python
payload = manuscript_plan_payload(plan)
assert payload["schema_version"] == 1
assert list(item["code"] for item in payload["sections"]) == list(SECTION_ORDER)
assert "artifact_identity" not in json.dumps(payload)
assert "snapshot_token" not in json.dumps(payload)
assert len(payload["next_actions"]) == 1
```

Assert Markdown includes the eight-section table, locator, limitations, open facts, research statements, conflicts, exclusions, one next action, and safety boundaries.

- [ ] **Step 2: Run renderer tests and verify RED**

Expected: missing `manuscript_plan_payload` and `render_manuscript_plan`.

- [ ] **Step 3: Implement explicit serializers**

Implement:

```python
def manuscript_plan_payload(plan: ManuscriptPlan) -> dict[str, object]:
    return {
        "schema_version": plan.schema_version,
        "as_of": plan.as_of,
        "project": {
            "title": plan.project.title,
            "slug": plan.project.slug,
            "stage": plan.project.stage,
            "state": plan.project.state,
            "blockers": list(plan.project.blockers),
        },
        "overall_status": plan.overall_status,
        "sections": [_section_payload(item) for item in plan.sections],
        "citation_candidates": [_claim_payload(item) for item in plan.citation_candidates],
        "open_facts": [_claim_payload(item) for item in plan.open_facts],
        "research_statements": [_claim_payload(item) for item in plan.research_statements],
        "conflicts": [_claim_payload(item) for item in plan.conflicts],
        "excluded_claims": [_excluded_payload(item) for item in plan.excluded_claims],
        "next_actions": [{
            "code": plan.next_action.code,
            "reason": plan.next_action.reason,
            "target": plan.next_action.target,
            "command": plan.next_action.command,
        }],
        "boundaries": list(plan.boundaries),
    }

def render_manuscript_plan(plan: ManuscriptPlan) -> str:
    lines = _render_header(plan)
    lines.extend(_render_sections(plan.sections))
    lines.extend(_render_claim_group("事实性写作候选", plan.citation_candidates))
    lines.extend(_render_claim_group("待补证事实", plan.open_facts))
    lines.extend(_render_claim_group("推断与假设", plan.research_statements))
    lines.extend(_render_claim_group("冲突证据", plan.conflicts))
    lines.extend(_render_excluded(plan.excluded_claims))
    lines.extend(_render_action(plan.next_action))
    lines.extend(_render_boundaries(plan.boundaries))
    return "\n".join(lines).rstrip() + "\n"

def build_manuscript_plan(workspace: Path, slug: str, *, as_of: date) -> ManuscriptPlan:
    return manuscript_plan_from_brief(
        build_meeting_brief(workspace, slug, as_of=as_of)
    )
```

Do not use `asdict(plan)` for the public payload. Serialize every public field explicitly so future internal snapshot fields cannot leak.

- [ ] **Step 4: Write failing CLI tests**

Test parser errors and the real command:

```python
code = main([
    "manuscript-plan", "--project", "topic-a", "--as-of", "2026-08-13",
    "--format", "json", "--workspace", str(tmp_path),
])
assert code == 0
payload = json.loads(capsys.readouterr().out)
assert payload["project"]["slug"] == "topic-a"
assert len(payload["sections"]) == 8
assert len(payload["next_actions"]) == 1
assert workspace_bytes(tmp_path) == before
```

Invalid dates and broken project evidence must return exit code 2 through the existing `main` error boundary.

- [ ] **Step 5: Add the CLI adapter**

Add parser:

```python
manuscript_parser = subparsers.add_parser(
    "manuscript-plan", help="生成证据绑定的论文写作就绪计划"
)
manuscript_parser.add_argument("--project", required=True, help="课题 slug")
manuscript_parser.add_argument("--as-of", default="", help="截止日期 YYYY-MM-DD")
manuscript_parser.add_argument(
    "--format", choices=("markdown", "json"), default="markdown"
)
manuscript_parser.add_argument("--workspace", type=Path, default=Path.cwd())
```

Parse `as_of` exactly like `meeting-brief`, call `build_manuscript_plan`, and print the selected explicit renderer.

- [ ] **Step 6: Run focused CLI tests and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_manuscript_plan.py tests/test_manuscript_plan_cli.py
git add src/research_os/manuscript_plan.py src/research_os/cli.py `
  tests/test_manuscript_plan.py tests/test_manuscript_plan_cli.py
git commit -m "feat: expose evidence manuscript plan CLI"
```

### Task 5: Documentation, version, and installed-wheel journey

**Files:**
- Modify: `README.md`
- Modify: `docs/DEVELOPER-HANDOFF.md`
- Modify: `pyproject.toml`
- Modify: `src/research_os/__init__.py`
- Modify: `tests/installed_wheel_smoke.py`

- [ ] **Step 1: Extend installed-wheel smoke before changing version**

After the existing completed-cycle meeting brief assertions, add:

```python
manuscript_args = [
    "manuscript-plan", "--project", "wheel-topic", "--as-of", "2026-08-13",
    "--format", "json", "--workspace", str(workspace),
]
before = workspace_bytes(workspace)
code, first_plan = run_cli(manuscript_args)
assert code == 0, first_plan
code, second_plan = run_cli(manuscript_args)
assert code == 0 and second_plan == first_plan
payload = json.loads(first_plan)
assert payload["overall_status"] == "ready_for_outline"
assert payload["citation_candidates"][0]["claim_id"] == "C001"
assert payload["sections"][0]["code"] == "abstract"
assert len(payload["next_actions"]) == 1
assert workspace_bytes(workspace) == before
```

- [ ] **Step 2: Update version and documentation**

Bump both package version sources from `0.6.0` to `0.7.0`. Add README quick-start, output contract, evidence boundaries, and a concrete Markdown example. Update developer handoff with module ownership, schema, tests, new design/plan links, and exact verification commands.

- [ ] **Step 3: Run source-tree verification**

```powershell
$env:PYTHONUTF8='1'
& '.\.venv\Scripts\python.exe' -m compileall -q src
& '.\.venv\Scripts\python.exe' -m pytest -p no:cacheprovider -W error -q
& '.\.venv\Scripts\python.exe' -m pip check
& '.\.venv\Scripts\python.exe' -m research_os doctor --workspace .
& '.\.venv\Scripts\python.exe' -m research_os kb doctor --workspace .
git diff --check
```

Expected: all commands succeed; doctor may retain only the documented warning that the repository root has no real project.

- [ ] **Step 4: Build and verify the wheel outside the repository**

Create new validated temporary directories, build `research_os-0.7.0-py3-none-any.whl`, install with `--target`, then execute `tests/installed_wheel_smoke.py` from the wheel directory with only the installed target on `PYTHONPATH`. Record version, user-journey success, and SHA256.

- [ ] **Step 5: Commit the release integration**

```powershell
git add README.md docs/DEVELOPER-HANDOFF.md pyproject.toml `
  src/research_os/__init__.py tests/installed_wheel_smoke.py
git commit -m "release: verify manuscript planning v0.7.0"
```

### Task 6: Independent review and final handoff

**Files:**
- Review all changes since `3ef31da`

- [ ] **Step 1: Request an independent read-only review**

Ask the reviewer to reproduce:

- invalid/open/conflicted claim leakage attempts;
- inference/hypothesis promotion attempts;
- stage mismatch and missing result inputs;
- project, ledger, cycle, Idea archive, and stage-document replacement races;
- command injection through title, claim, limitations, or source notes;
- JSON internal-field leakage;
- read-only and determinism failures.

- [ ] **Step 2: Fix every Critical or Important with a new RED test**

For each valid finding, run the exact reproduction to RED, implement the smallest root-cause fix, rerun focused tests, and commit separately. Do not accept review feedback without reproducing it.

- [ ] **Step 3: Re-run all completion gates**

Repeat Task 5 Steps 3 and 4 on the final reviewed HEAD. Require a clean worktree and `git diff --check HEAD` success.

- [ ] **Step 4: Deliver the user-facing proof**

Report:

- what `manuscript-plan` does for real paper writing;
- one command to run it;
- a short excerpt showing section status, one locator-bound fact, one excluded/open item, and the unique next action;
- full test count, doctor status, wheel SHA256, independent review verdict;
- clickable README, developer handoff, design, plan, and core module paths;
- preserved branch name without merging, pushing, deleting, or executing experiments.
