# Evidence-Bound Manuscript Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, read-only `manuscript-audit` command that validates paragraph-level manuscript provenance against the current project's evidence, selected Idea, experiment design, and registered aggregate results.

**Architecture:** Extract strict result-manifest loading into a focused reusable module, parse annotated Markdown with a pure block parser, then evaluate parsed blocks against two stable v0.7 manuscript-plan snapshots. The CLI only parses arguments and renders an explicit schema; no untrusted manuscript text enters commands or issue messages.

**Tech Stack:** Python 3.11+, frozen dataclasses, `pathlib`, `hashlib`, PyYAML, argparse, pytest, existing Research OS stable-file identity primitives.

---

### Task 1: Extract reusable validated result inputs

**Files:**
- Create: `src/research_os/result_inputs.py`
- Modify: `src/research_os/guidance.py`
- Create: `tests/test_result_inputs.py`
- Modify: `tests/test_guidance.py`

- [ ] **Step 1: Write failing public-loader tests**

Create fixtures with one valid `results-manifest.yaml` and assert a wished-for API:

```python
from research_os.result_inputs import load_result_inputs

snapshot = load_result_inputs(project, project_identity)
assert snapshot.token
assert [(item.name, item.sha256) for item in snapshot.artifacts] == [
    ("aggregate-results.csv", digest)
]
assert snapshot.artifacts[0].source_repository == "public-experiment-repository"
assert snapshot.artifacts[0].generated_at == "2026-08-13T00:00:00Z"
```

Add separate tests for empty/missing manifest, unknown fields, duplicate paths, unsupported extension, unsafe relative path, invalid timestamp, empty result file, hash mismatch, symlink/reparse input, same-content manifest replacement, and same-content artifact replacement. Monkeypatch `read_stable_direct_text` only for the exact mid-read replacement tests; ordinary cases use real files.

- [ ] **Step 2: Run the new tests and verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -p no:cacheprovider -q `
  tests/test_result_inputs.py
```

Expected: collection fails because `research_os.result_inputs` does not exist.

- [ ] **Step 3: Implement the focused result-input module**

Define:

```python
@dataclass(frozen=True)
class ResultArtifact:
    name: str
    path: Path
    sha256: str
    source_repository: str
    generated_at: str
    identity: tuple[int, int]

@dataclass(frozen=True)
class ResultInputSnapshot:
    artifacts: tuple[ResultArtifact, ...]
    token: str
    directory_identity: tuple[int, int] | None
    manifest_identity: tuple[int, int] | None

def load_result_inputs(
    project_path: Path,
    expected_project_identity: tuple[int, int],
) -> ResultInputSnapshot:
    ...
```

Move the existing strict schema, extension, SHA256, provenance, before/read/after identity, and token logic from `guidance._result_inputs` without relaxing it. Reject an artifact whose decoded text is blank. A missing manifest returns an empty snapshot with token `"missing"`; a present empty `results` list is valid but contains no artifacts.

- [ ] **Step 4: Replace the guidance private loader**

Use:

```python
result_snapshot = load_result_inputs(project_path, project_identity)
result_inputs = tuple(item.path for item in result_snapshot.artifacts)
result_inputs_sha256 = result_snapshot.token
```

In `validate_stage_documents`, recompute `load_result_inputs(...).token` and compare it with `StageView.dependency_sha256`.

- [ ] **Step 5: Run focused and existing guidance tests**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -p no:cacheprovider -W error -q `
  tests/test_result_inputs.py tests/test_guidance.py `
  tests/test_dashboard.py tests/test_meeting_brief.py
```

Expected: all pass; no warnings.

- [ ] **Step 6: Commit the extraction**

```powershell
git add src/research_os/result_inputs.py src/research_os/guidance.py `
  tests/test_result_inputs.py tests/test_guidance.py
git commit -m "refactor: expose validated result inputs"
```

### Task 2: Parse deterministic manuscript annotations and blocks

**Files:**
- Create: `src/research_os/manuscript_markup.py`
- Create: `tests/test_manuscript_markup.py`

- [ ] **Step 1: Write annotation grammar tests**

Test the six exact forms from the design. The desired public types are:

```python
@dataclass(frozen=True)
class ManuscriptAnnotation:
    kind: str
    claim_ids: tuple[str, ...]
    idea_id: str
    artifact_names: tuple[str, ...]
    line: int

@dataclass(frozen=True)
class ManuscriptBlock:
    section: str
    block_index: int
    line: int
    annotation: ManuscriptAnnotation | None
```

Assertions must cover duplicate keys, unknown keys, duplicate values, invalid IDs, kind-specific missing/extra fields, trailing text, and two annotations for one block. Parser errors are data, not exceptions:

```python
parsed = parse_manuscript(text)
assert [issue.code for issue in parsed.syntax_issues] == ["INVALID_ANNOTATION"]
```

- [ ] **Step 2: Verify annotation tests RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -p no:cacheprovider -q `
  tests/test_manuscript_markup.py -k annotation
```

Expected: collection fails because the module is missing.

- [ ] **Step 3: Implement strict annotation parsing**

Use one anchored regular expression for the comment envelope and split the body only on `;`. Validate keys against the kind-specific schema:

```python
ANNOTATION_FIELDS = {
    "fact": frozenset({"kind", "claims"}),
    "inference": frozenset({"kind", "claims"}),
    "hypothesis": frozenset({"kind", "claims"}),
    "limitation": frozenset({"kind", "claims"}),
    "method": frozenset({"kind", "idea"}),
    "result": frozenset({"kind", "artifacts"}),
}
SAFE_VALUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
```

Do not preserve the manuscript text in `ManuscriptBlock` or syntax issues.

- [ ] **Step 4: Write block and section parser tests**

Cover paragraphs, consecutive list lines, block quotes, tables, blank-line boundaries, H2 section changes, exact section names, duplicate/missing sections, orphan/cross-heading annotations, fenced-code exclusion, H1/H3 behavior, Windows newlines, and deterministic line numbers.

The desired aggregate is:

```python
@dataclass(frozen=True)
class ParsedManuscript:
    blocks: tuple[ManuscriptBlock, ...]
    section_occurrences: tuple[tuple[str, int], ...]
    syntax_issues: tuple[MarkupIssue, ...]
```

- [ ] **Step 5: Verify parser tests RED, then implement minimal block parsing**

Run the block subset before implementation, confirm expected failures, then implement a line-state machine. It must never parse inside fenced code and must clear pending annotations at a heading.

- [ ] **Step 6: Run all markup tests and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -p no:cacheprovider -W error -q `
  tests/test_manuscript_markup.py
git add src/research_os/manuscript_markup.py tests/test_manuscript_markup.py
git commit -m "feat: parse evidence manuscript markup"
```

### Task 3: Evaluate provenance and section gates

**Files:**
- Create: `src/research_os/manuscript_audit.py`
- Create: `tests/test_manuscript_audit.py`

- [ ] **Step 1: Write failing fact and research-statement tests**

Construct `ManuscriptPlan` fixtures directly. Assert:

```python
audit = audit_parsed_manuscript(parsed, plan, result_snapshot)
assert audit.status == "pass"
assert audit.used_claim_ids == ("C001",)
```

Add one test each for unknown claim, verified inference used as fact, open fact, conflicted fact, excluded claim, inference/hypothesis type mismatch, invalid research statement, and missing limitation. Each must assert the exact stable issue code and no prose field in the issue.

- [ ] **Step 2: Run the audit tests and verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -p no:cacheprovider -q `
  tests/test_manuscript_audit.py -k 'claim or limitation'
```

Expected: collection fails because `research_os.manuscript_audit` is missing.

- [ ] **Step 3: Implement frozen public audit types and claim indexes**

Define:

```python
@dataclass(frozen=True)
class ManuscriptAuditIssue:
    code: str
    severity: str
    section: str
    block_index: int
    line: int
    claim_ids: tuple[str, ...]
    artifact_names: tuple[str, ...]
    message: str

@dataclass(frozen=True)
class SectionAudit:
    code: str
    title: str
    readiness: str
    block_count: int
    annotated_block_count: int
    issue_count: int

@dataclass(frozen=True)
class ManuscriptAudit:
    schema_version: int
    as_of: str
    project: ProjectStatus
    draft_path: str
    draft_sha256: str
    status: str
    block_counts: tuple[tuple[str, int], ...]
    sections: tuple[SectionAudit, ...]
    issues: tuple[ManuscriptAuditIssue, ...]
    used_claim_ids: tuple[str, ...]
    used_result_artifacts: tuple[str, ...]
    boundaries: tuple[str, ...]
```

Index only the already-routed groups from `ManuscriptPlan`. Do not reload or reinterpret raw ledger YAML.

- [ ] **Step 4: Write failing method, result, section, and structural tests**

Cover selected/non-selected Idea IDs, ready/partial/blocked section state, registered/unregistered artifacts, kind-to-section restrictions, unannotated blocks, missing/duplicate sections, invalid/orphan annotations, and stable issue sorting.

- [ ] **Step 5: Implement the gate evaluator**

Use fixed dictionaries for kind/section compatibility and message templates. `method` checks `plan.sections[methods] == ready` plus the selected IDs supplied from the stable meeting brief. `result` checks the ready Results section plus `ResultInputSnapshot.artifacts`. Sort issues by `(line, code, claim_ids, artifact_names)`.

Because `ManuscriptPlan` does not carry selected IDs, define an internal immutable `AuditContext(plan, selected_idea_ids, result_inputs)` used by the evaluator; the filesystem builder will populate it from one `MeetingBrief`/plan composition in Task 4.

- [ ] **Step 6: Run audit and upstream plan tests, then commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -p no:cacheprovider -W error -q `
  tests/test_manuscript_audit.py tests/test_manuscript_plan.py
git add src/research_os/manuscript_audit.py tests/test_manuscript_audit.py
git commit -m "feat: audit manuscript provenance gates"
```

### Task 4: Add safe filesystem builder, PHI stop, renderers, and CLI

**Files:**
- Modify: `src/research_os/manuscript_audit.py`
- Modify: `src/research_os/cli.py`
- Create: `tests/test_manuscript_audit_cli.py`

- [ ] **Step 1: Write failing safe-builder tests**

Create a real project fixture and assert `build_manuscript_audit(workspace, slug, draft, as_of=date(...))`. Test:

- a direct `.md` file below `writing/`;
- file outside `writing/`;
- nested file instead of direct child;
- wrong extension;
- writing/draft symlink and Windows reparse point where supported;
- draft larger than 4 MiB;
- invalid UTF-8;
- same-content replacement and mid-read replacement;
- research-state change between the two manuscript-plan snapshots;
- read-only workspace bytes.

Add a parameterized PHI test for all six markers. Assert a `PermissionError("PHI_SUSPECTED")` and assert the captured error contains neither the draft line nor a sample identifier value.

- [ ] **Step 2: Verify builder tests RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -p no:cacheprovider -q `
  tests/test_manuscript_audit_cli.py -k 'builder or phi or replacement'
```

Expected: `build_manuscript_audit` is absent.

- [ ] **Step 3: Implement stable draft and double-plan reads**

The builder must:

```python
project = resolve_project_path(workspace, slug, require_exists=True)
project_identity = directory_identity(project)
writing = project / "writing"
writing_identity = directory_identity(writing)
draft_identity_before = direct_file_identity(
    draft, expected_parent=writing, expected_parent_identity=writing_identity
)
first_brief = build_meeting_brief(workspace, slug, as_of=as_of)
first_plan = manuscript_plan_from_brief(first_brief)
text = read_stable_direct_text(
    draft,
    expected_parent=writing,
    expected_parent_identity=writing_identity,
    max_bytes=4 * 1024 * 1024,
)
second_brief = build_meeting_brief(workspace, slug, as_of=as_of)
second_plan = manuscript_plan_from_brief(second_brief)
```

Compare canonical `json.dumps(manuscript_plan_payload(...), sort_keys=True)` bytes. Recheck draft and directory identities and SHA after parsing. Load result inputs with the same project identity. If any identity or public plan payload changes, raise `OSError` before rendering.

- [ ] **Step 4: Write failing payload and Markdown tests**

Assert explicit JSON keys, eight section summaries, ordered issues, used provenance, boundary text, relative draft path, and absence of `identity`, `token`, `snapshot`, absolute workspace path, manuscript prose, and source notes. Assert Markdown has no prose reproduction and is deterministic.

- [ ] **Step 5: Implement explicit serializers and renderers**

Add `manuscript_audit_payload(audit)` and `render_manuscript_audit(audit)`. Do not use `asdict`. The report boundary list must include:

```text
ANNOTATION_NOT_ENTAILMENT
This audit is not clinical decision support.
Research OS did not rewrite the manuscript or execute experiments.
The researcher must verify semantic entailment and approve every statement.
```

- [ ] **Step 6: Add the CLI parser and dispatcher**

Add `manuscript-audit` beside `manuscript-plan`, parse `--as-of` with the same error contract, print JSON or Markdown, and return `1 if audit.issues else 0`. Existing `main` converts input exceptions to exit 2.

- [ ] **Step 7: Run CLI tests and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -p no:cacheprovider -W error -q `
  tests/test_manuscript_markup.py tests/test_manuscript_audit.py `
  tests/test_manuscript_audit_cli.py tests/test_cli.py
git add src/research_os/manuscript_audit.py src/research_os/cli.py `
  tests/test_manuscript_audit_cli.py
git commit -m "feat: expose read-only manuscript audit CLI"
```

### Task 5: Integrate the annotation contract into writing guidance

**Files:**
- Modify: `src/research_os/templates/manuscript-outline.md`
- Modify: `.agents/skills/manuscript-assistant/SKILL.md`
- Modify: `tests/test_skills.py`
- Modify: `tests/test_project.py`
- Modify: `README.md`
- Modify: `docs/DEVELOPER-HANDOFF.md`

- [ ] **Step 1: Write failing template and skill-contract tests**

Assert the installed project template contains all six exact annotation examples, warns that annotations do not prove entailment, and includes the final audit command. Assert the skill requires block annotations and a final `manuscript-audit` run but still forbids fabricated citations, PHI, overwrite, clinical claims, and experiment execution.

- [ ] **Step 2: Verify documentation-contract tests RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -p no:cacheprovider -q `
  tests/test_skills.py tests/test_project.py
```

Expected: failures for missing annotation/audit language.

- [ ] **Step 3: Update the template and skill**

Add concise annotated examples under each section. Keep generated prose empty. Include `<!-- research-os:kind=... -->` examples as comments only and direct users to remove unused examples rather than treating them as evidence.

- [ ] **Step 4: Document the user workflow and developer ownership**

README must show one annotated fact, method, result, and limitation block; exit codes; PHI stop; and the command. Developer handoff must document `manuscript_markup.py`, `manuscript_audit.py`, `result_inputs.py`, issue schema, tests, design/plan links, and exact verification commands.

- [ ] **Step 5: Run contract tests and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -p no:cacheprovider -W error -q `
  tests/test_skills.py tests/test_project.py tests/test_workspace.py
git add src/research_os/templates/manuscript-outline.md `
  .agents/skills/manuscript-assistant/SKILL.md tests/test_skills.py `
  tests/test_project.py README.md docs/DEVELOPER-HANDOFF.md
git commit -m "docs: teach evidence-bound manuscript markup"
```

### Task 6: Release v0.8.0 and independently review it

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/research_os/__init__.py`
- Modify: `tests/test_workspace.py`
- Modify: `tests/installed_wheel_smoke.py`
- Modify: `docs/DEVELOPER-HANDOFF.md`

- [ ] **Step 1: Extend installed-wheel smoke before bumping the version**

After the existing manuscript-plan journey, write one annotated draft with fact, method, result, and limitation blocks. Run the installed `manuscript-audit` twice with fixed `--as-of`, assert identical JSON, `status == "pass"`, zero issues, used claim/result IDs, no internal fields, and unchanged workspace bytes.

Then replace one fact annotation with an inference claim and assert exit 1 plus `CLAIM_KIND_MISMATCH`, without manuscript prose in output.

- [ ] **Step 2: Verify the wheel-smoke source journey RED**

Run `tests/installed_wheel_smoke.py` against a temporary source install or its focused helper. Expected: CLI rejects unknown `manuscript-audit` until Task 4 is present; after Task 4, the new journey passes while version remains 0.7.0.

- [ ] **Step 3: Bump both version sources to 0.8.0**

Change `pyproject.toml` and `src/research_os/__init__.py`, and update the exact version assertion in `tests/test_workspace.py`.

- [ ] **Step 4: Run every source-tree release gate**

```powershell
$env:PYTHONUTF8='1'
& '.\.venv\Scripts\python.exe' -m compileall -q src
& '.\.venv\Scripts\python.exe' -m pytest -p no:cacheprovider -W error -q
& '.\.venv\Scripts\python.exe' -m pip check
& '.\.venv\Scripts\python.exe' -m research_os doctor --workspace .
& '.\.venv\Scripts\python.exe' -m research_os kb doctor --workspace .
git diff --check
```

All must exit 0 except the already documented doctor warning that the repository root has no real project.

- [ ] **Step 5: Build and test an isolated installed wheel**

Build `research_os-0.8.0-py3-none-any.whl` into a new temporary directory, install with `--target`, run Python with `-P` and only the installed target on `PYTHONPATH`, execute `tests/installed_wheel_smoke.py`, and record the installed module path, version, and SHA256.

- [ ] **Step 6: Commit the release integration**

```powershell
git add pyproject.toml src/research_os/__init__.py tests/test_workspace.py `
  tests/installed_wheel_smoke.py docs/DEVELOPER-HANDOFF.md
git commit -m "release: verify manuscript audit v0.8.0"
```

- [ ] **Step 7: Request independent adversarial review**

Review the fixed range from this plan commit through the release commit. Require attempts for:

- unannotated prose and annotation crossing headings;
- open/conflicted/invalid/type-mismatched claim promotion;
- Idea/result gate bypass;
- PHI text disclosure;
- path escape and junction/reparse input;
- project, writing directory, draft, ledger, Idea, stage, result manifest, and result artifact replacement, including same-content replacement;
- JSON internal-field or manuscript-prose leakage;
- shell/Markdown injection through IDs, filenames, title, claim text, limitations, source notes, and draft prose;
- read-only and deterministic-output violations.

Fix every valid Critical or Important with a new RED test and a separate commit. Do not accept review findings without reproduction.

- [ ] **Step 8: Re-run final gates, update the final hash, and push**

Repeat Steps 4 and 5 on the reviewed HEAD, update the developer handoff with final test count, wheel hash, and review verdict, commit the documentation-only hash update, confirm a clean worktree, then push `codex/manuscript-audit-v08` to the configured GitHub remote without force-push.
