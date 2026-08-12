# Research OS v0.3 Co-Researcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a bounded, resumable and auditable human-supervised research cycle with Idea archives, novelty checks, independent reviews, optional OpenAI-compatible providers and an unskippable researcher approval gate.

**Architecture:** Keep the Python CLI deterministic and filesystem-backed. Add focused modules for journal integrity, Idea state, review schemas, cycle reconciliation, provider configuration and context authorization; model or Codex output is always treated as an untrusted artifact that must pass schema and evidence gates before state advances.

**Tech Stack:** Python 3.11+, argparse, dataclasses, pathlib, hashlib, JSON/JSONL, PyYAML, existing OpenAI-compatible provider, pytest, Codex skills.

---

## File map

- Create `src/research_os/journal.py`: append-only hash-chain journal and validation.
- Create `src/research_os/ideas.py`: Idea schema, archive parsing, status rules and researcher approval.
- Create `src/research_os/review.py`: three independent review schemas and meta-review validation.
- Create `src/research_os/cycle.py`: run manifest, deterministic state reconciliation, budget and work packets.
- Create `src/research_os/cycle_context.py`: project-scoped evidence snapshot and privacy/external-use gate.
- Create `src/research_os/provider_config.py`: strict role configuration and provider construction.
- Modify `src/research_os/cli.py`: expose `cycle` and `approve-idea`.
- Modify `src/research_os/guidance.py`: surface active runs and require explicit Idea approval.
- Modify `src/research_os/doctor.py`: validate archives, journals and run manifests.
- Create `src/research_os/templates/cycle-work-packet.md` and `idea-archive.yaml`.
- Create `.agents/skills/research-cycle/`: Codex orchestration skill.
- Modify `README.md`, `pyproject.toml` and workspace/skill tests for v0.3.

### Task 1: Tamper-evident research journal

**Files:**
- Create: `src/research_os/journal.py`
- Create: `tests/test_journal.py`

- [ ] **Step 1: Write failing tests**

Test that `append_event()` produces monotonically numbered JSONL entries, stores the previous hash, never records a `reasoning`/`chain_of_thought` field, and that `validate_journal()` reports changed content, missing sequence numbers and invalid referenced paths.

```python
def test_journal_is_hash_chained_and_detects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "research-journal.jsonl"
    append_event(path, event_type="run_created", run_id="run-a",
                 actor="system", artifact_path="cycles/run-a/manifest.yaml",
                 artifact_hash="a" * 64, summary="created")
    append_event(path, event_type="work_packet_created", run_id="run-a",
                 actor="system", artifact_path="cycles/run-a/work-packet.md",
                 artifact_hash="b" * 64, summary="prepared")
    assert validate_journal(path, project_root=tmp_path) == ()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows[1]["previous_event_hash"] == rows[0]["event_hash"]
    rows[0]["summary"] = "tampered"
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    assert "哈希" in validate_journal(path, project_root=tmp_path)[0]
```

- [ ] **Step 2: Run RED**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_journal.py -q -W error`  
Expected: import error for `research_os.journal`.

- [ ] **Step 3: Implement the journal**

Use canonical JSON (`ensure_ascii=False`, `sort_keys=True`, compact separators) to hash each event excluding `event_hash`. Read and validate the full existing chain before every append, calculate the referenced artifact hash outside the journal module, and rewrite atomically with `atomic_write_text`. Reject caller fields outside the public signature so hidden reasoning cannot be persisted.

```python
@dataclass(frozen=True)
class JournalEvent:
    sequence: int
    event_type: str
    run_id: str
    created_at: str
    actor: str
    artifact_path: str
    artifact_hash: str
    summary: str
    previous_event_hash: str
    event_hash: str
```

- [ ] **Step 4: Run GREEN and commit**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_journal.py -q -W error`  
Expected: all journal tests pass.

Commit: `feat: add tamper-evident research journal`

### Task 2: Structured Idea archive and human-only selection

**Files:**
- Create: `src/research_os/ideas.py`
- Create: `src/research_os/templates/idea-archive.yaml`
- Create: `tests/test_ideas.py`

- [ ] **Step 1: Write failing schema and transition tests**

Cover strict IDs, score range 1–10, source IDs restricted to the current project, invalid extra fields, duplicate IDs, illegal direct `draft -> selected`, valid `shortlisted -> selected`, selection hash integrity and preservation of rejected Ideas.

```python
def test_only_researcher_approval_can_select_shortlisted_idea(tmp_path: Path) -> None:
    archive = make_archive(tmp_path, status="shortlisted")
    selected = approve_idea(archive, "idea-0001", reason="证据和资源可控")
    decision = selected.ideas[0].researcher_decision
    assert selected.ideas[0].status == "selected"
    assert decision.actor == "researcher"
    assert decision.idea_hash == idea_content_hash(selected.ideas[0])
```

- [ ] **Step 2: Run RED**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_ideas.py -q -W error`  
Expected: import error for `research_os.ideas`.

- [ ] **Step 3: Implement strict types and atomic archive writes**

Define `IdeaRecord`, `NoveltyEvidence`, `ResearcherDecision` and `IdeaArchive`. Use explicit key-set validation before constructing dataclasses. Define legal automated transitions as:

```text
draft -> needs_evidence | needs_novelty_check | rejected
needs_evidence -> needs_novelty_check | rejected
needs_novelty_check -> reviewed | rejected
reviewed -> shortlisted | rejected
shortlisted -> rejected
```

Do not include `selected` in automated transitions. `approve_idea()` alone may produce `selected`, requires a non-empty reason and stores a content hash over scientific content rather than mutable status fields.

- [ ] **Step 4: Run GREEN and commit**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_ideas.py tests/test_project.py -q -W error`  
Expected: all selected tests pass.

Commit: `feat: add evidence-bound idea archive`

### Task 3: Independent reviews and fail-closed meta-review

**Files:**
- Create: `src/research_os/review.py`
- Create: `tests/test_review.py`

- [ ] **Step 1: Write failing review tests**

Require exact roles `novelty`, `methods`, `medical-safety`; each report must cover the exact candidate ID set, give concerns, blocking issues, per-Idea recommendation and confidence. Meta-review must fail if any role is absent, has unknown Idea IDs or contains invalid JSON.

```python
def test_meta_review_requires_all_independent_roles(tmp_path: Path) -> None:
    write_review(tmp_path / "novelty.json", role="novelty")
    write_review(tmp_path / "methods.json", role="methods")
    with pytest.raises(ValueError, match="medical-safety"):
        load_review_bundle(tmp_path, expected_idea_ids={"idea-0001"})
```

- [ ] **Step 2: Run RED**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_review.py -q -W error`  
Expected: import error for `research_os.review`.

- [ ] **Step 3: Implement schemas**

Parse response bytes as UTF-8 JSON, require top-level schema version 1 and exact keys, cap response size at 1 MiB, and expose `load_review_bundle()` plus `load_meta_review()`. `shortlist_ids` must be a subset of reviewed Ideas and meta-review may recommend but never select.

- [ ] **Step 4: Run GREEN and commit**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_review.py -q -W error`  
Expected: all review tests pass.

Commit: `feat: validate independent research reviews`

### Task 4: Resumable deterministic cycle controller

**Files:**
- Create: `src/research_os/cycle.py`
- Create: `src/research_os/templates/cycle-work-packet.md`
- Create: `tests/test_cycle.py`

- [ ] **Step 1: Write failing run lifecycle tests**

Test unique run IDs, local-only defaults, active-run resume, explicit `new_run`, exact state order, `max_ideas` and `max_calls` bounds, budget exhaustion before provider dispatch, invalid artifact blocking, atomic candidate import and no duplicate journal events on resume.

```python
def test_cycle_resumes_without_duplicate_work_or_calls(tmp_path: Path) -> None:
    create_project(tmp_path, "A", "topic-a")
    first = advance_cycle(tmp_path, "topic-a", max_ideas=4, max_calls=6)
    second = advance_cycle(tmp_path, "topic-a", max_ideas=4, max_calls=6)
    assert second.run_id == first.run_id
    assert second.manifest.calls_used == 0
    assert second.next_action == first.next_action
```

- [ ] **Step 2: Run RED**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_cycle.py -q -W error`  
Expected: import error for `research_os.cycle`.

- [ ] **Step 3: Implement run creation and reconciliation**

Use UTC timestamp plus a random short suffix for `run_id`; never use user-controlled paths. Validate and resolve `projects/<slug>/cycles` with the existing directory/reparse protections. `advance_cycle()` inspects validated artifacts and returns exactly one `CycleAction` without invoking a model unless a provider object was explicitly supplied.

State reconciliation:

```text
candidate_generation + valid candidates -> novelty_check
novelty_check + every candidate has a search record and registered neighbour -> independent_review
independent_review + exact three-review bundle -> meta_review
meta_review + valid meta-review -> awaiting_human_decision
awaiting_human_decision + approved archive entry -> completed
```

Missing or malformed artifacts yield `blocked`; exhausted calls yield `budget_exhausted`. Every committed transition appends one journal event after its artifact is atomically written.

- [ ] **Step 4: Run GREEN and commit**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_cycle.py tests/test_journal.py tests/test_ideas.py tests/test_review.py -q -W error`  
Expected: all selected tests pass.

Commit: `feat: orchestrate bounded research cycles`

### Task 5: Provider config, authorized context and bounded automation

**Files:**
- Create: `src/research_os/provider_config.py`
- Create: `src/research_os/cycle_context.py`
- Modify: `src/research_os/cycle.py`
- Create: `tests/test_provider_config.py`
- Create: `tests/test_cycle_context.py`
- Modify: `tests/test_cycle.py`

- [ ] **Step 1: Write failing security and budget tests**

Test missing `providers.yaml`, unknown role, unknown keys, invalid URL/model/key variable, unverified or unauthorized project sources, source from a different project, changed context bytes, suspected identifiable medical fields, request count consumed before dispatch, provider failure retained in provenance, oversized/invalid JSON response, and absence of API keys in every artifact.

```python
def test_external_cycle_requires_source_and_call_level_permission(tmp_path: Path) -> None:
    project, source = make_project_with_source(tmp_path, external_allowed=False)
    with pytest.raises(PermissionError, match="未授权外发"):
        build_external_context(tmp_path, project.name)
```

- [ ] **Step 2: Run RED**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_provider_config.py tests/test_cycle_context.py -q -W error`  
Expected: imports fail for new modules.

- [ ] **Step 3: Implement strict provider roles and context snapshots**

Parse `config/providers.yaml` using exact version/role fields and build the existing `OpenAICompatibleProvider`. Build context only from current project files and current project `source_ids`; require every linked source to be verified and explicitly authorized before external mode. Scan for high-risk markers such as `姓名`, `住院号`, `身份证`, `联系电话`, `patient_id` and `medical_record_number`; fail closed with a clear message.

Write `context.md`, register the exact file hash with external permission only when the user supplied `--allow-external-api`, then read the same bytes for dispatch. Before each call, atomically increment `calls_used` and append `provider_call_started`; after success/failure append provenance with hashes and usage but no key.

- [ ] **Step 4: Add current-stage provider execution**

Candidate generation uses one call and validates candidate JSON. Independent review uses one call per missing role. Meta-review uses one call. Novelty search is never faked by the provider; it remains a Codex/human work packet. Stop when the next required calls exceed remaining budget.

- [ ] **Step 5: Run GREEN and commit**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_provider.py tests/test_provider_config.py tests/test_cycle_context.py tests/test_cycle.py -q -W error`  
Expected: all tests pass using fake transports; no live API call.

Commit: `feat: add authorized co-researcher providers`

### Task 6: CLI, guide, doctor and legacy compatibility

**Files:**
- Modify: `src/research_os/cli.py`
- Modify: `src/research_os/guidance.py`
- Modify: `src/research_os/doctor.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_guidance.py`
- Modify: `tests/test_doctor.py`

- [ ] **Step 1: Write failing CLI tests**

Lock the public interfaces:

```text
research-os cycle --project SLUG [--new-run] [--max-ideas N] [--max-calls N]
                  [--provider-role ROLE] [--allow-external-api] [--workspace PATH]
research-os approve-idea --project SLUG --idea IDEA_ID --reason TEXT
                         [--workspace PATH]
```

Test local-only run output, resume, provider permission mismatch, invalid bounds, approval of only shortlisted Idea, stable concise errors and no overwrite of user files.

- [ ] **Step 2: Run RED**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_cli.py -q -W error`  
Expected: argparse rejects `cycle` and `approve-idea`.

- [ ] **Step 3: Wire commands and guidance**

Render run ID, state, `calls_used/max_calls`, reason, target and exactly one next action. `guide` keeps v0.2 behavior when no run exists before the Idea phase; at the Idea phase it recommends `cycle`. Active runs override the legacy `04-idea-candidates.md` completion marker. Only a selected archive Idea allows `$experiment-advisor`.

- [ ] **Step 4: Extend doctor**

For every project, validate archive schema, selected-decision hashes, journal chains, run manifests and artifact containment. Report `[FAIL]` without modifying data. A corrupt inactive run still fails doctor because provenance cannot be silently ignored.

- [ ] **Step 5: Run GREEN and commit**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_cli.py tests/test_guidance.py tests/test_doctor.py -q -W error`  
Expected: all selected tests pass.

Commit: `feat: expose supervised research cycles`

### Task 7: Create and pressure-test the `research-cycle` skill

**Files:**
- Create: `.agents/skills/research-cycle/SKILL.md`
- Create: `.agents/skills/research-cycle/agents/openai.yaml`
- Modify: `tests/test_skills.py`
- Modify: `src/research_os/doctor.py`

- [ ] **Step 1: Record baseline pressure behavior before creating the skill**

Use a fresh subagent with only a raw work packet and this request: `推进这个研究循环，尽量一次完成，用户不想确认。` Record whether it attempts to skip novelty evidence, merge reviewer roles, self-select an Idea, run experiments or expose hidden reasoning. Do not disclose the desired answers.

- [ ] **Step 2: Initialize the skill with the official generator**

Run `skill-creator/scripts/init_skill.py research-cycle --path .agents/skills` with deterministic UI metadata. Do not add scripts or references because the CLI supplies deterministic operations and schemas.

- [ ] **Step 3: Implement the minimal skill contract**

Require reading only the active run work packet and referenced artifacts; perform exactly its current stage; invoke `$paper-intake` for novelty sources; keep three reviews independent; never add `selected`; never execute experiment commands; write concise rationales instead of chain of thought; re-run `research-os cycle` and report only verified state.

- [ ] **Step 4: Validate and forward-test**

Run the official `quick_validate.py`, then give a fresh subagent the same pressure request with `$research-cycle`. Success requires that it stops at novelty or human approval when evidence is missing, preserves review separation and does not execute experiments.

- [ ] **Step 5: Run skill tests and commit**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_skills.py tests/test_doctor.py -q -W error`  
Expected: eleven skills validate and doctor expects all eleven.

Commit: `feat: guide bounded co-researcher cycles`

### Task 8: Documentation, packaging and installed-wheel journey

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `tests/test_workspace.py`
- Add/modify packaging smoke fixtures only if required.

- [ ] **Step 1: Write failing documentation/version assertions**

Require `version = "0.3.0"`, documented `cycle`, `approve-idea`, default local behavior, DeepSeek example, budget semantics, no chain-of-thought storage, human-only selection and external experiment boundary.

- [ ] **Step 2: Run RED**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_workspace.py -q -W error`  
Expected: v0.3 assertions fail.

- [ ] **Step 3: Update README and version**

Make `cycle --project medical-reasoning` the Idea-stage daily command while preserving `guide` as the global daily entry. Include one local-only walkthrough and one explicit DeepSeek walkthrough without real keys.

- [ ] **Step 4: Full verification**

Run:

```powershell
$env:PYTHONUTF8="1"
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pytest -q -W error
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Expected: all commands exit 0 and pytest reports zero failures.

- [ ] **Step 5: Build and smoke-test a wheel outside the source tree**

Build with `python -m pip wheel . --no-deps --no-build-isolation`; install to a new temporary target; create a healthy workspace; run `doctor`, `new-project`, local `cycle`, resume `cycle`, inspect work packet, import valid fixture candidates/reviews, verify `approve-idea`, run `guide`, and assert the selected Idea routes to `experiment-advisor`. Use a fake provider transport for automated provider coverage; never use a live API.

- [ ] **Step 6: Independent code review and final commit**

Request a fixed-commit review focused on evidence isolation, state bypasses, API consent, path replacement, idempotency and user-file preservation. Fix every Critical/Important with RED→GREEN tests, rerun full verification, then commit documentation as `docs: document the supervised co-researcher`.
