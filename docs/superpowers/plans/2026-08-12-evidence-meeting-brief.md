# Evidence-Bound Meeting Brief Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, evidence-bound `meeting-brief` command that produces a supervisor-ready Markdown or JSON decision memo without changing the workspace.

**Architecture:** A focused `meeting_brief.py` module captures one project-directory identity, composes the existing dashboard, then loads the ledger and active Idea archive under the same identity. It routes only validated claims into supported/conflicted/open sections, keeps invalid claims in an exclusion list, and renders stable discussion questions plus the existing safe actions. CLI code only parses dates and formats output.

**Tech Stack:** Python 3.11+, dataclasses, pathlib, existing strict YAML readers, argparse, pytest.

---

### Task 1: Preserve one project identity across dashboard composition

**Files:**
- Modify: `src/research_os/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing identity-reuse test**

```python
def test_dashboard_accepts_captured_project_identity(tmp_path: Path) -> None:
    project, _source_id = _write_ready_project(tmp_path)
    expected = (project.stat().st_dev, project.stat().st_ino)
    snapshot = build_project_dashboard(
        tmp_path,
        project.name,
        as_of=date(2026, 8, 12),
        expected_project_identity=expected,
    )
    assert snapshot.project.slug == project.name
```

- [ ] **Step 2: Run RED**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dashboard.py::test_dashboard_accepts_captured_project_identity -q`

Expected: FAIL because `build_project_dashboard` does not accept `expected_project_identity`.

- [ ] **Step 3: Implement the optional identity parameter**

```python
def build_project_dashboard(
    workspace: Path,
    slug: str,
    *,
    as_of: date,
    expected_project_identity: tuple[int, int] | None = None,
) -> ProjectDashboard:
    project = resolve_project_path(workspace.resolve(), slug, require_exists=True)
    project_identity = expected_project_identity or directory_identity(project)
    assert_directory_identity(project, project_identity, context="project")
    # Existing readers continue using project_identity.
```

- [ ] **Step 4: Run GREEN**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dashboard.py tests/test_dashboard_cli.py -q`

Expected: all dashboard tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/research_os/dashboard.py tests/test_dashboard.py
git commit -m "refactor: allow stable dashboard composition"
```

### Task 2: Route validated claims into a decision brief

**Files:**
- Create: `src/research_os/meeting_brief.py`
- Create: `tests/test_meeting_brief.py`

- [ ] **Step 1: Write the failing routing test**

```python
def test_meeting_brief_routes_claims_without_promoting_invalid_evidence(
    tmp_path: Path,
) -> None:
    project, source_id = write_meeting_project(tmp_path)
    write_claims(project, source_id)
    brief = build_meeting_brief(
        tmp_path, project.name, as_of=date(2026, 8, 12)
    )
    assert [item.claim_id for item in brief.supported_claims] == ["C001"]
    assert [item.claim_id for item in brief.conflicted_claims] == ["C002"]
    assert [item.claim_id for item in brief.open_claims] == ["C003"]
    assert {item.claim_id for item in brief.excluded_claims} == {"C004"}
    assert brief.supported_claims[0].support[0].locator == "p. 4, Table 2"
    assert brief.supported_claims[0].limitations
```

- [ ] **Step 2: Run RED**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_meeting_brief.py::test_meeting_brief_routes_claims_without_promoting_invalid_evidence -q`

Expected: collection fails because `research_os.meeting_brief` does not exist.

- [ ] **Step 3: Implement strict models and routing**

```python
@dataclass(frozen=True)
class EvidenceReference:
    source_id: str
    locator: str

@dataclass(frozen=True)
class BriefClaim:
    claim_id: str
    statement: str
    claim_type: str
    status: str
    confidence: str
    support: tuple[EvidenceReference, ...]
    opposition: tuple[EvidenceReference, ...]
    limitations: str
```

`build_meeting_brief` captures the project identity before calling `build_project_dashboard`, passes it into manifest and ledger readers, excludes every claim whose ID appears in a `ValidationIssue`, routes `conflicted` first, then `verified`, then `unverified/partially_verified`, and asserts the project identity before returning.

- [ ] **Step 4: Run GREEN**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_meeting_brief.py::test_meeting_brief_routes_claims_without_promoting_invalid_evidence -q`

Expected: PASS.

- [ ] **Step 5: Add the replacement regression**

```python
def test_meeting_brief_rejects_project_replacement_after_dashboard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Wrap dashboard construction, then replace the same-name project directory.
    # The following manifest/ledger read must raise OSError under the old identity.
```

Run: `./.venv/Scripts/python.exe -m pytest tests/test_meeting_brief.py -q`

Expected: all meeting-brief tests pass.

- [ ] **Step 6: Commit**

```powershell
git add src/research_os/meeting_brief.py tests/test_meeting_brief.py
git commit -m "feat: build evidence-bound meeting brief"
```

### Task 3: Add active Idea details and stable discussion questions

**Files:**
- Modify: `src/research_os/meeting_brief.py`
- Modify: `tests/test_meeting_brief.py`

- [ ] **Step 1: Write failing Idea test**

```python
def test_completed_idea_keeps_failure_boundary_and_human_reason(
    tmp_path: Path,
) -> None:
    project, source_id = write_meeting_project(tmp_path)
    run_id = advance_and_approve_one_idea(tmp_path, project, source_id)
    brief = build_meeting_brief(
        tmp_path, project.name, as_of=date(2026, 8, 12)
    )
    assert brief.ideas[0].run_id == run_id
    assert brief.ideas[0].failure_criterion == (
        "Unsupported conclusions do not decrease."
    )
    assert brief.ideas[0].decision_reason == (
        "Evidence and cost are acceptable."
    )
    assert any(
        item.code == "REVIEW_SELECTED_IDEA_BOUNDARY"
        for item in brief.questions
    )
```

- [ ] **Step 2: Run RED**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_meeting_brief.py::test_completed_idea_keeps_failure_boundary_and_human_reason -q`

Expected: FAIL because Idea details and discussion questions are absent.

- [ ] **Step 3: Implement Idea projection**

```python
@dataclass(frozen=True)
class BriefIdea:
    run_id: str
    idea_id: str
    title: str
    scientific_question: str
    hypothesis: str
    contribution: str
    evidence_source_ids: tuple[str, ...]
    novelty_status: str
    scores: tuple[tuple[str, int], ...]
    method_risks: tuple[str, ...]
    medical_safety_risks: tuple[str, ...]
    failure_criterion: str
    external_experiment: str
    status: str
    decision_reason: str
```

Load only records bound to the active `run_id`, reuse archive/cycle validators, exclude `rejected`, sort by `idea_id`, and cap at four.

- [ ] **Step 4: Implement question selection**

```python
@dataclass(frozen=True)
class DiscussionQuestion:
    code: str
    prompt: str
    rationale: str
```

Order questions as blocker, human/selected Idea decision, evidence uncertainty, then method fallback. Deduplicate by code and return at most three.

- [ ] **Step 5: Run GREEN and commit**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_meeting_brief.py tests/test_cycle.py tests/test_ideas.py -q`

Expected: all selected tests pass.

```powershell
git add src/research_os/meeting_brief.py tests/test_meeting_brief.py
git commit -m "feat: add Idea decision context to meeting brief"
```

### Task 4: Add Markdown/JSON CLI and read-only proof

**Files:**
- Modify: `src/research_os/meeting_brief.py`
- Modify: `src/research_os/cli.py`
- Create: `tests/test_meeting_brief_cli.py`

- [ ] **Step 1: Write failing CLI test**

```python
def test_meeting_brief_markdown_is_deterministic_and_read_only(
    tmp_path: Path, capsys
) -> None:
    project = write_cli_fixture(tmp_path)
    before = workspace_bytes(tmp_path)
    args = [
        "meeting-brief", "--project", project.name,
        "--as-of", "2026-08-12", "--workspace", str(tmp_path),
    ]
    assert main(args) == 0
    first = capsys.readouterr().out
    assert main(args) == 0
    second = capsys.readouterr().out
    assert first == second
    assert "## 已支持的结论" in first
    assert "source_id" in first and "locator" in first
    assert workspace_bytes(tmp_path) == before
```

- [ ] **Step 2: Run RED**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_meeting_brief_cli.py -q`

Expected: FAIL because the parser has no `meeting-brief` command.

- [ ] **Step 3: Implement renderer, payload and CLI branch**

Add `--project`, `--as-of`, `--format {markdown,json}` and `--workspace`. Add `meeting_brief_payload()` with explicit lists and `render_meeting_brief()` with escaped Markdown cells. Invalid dates raise `ValueError("--as-of 必须是 YYYY-MM-DD 日期")` and return code 2.

- [ ] **Step 4: Run GREEN and commit**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_meeting_brief_cli.py tests/test_cli.py -q`

Expected: all selected tests pass.

```powershell
git add src/research_os/meeting_brief.py src/research_os/cli.py tests/test_meeting_brief_cli.py
git commit -m "feat: expose evidence meeting brief CLI"
```

### Task 5: Prove the medical-reasoning journey and release v0.6.0

**Files:**
- Modify: `tests/installed_wheel_smoke.py`
- Modify: `tests/test_workspace.py`
- Modify: `README.md`
- Modify: `docs/DEVELOPER-HANDOFF.md`
- Modify: `pyproject.toml`
- Modify: `src/research_os/__init__.py`

- [ ] **Step 1: Extend installed-wheel smoke**

After the fixture completes its selected Idea, run `meeting-brief` twice with `--as-of 2026-08-12 --format json`. Assert byte-identical output, a supported claim with locator, the selected Idea failure criterion and decision reason, at most three questions/actions, and unchanged workspace bytes.

- [ ] **Step 2: Run the source-mode smoke**

Run: `./.venv/Scripts/python.exe tests/installed_wheel_smoke.py .tmp-meeting-smoke .`

Expected: the new journey fails until its output contract is fully implemented; after implementation it ends with `installed-wheel smoke passed`.

- [ ] **Step 3: Update release metadata and docs**

Bump `pyproject.toml` and `research_os.__version__` from `0.5.0` to `0.6.0`. Document the exact command, interpretation rules, evidence exclusions, clinical boundary, sample structure, module ownership, and verification commands. Update workspace tests to require v0.6.0 and the new CLI.

- [ ] **Step 4: Run complete verification**

```powershell
./.venv/Scripts/python.exe -m compileall -q src tests
./.venv/Scripts/python.exe -m pytest -q -W error
./.venv/Scripts/python.exe -m pip check
git diff --check
./.venv/Scripts/python.exe -m research_os doctor --workspace .
./.venv/Scripts/python.exe -m research_os kb doctor --workspace .
```

Expected: zero failures; repository doctor may retain only the documented no-project warning.

- [ ] **Step 5: Build and verify an isolated wheel**

Build `research_os-0.6.0-py3-none-any.whl`, install it with dependencies into a fresh venv outside the source import path, and run `tests/installed_wheel_smoke.py`. Expected final line: `installed-wheel smoke passed`.

- [ ] **Step 6: Commit**

```powershell
git add tests/installed_wheel_smoke.py tests/test_workspace.py README.md docs/DEVELOPER-HANDOFF.md pyproject.toml src/research_os/__init__.py
git commit -m "release: verify evidence meeting brief v0.6.0"
```
