# Research OS Daily Driver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Research OS into a daily driver that diagnoses its workspace, links sources to projects, imports source lists atomically, and recommends one trustworthy next research action.

**Architecture:** Keep the deterministic Python CLI as the only executable layer. Extend `project.py` with human-readable project manifests, extend `sources.py` with preflighted batch transactions, and add focused `doctor.py` and `guidance.py` read-only services. The CLI only parses arguments and renders those services; no command executes experiments or calls an external model unless the existing explicit `model-call` gate is used.

**Tech Stack:** Python 3.11+, argparse, pathlib, dataclasses, PyYAML, pytest, setuptools package data.

---

## File map

- Modify `src/research_os/project.py`: project manifest load/write/link and new-project metadata.
- Create `src/research_os/templates/start-here.md`: short per-project onboarding page.
- Modify `src/research_os/sources.py`: manifest parsing and atomic `add_many` transaction.
- Create `src/research_os/doctor.py`: read-only workspace diagnostics.
- Create `src/research_os/guidance.py`: deterministic stage analysis and next-action selection.
- Modify `src/research_os/cli.py`: `doctor`, `guide`, `add-sources`, `--project`, and UTF-8 console entrypoint.
- Modify `README.md`: daily workflow and migration guidance.
- Modify `.agents/skills/paper-intake/SKILL.md`: always associate imported sources with a project when known.
- Modify `tests/test_project.py`, `tests/test_sources.py`, and `tests/test_cli.py`.
- Create `tests/test_doctor.py` and `tests/test_guidance.py`.
- Create `tests/fixtures/smoke-sources.txt`: stable public identifier for installed-wheel smoke tests.

### Task 1: Add project manifests and source associations

**Files:**
- Modify: `src/research_os/project.py`
- Create: `src/research_os/templates/start-here.md`
- Modify: `tests/test_project.py`

- [ ] **Step 1: Write failing project-manifest tests**

Add tests that express the public behavior:

```python
from research_os.project import load_project_manifest, link_project_sources


def test_create_project_writes_manifest_and_start_here(tmp_path: Path) -> None:
    path = create_project(tmp_path, "医疗推理", "medical-reasoning")

    manifest = load_project_manifest(path)
    assert manifest.schema_version == 1
    assert manifest.title == "医疗推理"
    assert manifest.slug == "medical-reasoning"
    assert manifest.source_ids == ()
    assert "research-os guide --project medical-reasoning" in (
        path / "START-HERE.md"
    ).read_text(encoding="utf-8")


def test_link_project_sources_is_ordered_and_idempotent(tmp_path: Path) -> None:
    path = create_project(tmp_path, "A", "topic-a")

    link_project_sources(tmp_path, "topic-a", ["src-b", "src-a", "src-b"])
    link_project_sources(tmp_path, "topic-a", ["src-a"])

    assert load_project_manifest(path).source_ids == ("src-b", "src-a")


def test_legacy_project_manifest_falls_back_to_brief_title(tmp_path: Path) -> None:
    project = tmp_path / "projects" / "legacy"
    project.mkdir(parents=True)
    (project / "00-research-brief.md").write_text(
        "# 旧课题\n", encoding="utf-8"
    )

    manifest = load_project_manifest(project, allow_legacy=True)

    assert manifest.title == "旧课题"
    assert manifest.slug == "legacy"
    assert manifest.source_ids == ()
    assert manifest.persisted is False
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
$env:PYTHONUTF8="1"
.\.venv\Scripts\python.exe -m pytest tests/test_project.py -q
```

Expected: collection fails because `load_project_manifest` and `link_project_sources` do not exist.

- [ ] **Step 3: Implement the manifest model and writes**

In `project.py`, add a frozen model and strict YAML functions:

```python
from dataclasses import dataclass
from datetime import datetime, timezone

import yaml


@dataclass(frozen=True)
class ProjectManifest:
    schema_version: int
    title: str
    slug: str
    created_at: str
    source_ids: tuple[str, ...]
    persisted: bool = True


def _manifest_path(project_path: Path) -> Path:
    return project_path / "project.yaml"


def write_project_manifest(project_path: Path, manifest: ProjectManifest) -> None:
    payload = {
        "schema_version": manifest.schema_version,
        "title": manifest.title,
        "slug": manifest.slug,
        "created_at": manifest.created_at,
        "source_ids": list(manifest.source_ids),
    }
    atomic_write_text(
        _manifest_path(project_path),
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
    )


def load_project_manifest(
    project_path: Path, *, allow_legacy: bool = False
) -> ProjectManifest:
    path = _manifest_path(project_path)
    if not path.exists():
        if not allow_legacy:
            raise FileNotFoundError(path)
        brief = project_path / "00-research-brief.md"
        first_heading = next(
            (
                line[2:].strip()
                for line in brief.read_text(encoding="utf-8").splitlines()
                if line.startswith("# ") and line[2:].strip()
            ),
            project_path.name,
        )
        return ProjectManifest(1, first_heading, project_path.name, "", (), False)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError(f"课题元数据格式无效: {path}")
    title = str(raw.get("title", "")).strip()
    slug = str(raw.get("slug", "")).strip()
    source_ids = raw.get("source_ids", [])
    if not title or not SLUG_PATTERN.fullmatch(slug) or not isinstance(source_ids, list):
        raise ValueError(f"课题元数据字段无效: {path}")
    clean_ids = tuple(str(item).strip() for item in source_ids)
    if any(not item.startswith("src-") for item in clean_ids):
        raise ValueError(f"课题 source_ids 无效: {path}")
    return ProjectManifest(
        1, title, slug, str(raw.get("created_at", "")), clean_ids, True
    )


def link_project_sources(workspace: Path, slug: str, source_ids: list[str]) -> None:
    project_path = workspace.resolve() / "projects" / slug
    if not project_path.is_dir():
        raise FileNotFoundError(f"课题不存在: {project_path}")
    manifest = load_project_manifest(project_path, allow_legacy=True)
    ordered = list(manifest.source_ids)
    ordered.extend(item for item in source_ids if item not in ordered)
    write_project_manifest(
        project_path,
        ProjectManifest(
            manifest.schema_version,
            manifest.title,
            manifest.slug,
            manifest.created_at or datetime.now(timezone.utc).isoformat(),
            tuple(ordered),
        ),
    )
```

Update `create_project` to write `project.yaml`, and add `"start-here.md": "START-HERE.md"` to `PROJECT_FILES`. Replace both `{{PROJECT_TITLE}}` and `{{PROJECT_SLUG}}` in template content.

Create `start-here.md` with complete copy:

```markdown
# {{PROJECT_TITLE}}：从这里开始

每天先运行：

```powershell
research-os guide --project {{PROJECT_SLUG}}
```

核心文件是 `00-research-brief.md`、`02-evidence-ledger.yaml` 和 `03-literature-review.md`。资料登记时传入 `--project {{PROJECT_SLUG}}`，避免和其他课题混淆。

只放公开资料、公开数据集说明和脱敏示例；禁止放入真实姓名、住院号、联系方式或其他可识别健康信息。
```

- [ ] **Step 4: Run project tests and full regression**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_project.py tests/test_workspace.py -q -W error
```

Expected: all selected tests pass with no warning.

- [ ] **Step 5: Commit the project-manifest slice**

```powershell
git add src/research_os/project.py src/research_os/templates/start-here.md tests/test_project.py
git commit -m "feat: track project metadata and source links"
```

### Task 2: Add atomic source-list intake

**Files:**
- Modify: `src/research_os/sources.py`
- Modify: `tests/test_sources.py`
- Create: `tests/fixtures/smoke-sources.txt`

- [ ] **Step 1: Write failing batch-intake tests**

```python
from research_os.sources import load_source_manifest


def test_source_manifest_supports_comments_and_relative_files(tmp_path: Path) -> None:
    paper = tmp_path / "paper.pdf"
    paper.write_bytes(b"public paper")
    manifest = tmp_path / "sources.txt"
    manifest.write_text(
        "# seed\n\n./paper.pdf\ndoi:10.1000/ABC\n", encoding="utf-8"
    )

    values = load_source_manifest(manifest)

    assert values == [paper.resolve().as_posix(), "doi:10.1000/ABC"]


def test_add_many_is_atomic_when_one_source_is_invalid(tmp_path: Path) -> None:
    registry_path = tmp_path / "library" / "sources.jsonl"
    registry = SourceRegistry(registry_path)
    registry.add("doi:10.1000/existing")
    before = registry_path.read_bytes()

    with pytest.raises(InvalidSourceError):
        registry.add_many(["doi:10.1000/good", "missing.pdf"])

    assert registry_path.read_bytes() == before


def test_add_many_reports_added_duplicate_and_authorization_upgrade(
    tmp_path: Path,
) -> None:
    registry = SourceRegistry(tmp_path / "library" / "sources.jsonl")
    registry.add("doi:10.1000/existing")

    result = registry.add_many(
        ["doi:10.1000/existing", "doi:10.1000/new", "doi:10.1000/new"],
        external_api_allowed=True,
    )

    assert (result.added, result.duplicates, result.authorizations_upgraded) == (1, 2, 1)
    assert len(registry.records()) == 2
```

- [ ] **Step 2: Run source tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_sources.py -q
```

Expected: failures report missing `load_source_manifest` and `add_many`.

- [ ] **Step 3: Implement preflighted batch registration**

Add the result type and parser:

```python
@dataclass(frozen=True)
class BatchAddResult:
    records: tuple[SourceRecord, ...]
    added: int
    duplicates: int
    authorizations_upgraded: int


def load_source_manifest(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(path)
    values: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        candidate = Path(value).expanduser()
        if not candidate.is_absolute() and not value.lower().startswith(
            ("doi:", "arxiv:", "http://", "https://")
        ):
            candidate = path.parent / candidate
            value = candidate.resolve().as_posix()
        try:
            normalize_source(value)
        except InvalidSourceError as exc:
            raise InvalidSourceError(f"{path}:{line_number}: {exc}") from exc
        values.append(value)
    if not values:
        raise InvalidSourceError(f"来源清单没有可导入条目: {path}")
    return values
```

Refactor `SourceRegistry.add` to call `add_many([value], ...)` and return the first record. Implement `add_many` by building every candidate before changing `records`; then merge candidates into an in-memory list and call `_write` once only when the list changed. Preserve the first record's `notes` and `imported_at`, and only replace `external_api_allowed=False` with `True` when explicitly requested.

Use this implementation (the preflight list comprehension is intentionally before `_read` mutation and `_write`):

```python
def _candidate_record(
    value: str, *, notes: str, external_api_allowed: bool
) -> SourceRecord:
    kind, canonical = normalize_source(value)
    content_hash = hash_file(Path(canonical)) if kind == "file" else None
    identity = content_hash if content_hash is not None else canonical
    return SourceRecord(
        source_id=make_source_id(kind, identity),
        kind=kind,
        canonical=canonical,
        imported_at=datetime.now(timezone.utc).isoformat(),
        content_hash=content_hash,
        notes=notes,
        external_api_allowed=external_api_allowed,
    )


def add_many(
    self,
    values: list[str],
    *,
    notes: str = "",
    external_api_allowed: bool = False,
) -> BatchAddResult:
    if not values:
        raise InvalidSourceError("批量来源不能为空")
    candidates = [
        _candidate_record(
            value,
            notes=notes,
            external_api_allowed=external_api_allowed,
        )
        for value in values
    ]
    records = self._read()
    indexes = {record.source_id: index for index, record in enumerate(records)}
    returned: list[SourceRecord] = []
    added = duplicates = upgraded = 0
    changed = False
    for candidate in candidates:
        index = indexes.get(candidate.source_id)
        if index is None:
            indexes[candidate.source_id] = len(records)
            records.append(candidate)
            returned.append(candidate)
            added += 1
            changed = True
            continue
        duplicates += 1
        existing = records[index]
        if external_api_allowed and not existing.external_api_allowed:
            existing = replace(existing, external_api_allowed=True)
            records[index] = existing
            upgraded += 1
            changed = True
        returned.append(existing)
    if changed:
        self._write(records)
    return BatchAddResult(tuple(returned), added, duplicates, upgraded)
```

- [ ] **Step 4: Run focused and full source tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_sources.py tests/test_provider.py -q -W error
```

Expected: all selected tests pass and the external authorization tests remain green.

- [ ] **Step 5: Commit atomic batch intake**

Create `tests/fixtures/smoke-sources.txt` with this exact UTF-8 content:

```text
doi:10.1000/smoke
```

```powershell
git add src/research_os/sources.py tests/test_sources.py tests/fixtures/smoke-sources.txt
git commit -m "feat: import source manifests atomically"
```

### Task 3: Add read-only workspace doctor

**Files:**
- Create: `src/research_os/doctor.py`
- Create: `tests/test_doctor.py`

- [ ] **Step 1: Write failing diagnostic tests**

```python
from research_os.doctor import run_doctor


def test_doctor_reports_healthy_workspace(tmp_path: Path) -> None:
    for folder in ("projects", "library", "inbox", ".agents/skills"):
        (tmp_path / folder).mkdir(parents=True, exist_ok=True)
    for skill in EXPECTED_SKILLS:
        path = tmp_path / ".agents" / "skills" / skill
        path.mkdir()
        (path / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "research.yaml").write_text("version: 1\n", encoding="utf-8")

    report = run_doctor(tmp_path, stdout_encoding="utf-8", python_version=(3, 11, 0))

    assert report.exit_code == 0
    assert not [item for item in report.items if item.level == "fail"]


def test_doctor_fails_for_missing_workspace_structure(tmp_path: Path) -> None:
    report = run_doctor(tmp_path, stdout_encoding="utf-8", python_version=(3, 11, 0))

    assert report.exit_code == 1
    assert any(item.name == "workspace" and item.level == "fail" for item in report.items)


def test_doctor_warns_for_non_utf8_console(tmp_path: Path) -> None:
    report = run_doctor(tmp_path, stdout_encoding="cp936", python_version=(3, 11, 0))

    console = next(item for item in report.items if item.name == "console")
    assert console.level == "warn"
    assert "PYTHONUTF8" in console.fix
```

- [ ] **Step 2: Run diagnostic tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_doctor.py -q
```

Expected: import fails because `research_os.doctor` does not exist.

- [ ] **Step 3: Implement focused diagnostics**

Create immutable output models:

```python
EXPECTED_SKILLS = (
    "research-project-init", "paper-intake", "paper-deep-read",
    "literature-synthesis", "idea-review", "experiment-advisor",
    "result-interpreter", "manuscript-assistant", "mock-reviewer",
    "research-weekly-review",
)


@dataclass(frozen=True)
class DiagnosticItem:
    level: str
    name: str
    message: str
    fix: str = ""


@dataclass(frozen=True)
class DoctorReport:
    items: tuple[DiagnosticItem, ...]

    @property
    def exit_code(self) -> int:
        return 1 if any(item.level == "fail" for item in self.items) else 0
```

Implement `run_doctor(workspace, stdout_encoding=None, python_version=None)` as a read-only function. It must inspect required directories, skill files, Python >= 3.11, console encoding, parse `library/sources.jsonl` through `SourceRegistry.records()`, call `verified_source_ids()` to identify stale local files, and verify each project contains the seven numbered core files. Convert parse errors into a `fail` item instead of raising.

Add `render_doctor(report)` that emits one line per item in the stable format `[PASS] name: message`, `[WARN] ...`, or `[FAIL] ...`, followed by indented `修复：...` only when `fix` is non-empty.

- [ ] **Step 4: Verify diagnostics**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_doctor.py -q -W error
```

Expected: all doctor tests pass.

- [ ] **Step 5: Commit doctor**

```powershell
git add src/research_os/doctor.py tests/test_doctor.py
git commit -m "feat: diagnose Research OS workspaces"
```

### Task 4: Add deterministic project guidance

**Files:**
- Create: `src/research_os/guidance.py`
- Create: `tests/test_guidance.py`

- [ ] **Step 1: Write failing next-action tests**

```python
from research_os.guidance import guide_project


def test_new_project_recommends_research_brief(tmp_path: Path) -> None:
    create_project(tmp_path, "医疗推理", "medical-reasoning")

    report = guide_project(tmp_path, "medical-reasoning")

    assert report.next_action.skill == "research-project-init"
    assert report.next_action.target == "00-research-brief.md"


def test_edited_brief_without_linked_sources_recommends_intake(tmp_path: Path) -> None:
    project = create_project(tmp_path, "A", "topic-a")
    (project / "00-research-brief.md").write_text(
        "# A\n\n## 一句话研究问题\n方法 X 是否改善任务 Y？\n",
        encoding="utf-8",
    )

    report = guide_project(tmp_path, "topic-a")

    assert report.next_action.skill == "paper-intake"
    assert "--project topic-a" in report.next_action.command


def test_projects_do_not_share_global_sources(tmp_path: Path) -> None:
    first = create_project(tmp_path, "A", "topic-a")
    second = create_project(tmp_path, "B", "topic-b")
    for project, title in ((first, "A"), (second, "B")):
        (project / "00-research-brief.md").write_text(
            f"# {title}\n\n研究问题已填写。\n", encoding="utf-8"
        )
    link_project_sources(tmp_path, "topic-a", ["src-only-a"])

    report = guide_project(tmp_path, "topic-b")

    assert report.next_action.skill == "paper-intake"


def test_experiment_design_waits_for_external_results(tmp_path: Path) -> None:
    project = create_progressed_project_through_design(tmp_path)

    report = guide_project(tmp_path, project.name)

    assert report.next_action.skill is None
    assert "独立实验仓库" in report.next_action.command
    assert "不执行实验" in report.next_action.reason
```

Define the helper with real package functions, not mocks:

```python
def create_progressed_project_through_design(tmp_path: Path) -> Path:
    project = create_project(tmp_path, "A", "topic-a")
    record = SourceRegistry(tmp_path / "library" / "sources.jsonl").add(
        "doi:10.1000/topic-a"
    )
    link_project_sources(tmp_path, "topic-a", [record.source_id])
    papers = tmp_path / "library" / "papers"
    papers.mkdir(parents=True)
    (papers / "topic-a-paper.md").write_text(
        f"# Paper\n\nsource_id: {record.source_id}\n", encoding="utf-8"
    )
    (project / "00-research-brief.md").write_text(
        "# A\n\n研究问题已由研究者填写。\n", encoding="utf-8"
    )
    (project / "02-evidence-ledger.yaml").write_text(
        f'''project: A
schema_version: 1
claims:
  - claim_id: C001
    statement: 论文报告了公开任务结果
    type: fact
    status: verified
    support:
      - source_id: {record.source_id}
        locator: p. 1
    opposition: []
    confidence: medium
    limitations: 仅限论文报告的公开任务
''',
        encoding="utf-8",
    )
    for filename in (
        "03-literature-review.md",
        "04-idea-candidates.md",
        "05-experiment-design.md",
    ):
        (project / filename).write_text(
            f"# {filename}\n\n已由研究者填写。\n", encoding="utf-8"
        )
    return project
```

- [ ] **Step 2: Run guidance tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_guidance.py -q
```

Expected: import fails because `research_os.guidance` does not exist.

- [ ] **Step 3: Implement stages and one-action selection**

Create these public result models:

```python
@dataclass(frozen=True)
class StageView:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class NextAction:
    reason: str
    target: str
    command: str
    skill: str | None


@dataclass(frozen=True)
class GuideReport:
    title: str
    slug: str
    stages: tuple[StageView, ...]
    next_action: NextAction
```

Implement `_matches_template(project_path, filename, template_name, title)` using `template_content` and exact normalized newline comparison. Implement `_linked_paper_card_count(workspace, source_ids)` by scanning `library/papers/*.md` for explicit IDs. Implement `_result_inputs(project_path)` by ignoring `.gitkeep` and provenance files in `artifacts/`.

`guide_project` must select the first matching action in this fixed order:

1. Unchanged brief -> `$research-project-init`, target `00-research-brief.md`.
2. No explicitly linked source -> `$paper-intake`, include `--project SLUG` where `SLUG` is `report.slug`.
3. No paper card containing a linked source ID -> `$paper-deep-read`.
4. Empty ledger or unchanged literature synthesis -> `$literature-synthesis`.
5. Unchanged Idea file -> `$idea-review`.
6. Unchanged experiment design -> `$experiment-advisor`.
7. No external result artifact -> no skill; explain that Research OS does not execute experiments and request a public/deidentified aggregate result file from the independent experiment repository.
8. Unchanged result analysis with an artifact present -> `$result-interpreter`.
9. No Markdown manuscript in `writing/` -> `$manuscript-assistant`.
10. No Markdown review in `reviews/` -> `$mock-reviewer`.
11. Otherwise -> `$research-weekly-review`.

Before action selection, load and validate the evidence ledger. A malformed ledger or unknown linked source must produce a `受阻` stage and a next action that tells the user to run `validate-ledger`; it must not advance to Idea or writing.

Implement `render_guide(report)` as a compact Chinese dashboard: title line, a four-column Markdown table (`阶段/状态/说明` is sufficient as three columns), then exactly one `下一步` section containing reason, target, and a fenced text command.

- [ ] **Step 4: Verify guidance and evidence integration**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_guidance.py tests/test_evidence.py -q -W error
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit guidance**

```powershell
git add src/research_os/guidance.py tests/test_guidance.py
git commit -m "feat: recommend the next research action"
```

### Task 5: Expose the daily-driver CLI and UTF-8 entrypoint

**Files:**
- Modify: `src/research_os/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `.agents/skills/paper-intake/SKILL.md`

- [ ] **Step 1: Write failing CLI integration tests**

```python
def test_cli_guide_requires_no_project_when_workspace_is_empty(
    tmp_path: Path, capsys
) -> None:
    (tmp_path / "projects").mkdir()

    assert main(["guide", "--workspace", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "new-project" in output
    assert "下一步" in output


def test_cli_batch_import_links_sources_to_project(tmp_path: Path) -> None:
    create_project(tmp_path, "A", "topic-a")
    manifest = tmp_path / "sources.txt"
    manifest.write_text("doi:10.1000/a\narXiv:2401.01234\n", encoding="utf-8")

    exit_code = main(
        [
            "add-sources", str(manifest), "--workspace", str(tmp_path),
            "--project", "topic-a",
        ]
    )

    assert exit_code == 0
    assert len(load_project_manifest(tmp_path / "projects" / "topic-a").source_ids) == 2


def test_cli_doctor_uses_report_exit_code(tmp_path: Path, capsys) -> None:
    assert main(["doctor", "--workspace", str(tmp_path)]) == 1
    assert "[FAIL]" in capsys.readouterr().out
```

- [ ] **Step 2: Run CLI tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cli.py -q
```

Expected: argparse rejects `guide`, `doctor`, `add-sources`, and `--project`.

- [ ] **Step 3: Wire services into argparse**

Add parsers with these exact interfaces:

```text
research-os doctor [--workspace PATH]
research-os guide [--project SLUG] [--workspace PATH]
research-os add-sources MANIFEST [--project SLUG] [--notes TEXT]
                        [--allow-external-api] [--workspace PATH]
research-os add-source SOURCE [--project SLUG] ...existing options...
```

When `guide` receives no project:

- zero projects: print one next action containing `new-project`;
- one project: select it automatically;
- multiple projects: list slugs and return exit code `2`, requiring explicit `--project`.

For `add-source` and `add-sources`, preflight the requested project before modifying the source registry, then call `link_project_sources` after successful registry write. Render batch counts as `新增 N，重复 N，升级外发许可 N，关联课题 SLUG`.

Add Windows UTF-8 configuration only in `entrypoint`, so pytest's direct `main()` calls are not mutated:

```python
def _configure_windows_utf8() -> None:
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def entrypoint() -> None:
    _configure_windows_utf8()
    raise SystemExit(main())
```

- [ ] **Step 4: Update the paper-intake skill contract**

In `.agents/skills/paper-intake/SKILL.md`, require `--project medical-reasoning` in the worked example and state that the actual target project's slug must replace `medical-reasoning`. Require `add-sources` for a user-provided list. State that source IDs must appear in `project.yaml` before the skill reports intake complete. Do not change medical privacy or external API gates.

- [ ] **Step 5: Run CLI and skill validation**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cli.py tests/test_skills.py -q -W error
```

Expected: all selected tests pass and the modified skill remains valid.

- [ ] **Step 6: Commit the CLI slice**

```powershell
git add src/research_os/cli.py tests/test_cli.py .agents/skills/paper-intake/SKILL.md
git commit -m "feat: expose the Research OS daily driver"
```

### Task 6: Documentation, packaging, and end-to-end verification

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `tests/test_workspace.py`

- [ ] **Step 1: Write a failing packaging/workspace assertion**

Add to `tests/test_workspace.py`:

```python
def test_daily_driver_is_documented_and_packaged() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "research-os guide" in readme
    assert "research-os doctor" in readme
    assert "research-os add-sources" in readme
    assert 'version = "0.2.0"' in pyproject
```

- [ ] **Step 2: Run the assertion and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_workspace.py -q
```

Expected: failure because the v0.2 commands and version are absent.

- [ ] **Step 3: Rewrite the quick start around the daily workflow**

Update `README.md` so the first runnable sequence is:

```powershell
.\.venv\Scripts\research-os.exe doctor
.\.venv\Scripts\research-os.exe new-project --title "医疗诊断大模型的可靠推理" --slug medical-reasoning
.\.venv\Scripts\research-os.exe guide --project medical-reasoning
```

Add a batch intake example with `--project medical-reasoning`, explain source association and old-project fallback, and keep the full DeepSeek consent example. Move low-level command detail after the daily workflow. Document that after experiment design, `guide` deliberately waits for aggregate results from a separate experiment repository.

Set `version = "0.2.0"` in `pyproject.toml`. The existing package-data glob already includes `start-here.md`; do not add a second package configuration.

- [ ] **Step 4: Run the full test suite**

```powershell
$env:PYTHONUTF8="1"
.\.venv\Scripts\python.exe -m compileall -q src
.\.venv\Scripts\python.exe -m pytest -q -W error
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Expected: compileall exits 0, every pytest test passes, pip reports `No broken requirements found.`, and `git diff --check` is silent.

- [ ] **Step 5: Build and smoke-test an installed wheel outside the source tree**

Use a newly created temporary directory and store it in `$taskSmokeRoot`. Build the wheel from the current working tree into `$taskSmokeRoot\dist`, install it into `$taskSmokeRoot\site`, create a healthy workspace in `$taskSmokeRoot\workspace`, and store the source list at `$taskSmokeRoot\sources.txt`. Then run:

```powershell
$taskSmokeRoot = Join-Path ([IO.Path]::GetTempPath()) ("research-os-v02-" + [guid]::NewGuid().ToString("N"))
$taskSmokeWorkspace = Join-Path $taskSmokeRoot "workspace"
$taskSmokeSite = Join-Path $taskSmokeRoot "site"
New-Item -ItemType Directory -Path $taskSmokeWorkspace -Force | Out-Null
Copy-Item -LiteralPath config, inbox, library, projects, .agents -Destination $taskSmokeWorkspace -Recurse
.\.venv\Scripts\python.exe -m pip wheel . --no-deps --wheel-dir (Join-Path $taskSmokeRoot "dist")
$taskWheel = Get-ChildItem -LiteralPath (Join-Path $taskSmokeRoot "dist") -Filter *.whl | Select-Object -First 1
.\.venv\Scripts\python.exe -m pip install --target $taskSmokeSite $taskWheel.FullName
$env:PYTHONPATH = $taskSmokeSite
.\.venv\Scripts\python.exe -m research_os doctor --workspace $taskSmokeWorkspace
.\.venv\Scripts\python.exe -m research_os new-project --workspace $taskSmokeWorkspace --title "Smoke" --slug smoke
.\.venv\Scripts\python.exe -m research_os guide --workspace $taskSmokeWorkspace --project smoke
.\.venv\Scripts\python.exe -m research_os add-sources tests\fixtures\smoke-sources.txt --workspace $taskSmokeWorkspace --project smoke
```

Expected: no import/resource error; the new project contains `project.yaml` and `START-HERE.md`; guide recommends the brief first; batch sources are linked to `smoke`.

- [ ] **Step 6: Commit documentation and version**

```powershell
git add README.md pyproject.toml tests/test_workspace.py
git commit -m "docs: make Research OS a daily workflow"
```

- [ ] **Step 7: Run final repository hygiene checks**

```powershell
.\.venv\Scripts\python.exe -m pytest -q -W error
git status --short
git log -7 --oneline
```

Expected: all tests pass, status is clean, and the log contains one focused commit for each completed slice.
