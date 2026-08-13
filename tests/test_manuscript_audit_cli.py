from __future__ import annotations

from dataclasses import replace
from datetime import date
import hashlib
import json
from pathlib import Path
import os
import shutil
import subprocess

import pytest

import research_os.cli as cli_module
import research_os.io as io_module
import research_os.manuscript_audit as audit_module
from research_os.cli import main
from research_os.dashboard import ProjectStatus
from research_os.manuscript_audit import (
    ManuscriptAudit,
    ManuscriptAuditIssue,
    SectionAudit,
    build_manuscript_audit,
    manuscript_audit_payload,
    render_manuscript_audit,
)
from research_os.project import create_project, link_project_sources
from research_os.sources import SourceRegistry


def test_builder_rejects_draft_outside_project_writing_directory(tmp_path: Path) -> None:
    project = create_project(tmp_path, "Public project", "public-project")
    outside = tmp_path / "outside.md"
    outside.write_text("## Abstract\n", encoding="utf-8")

    with pytest.raises(ValueError):
        build_manuscript_audit(
            tmp_path,
            project.name,
            outside,
            as_of=date(2026, 8, 13),
        )


def _audit() -> ManuscriptAudit:
    sections = tuple(
        SectionAudit(code, title, "ready", 0, 0, 0)
        for code, title in (
            ("abstract", "Abstract"),
            ("introduction", "Introduction"),
            ("related_work", "Related Work"),
            ("methods", "Methods"),
            ("experiments", "Experiments"),
            ("results", "Results"),
            ("limitations_ethics", "Limitations and Ethics"),
            ("conclusion", "Conclusion"),
        )
    )
    return ManuscriptAudit(
        1,
        "2026-08-13",
        ProjectStatus("Public project", "public-project", "writing", "active", ()),
        "writing/draft.md",
        "0" * 64,
        "pass",
        (("fact", 0), ("inference", 0), ("hypothesis", 0), ("limitation", 0), ("method", 0), ("result", 0)),
        sections,
        (),
        ("C001",),
        ("metrics.csv",),
        ("ANNOTATION_NOT_ENTAILMENT",),
    )


def _draft_project(tmp_path: Path, content: str = "## Abstract\nPublic text.\n") -> tuple[Path, Path]:
    project = create_project(tmp_path, "Public project", "public-project")
    draft = project / "writing" / "draft.md"
    draft.write_text(content, encoding="utf-8")
    return project, draft


def _write_result_input(project: Path, content: str = "metric,value\nscore,1\n") -> Path:
    artifacts = project / "artifacts"
    artifact = artifacts / "metrics.csv"
    artifact.write_text(content, encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    (artifacts / "results-manifest.yaml").write_text(
        "schema_version: 1\nresults:\n"
        "  - path: metrics.csv\n"
        f"    sha256: {digest}\n"
        "    source_repository: public-repository\n"
        "    generated_at: '2026-08-13T00:00:00Z'\n",
        encoding="utf-8",
    )
    return artifact


def test_builder_accepts_a_direct_utf8_markdown_file_without_writes(tmp_path: Path) -> None:
    project, draft = _draft_project(tmp_path)
    before = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    audit = build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))

    after = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert audit.draft_path == "writing/draft.md"
    assert after == before


@pytest.mark.parametrize("relative", ("writing/nested/draft.md", "writing/draft.txt"))
def test_builder_rejects_nested_and_wrong_extension_drafts(tmp_path: Path, relative: str) -> None:
    project = create_project(tmp_path, "Public project", "public-project")
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("## Abstract\n", encoding="utf-8")

    with pytest.raises(ValueError):
        build_manuscript_audit(tmp_path, project.name, path, as_of=date(2026, 8, 13))


def test_builder_rejects_draft_symlink(tmp_path: Path) -> None:
    project, draft = _draft_project(tmp_path)
    target = tmp_path / "outside.md"
    target.write_text("## Abstract\n", encoding="utf-8")
    draft.unlink()
    try:
        draft.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    with pytest.raises(ValueError):
        build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))


def test_builder_rejects_writing_directory_symlink_alias(tmp_path: Path) -> None:
    project, draft = _draft_project(tmp_path)
    alias = project / "writing-alias"
    try:
        alias.symlink_to(project / "writing", target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")

    with pytest.raises(ValueError):
        build_manuscript_audit(
            tmp_path, project.name, alias / draft.name, as_of=date(2026, 8, 13)
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows junction test")
def test_builder_rejects_writing_directory_junction_alias(tmp_path: Path) -> None:
    project, draft = _draft_project(tmp_path)
    alias = project / "writing-alias"
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(alias), str(project / "writing")],
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        pytest.skip("junction creation unavailable")

    with pytest.raises(ValueError):
        build_manuscript_audit(
            tmp_path, project.name, alias / draft.name, as_of=date(2026, 8, 13)
        )


def test_builder_rejects_lexically_nested_parent_that_resolves_to_writing(
    tmp_path: Path,
) -> None:
    project, _draft = _draft_project(tmp_path)
    (project / "writing" / "nested").mkdir()

    with pytest.raises(ValueError):
        build_manuscript_audit(
            tmp_path,
            project.name,
            Path("writing") / "nested" / ".." / "draft.md",
            as_of=date(2026, 8, 13),
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows junction test")
def test_builder_rejects_windows_reparse_draft(tmp_path: Path) -> None:
    project = create_project(tmp_path, "Public project", "public-project")
    target = tmp_path / "target"
    target.mkdir()
    draft = project / "writing" / "draft.md"
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(draft), str(target)],
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        pytest.skip("junction creation unavailable")

    with pytest.raises(ValueError):
        build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))


def test_builder_rejects_drafts_larger_than_four_mebibytes(tmp_path: Path) -> None:
    project, draft = _draft_project(tmp_path)
    draft.write_bytes(b"x" * (4 * 1024 * 1024 + 1))

    with pytest.raises(ValueError):
        build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))


def test_builder_rejects_non_utf8_draft(tmp_path: Path) -> None:
    project, draft = _draft_project(tmp_path)
    draft.write_bytes(b"\xff\xfe")

    with pytest.raises(UnicodeError):
        build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))


@pytest.mark.parametrize("marker", ("姓名", "住院号", "身份证", "联系电话", "patient_id", "medical_record_number"))
def test_builder_stops_for_each_phi_marker_without_echoing_it(tmp_path: Path, marker: str) -> None:
    project, draft = _draft_project(tmp_path, f"## Abstract\n{marker}: secret\n")

    with pytest.raises(PermissionError) as exc_info:
        build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))

    assert str(exc_info.value) == "PHI_SUSPECTED"
    assert marker not in str(exc_info.value)


def test_builder_stops_for_phi_before_attempting_to_read_a_broken_ledger(tmp_path: Path) -> None:
    project, draft = _draft_project(tmp_path, "## Abstract\npatient_id: secret\n")
    (project / "02-evidence-ledger.yaml").write_text("schema_version: [broken", encoding="utf-8")

    with pytest.raises(PermissionError) as exc_info:
        build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))

    assert str(exc_info.value) == "PHI_SUSPECTED"


def test_builder_detects_same_content_draft_replacement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project, draft = _draft_project(tmp_path)
    original_parse = audit_module.parse_manuscript

    def replace_then_parse(content: str):
        replacement = draft.with_name("replacement.md")
        replacement.write_text(content, encoding="utf-8")
        os.replace(replacement, draft)
        return original_parse(content)

    monkeypatch.setattr(audit_module, "parse_manuscript", replace_then_parse)

    with pytest.raises(OSError):
        build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))


def test_builder_detects_replacement_immediately_after_draft_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, draft = _draft_project(tmp_path)
    original_read = audit_module.read_stable_direct_text

    def replace_after_read(path: Path, **kwargs: object) -> str:
        content = original_read(path, **kwargs)
        replacement = draft.with_name("replacement.md")
        replacement.write_text(content, encoding="utf-8")
        os.replace(replacement, draft)
        return content

    monkeypatch.setattr(audit_module, "read_stable_direct_text", replace_after_read)

    with pytest.raises(OSError):
        build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))


def test_builder_detects_same_content_replacement_during_lowest_level_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, draft = _draft_project(tmp_path)
    expected_identity = (draft.stat().st_dev, draft.stat().st_ino)
    replacement_content = draft.read_bytes()
    original_read = io_module.os.read
    replaced = False
    replacement_blocked = False

    def replace_during_read(descriptor: int, size: int) -> bytes:
        nonlocal replaced, replacement_blocked
        if not replaced:
            metadata = os.fstat(descriptor)
            if (metadata.st_dev, metadata.st_ino) == expected_identity:
                replacement = draft.with_name("replacement.md")
                replacement.write_bytes(replacement_content)
                try:
                    os.replace(replacement, draft)
                except PermissionError:
                    replacement.unlink(missing_ok=True)
                    replacement_blocked = True
                else:
                    replaced = True
        return original_read(descriptor, size)

    monkeypatch.setattr(io_module.os, "read", replace_during_read)

    try:
        build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))
    except OSError:
        pass
    else:
        if replacement_blocked:
            pytest.skip("platform disallows replacing an open read-only file")
        pytest.fail("same-content replacement during os.read was accepted")
    if replacement_blocked:
        pytest.skip("platform disallows replacing an open read-only file")
    assert replaced


def test_builder_detects_writing_directory_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _draft = _draft_project(tmp_path)
    original_brief = audit_module.build_meeting_brief
    writing = project / "writing"
    moved = project / "moved-writing"

    def replace_after_first_brief(*args: object, **kwargs: object):
        brief = original_brief(*args, **kwargs)
        if not moved.exists():
            writing.rename(moved)
            shutil.copytree(moved, writing)
        return brief

    monkeypatch.setattr(audit_module, "build_meeting_brief", replace_after_first_brief)

    with pytest.raises(OSError):
        build_manuscript_audit(tmp_path, project.name, project / "writing" / "draft.md", as_of=date(2026, 8, 13))


def test_builder_detects_same_content_project_directory_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, draft = _draft_project(tmp_path)
    original_brief = audit_module.build_meeting_brief
    moved = tmp_path / "moved-project"

    def replace_after_first_brief(*args: object, **kwargs: object):
        brief = original_brief(*args, **kwargs)
        if not moved.exists():
            project.rename(moved)
            shutil.copytree(moved, project)
        return brief

    monkeypatch.setattr(audit_module, "build_meeting_brief", replace_after_first_brief)

    with pytest.raises(OSError):
        build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))


def test_builder_detects_research_state_change_between_snapshots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, draft = _draft_project(tmp_path)
    original_brief = audit_module.build_meeting_brief
    calls = 0

    def changed_second_brief(*args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        brief = original_brief(*args, **kwargs)
        return brief if calls == 1 else replace(brief, project=replace(brief.project, blockers=("changed",)))

    monkeypatch.setattr(audit_module, "build_meeting_brief", changed_second_brief)

    with pytest.raises(OSError, match="research state"):
        build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))


@pytest.mark.parametrize("name", ("02-evidence-ledger.yaml", "00-research-brief.md"))
def test_builder_detects_byte_identical_replacement_of_research_state_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    project, draft = _draft_project(tmp_path)
    target = project / name
    original_parse = audit_module.parse_manuscript

    def replace_state_then_parse(content: str):
        replacement = target.with_name(f"replacement-{name}")
        replacement.write_bytes(target.read_bytes())
        os.replace(replacement, target)
        return original_parse(content)

    monkeypatch.setattr(audit_module, "parse_manuscript", replace_state_then_parse)

    with pytest.raises(OSError, match="research state"):
        build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))


def test_builder_detects_cycle_directory_identity_replacement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project, draft = _draft_project(tmp_path)
    brief = audit_module.build_meeting_brief(tmp_path, project.name, as_of=date(2026, 8, 13))
    cycles = project / "cycles"
    cycles.mkdir()
    original_parse = audit_module.parse_manuscript

    def replace_cycles_then_parse(content: str):
        moved = project / "moved-cycles"
        cycles.rename(moved)
        shutil.copytree(moved, cycles)
        return original_parse(content)

    monkeypatch.setattr(audit_module, "parse_manuscript", replace_cycles_then_parse)
    monkeypatch.setattr(audit_module, "build_meeting_brief", lambda *_args, **_kwargs: brief)

    with pytest.raises(OSError, match="research state"):
        build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))


@pytest.mark.parametrize("relative", ("ideas/archive.yaml", "cycles/active-run.txt"))
def test_builder_detects_direct_control_file_identity_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative: str
) -> None:
    project, draft = _draft_project(tmp_path)
    brief = audit_module.build_meeting_brief(tmp_path, project.name, as_of=date(2026, 8, 13))
    control = project / relative
    control.parent.mkdir(exist_ok=True)
    control.write_text("control\n", encoding="utf-8")
    original_parse = audit_module.parse_manuscript

    def replace_control_then_parse(content: str):
        replacement = control.with_name(f"replacement-{control.name}")
        replacement.write_bytes(control.read_bytes())
        os.replace(replacement, control)
        return original_parse(content)

    monkeypatch.setattr(audit_module, "parse_manuscript", replace_control_then_parse)
    monkeypatch.setattr(audit_module, "build_meeting_brief", lambda *_args, **_kwargs: brief)

    with pytest.raises(OSError, match="research state"):
        build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))


def test_builder_detects_selected_idea_drift_when_plan_payload_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, draft = _draft_project(tmp_path)
    original_brief = audit_module.build_meeting_brief
    original_plan = audit_module.manuscript_plan_from_brief
    calls = 0

    def selected_idea_drift(*args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        brief = original_brief(*args, **kwargs)
        return brief if calls == 1 else replace(
            brief,
            idea_state=replace(brief.idea_state, selected_idea_ids=("idea-drift",)),
        )

    first_plan: object | None = None

    def unchanged_plan(brief: object):
        nonlocal first_plan
        if first_plan is None:
            first_plan = original_plan(brief)  # type: ignore[arg-type]
        return first_plan

    monkeypatch.setattr(audit_module, "build_meeting_brief", selected_idea_drift)
    monkeypatch.setattr(audit_module, "manuscript_plan_from_brief", unchanged_plan)

    with pytest.raises(OSError, match="selected Idea IDs"):
        build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))


def test_builder_detects_coordinated_result_artifact_and_manifest_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, draft = _draft_project(tmp_path)
    _write_result_input(project)
    original_parse = audit_module.parse_manuscript

    def mutate_results_then_parse(content: str):
        _write_result_input(project, "metric,value\nscore,2\n")
        return original_parse(content)

    monkeypatch.setattr(audit_module, "parse_manuscript", mutate_results_then_parse)

    with pytest.raises(OSError, match="result inputs"):
        build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))


def test_builder_detects_result_mutation_during_first_state_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, draft = _draft_project(tmp_path)
    _write_result_input(project)
    original_brief = audit_module.build_meeting_brief
    calls = 0

    def mutate_after_brief(*args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        brief = original_brief(*args, **kwargs)
        if calls == 1:
            _write_result_input(project, "metric,value\nscore,2\n")
        return brief

    monkeypatch.setattr(audit_module, "build_meeting_brief", mutate_after_brief)

    with pytest.raises(OSError, match="result inputs"):
        build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))


def test_builder_detects_same_content_result_artifact_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, draft = _draft_project(tmp_path)
    artifact = _write_result_input(project)
    original_parse = audit_module.parse_manuscript

    def replace_artifact_then_parse(content: str):
        replacement = artifact.with_name("replacement.csv")
        replacement.write_bytes(artifact.read_bytes())
        os.replace(replacement, artifact)
        return original_parse(content)

    monkeypatch.setattr(audit_module, "parse_manuscript", replace_artifact_then_parse)

    with pytest.raises(OSError, match="result inputs"):
        build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))


def test_builder_detects_same_content_result_manifest_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, draft = _draft_project(tmp_path)
    _write_result_input(project)
    manifest = project / "artifacts" / "results-manifest.yaml"
    original_parse = audit_module.parse_manuscript

    def replace_manifest_then_parse(content: str):
        replacement = manifest.with_name("replacement-manifest.yaml")
        replacement.write_bytes(manifest.read_bytes())
        os.replace(replacement, manifest)
        return original_parse(content)

    monkeypatch.setattr(audit_module, "parse_manuscript", replace_manifest_then_parse)

    with pytest.raises(OSError, match="result inputs"):
        build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))


def test_builder_detects_draft_replacement_after_pre_final_identity_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, draft = _draft_project(tmp_path)
    original_identity = audit_module.direct_file_identity
    calls = 0

    def replace_after_pre_final_identity(path: Path, **kwargs: object):
        nonlocal calls
        identity = original_identity(path, **kwargs)
        if path == draft:
            calls += 1
        if path == draft and calls == 3:
            replacement = draft.with_name("replacement.md")
            replacement.write_bytes(draft.read_bytes())
            os.replace(replacement, draft)
        return identity

    monkeypatch.setattr(audit_module, "direct_file_identity", replace_after_pre_final_identity)

    with pytest.raises(OSError):
        build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))


@pytest.mark.parametrize("same_content", (True, False))
def test_builder_rechecks_draft_after_third_state_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, same_content: bool
) -> None:
    project, draft = _draft_project(tmp_path)
    original_snapshot = audit_module._research_state_snapshot
    calls = 0

    def replace_after_final_snapshot(*args: object, **kwargs: object):
        nonlocal calls
        snapshot = original_snapshot(*args, **kwargs)
        calls += 1
        if calls == 3:
            replacement = draft.with_name("replacement.md")
            replacement.write_bytes(
                draft.read_bytes() if same_content else b"## Abstract\nchanged\n"
            )
            os.replace(replacement, draft)
        return snapshot

    monkeypatch.setattr(audit_module, "_research_state_snapshot", replace_after_final_snapshot)

    with pytest.raises(OSError):
        build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))


def test_public_payload_and_renderer_exclude_manuscript_prose_and_identities() -> None:
    audit = _audit()

    payload = manuscript_audit_payload(audit)
    rendered = render_manuscript_audit(audit)

    assert tuple(payload) == (
        "schema_version", "as_of", "project", "draft_path", "draft_sha256",
        "status", "block_counts", "sections", "issues", "used_claim_ids",
        "used_result_artifacts", "boundaries",
    )
    assert len(payload["sections"]) == 8
    assert "writing/draft.md" in rendered
    assert "identity" not in rendered.casefold()
    assert "snapshot" not in rendered.casefold()


def test_builder_public_output_does_not_leak_poisoned_input_content(tmp_path: Path) -> None:
    prose = "MANUSCRIPT_PROSE_SHOULD_NOT_LEAK"
    note = "SOURCE_NOTE_SHOULD_NOT_LEAK"
    project, draft = _draft_project(tmp_path, f"## Abstract\n{prose}\n")
    source = SourceRegistry(tmp_path / "library" / "sources.jsonl").add(
        "doi:10.1000/public-output", notes=note
    )
    link_project_sources(tmp_path, project.name, [source.source_id])
    audit = build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))
    encoded = json.dumps(manuscript_audit_payload(audit), ensure_ascii=False)
    rendered = render_manuscript_audit(audit)

    for forbidden in (prose, note, str(tmp_path), "identity", "token", "snapshot"):
        assert forbidden.casefold() not in encoded.casefold()
        assert forbidden.casefold() not in rendered.casefold()


def test_builder_boundaries_are_exact_and_markdown_is_deterministic(tmp_path: Path) -> None:
    project, draft = _draft_project(tmp_path)
    first = build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))
    second = build_manuscript_audit(tmp_path, project.name, draft, as_of=date(2026, 8, 13))

    assert first.boundaries == (
        "ANNOTATION_NOT_ENTAILMENT",
        "This audit is not clinical decision support.",
        "Research OS did not rewrite the manuscript or execute experiments.",
        "The researcher must verify semantic entailment and approve every statement.",
    )
    assert render_manuscript_audit(first) == render_manuscript_audit(second)


def test_renderer_uses_a_safe_code_span_for_backtick_draft_filename() -> None:
    rendered = render_manuscript_audit(
        replace(_audit(), draft_path="writing/` [active](https://example.test) `.md")
    )

    assert "- Draft: ``writing/` [active](https://example.test) `.md``" in rendered
    assert "- Draft: `writing/` [active]" not in rendered


def test_cli_emits_public_json_and_uses_issue_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    audit = _audit()
    monkeypatch.setattr(cli_module, "build_manuscript_audit", lambda *_args, **_kwargs: audit)

    exit_code = main(
        [
            "manuscript-audit", "--project", "public-project", "--draft",
            "writing/draft.md", "--workspace", str(tmp_path), "--as-of", "2026-08-13",
            "--format", "json",
        ]
    )

    assert exit_code == 0
    assert '"draft_path": "writing/draft.md"' in capsys.readouterr().out


def test_cli_returns_one_for_audit_issues(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    issue = ManuscriptAuditIssue("UNANNOTATED_BLOCK", "error", "Abstract", 1, 2, (), (), "safe")
    monkeypatch.setattr(
        cli_module,
        "build_manuscript_audit",
        lambda *_args, **_kwargs: replace(_audit(), issues=(issue,)),
    )

    assert main(["manuscript-audit", "--project", "public-project", "--draft", "writing/draft.md", "--workspace", str(tmp_path)]) == 1


def test_cli_uses_markdown_and_issue_presence_not_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        cli_module,
        "build_manuscript_audit",
        lambda *_args, **_kwargs: replace(_audit(), status="issues"),
    )

    assert main(["manuscript-audit", "--project", "public-project", "--draft", "writing/draft.md", "--workspace", str(tmp_path)]) == 0
    assert "# Manuscript audit" in capsys.readouterr().out


def test_cli_rejects_invalid_as_of(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["manuscript-audit", "--project", "public-project", "--draft", "writing/draft.md", "--workspace", str(tmp_path), "--as-of", "not-a-date"]) == 2
    assert "--as-of" in capsys.readouterr().err


@pytest.mark.parametrize("error", (ValueError("/poisoned/path artifact-secret"), OSError("/poisoned/path artifact-secret")))
def test_cli_maps_non_phi_audit_errors_without_echoing_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
) -> None:
    def fail(*_args: object, **_kwargs: object):
        raise error

    monkeypatch.setattr(cli_module, "build_manuscript_audit", fail)

    assert main(["manuscript-audit", "--project", "public-project", "--draft", "writing/draft.md", "--workspace", str(tmp_path)]) == 2
    captured = capsys.readouterr().err
    assert "artifact-secret" not in captured
    assert "/poisoned/path" not in captured
    assert "MANUSCRIPT_AUDIT_" in captured


@pytest.mark.parametrize(
    ("error", "expected_code"),
    (
        (PermissionError("PHI_SUSPECTED"), "PHI_SUSPECTED"),
        (PermissionError("ordinary /poisoned/path"), "MANUSCRIPT_AUDIT_INPUT_ERROR"),
    ),
)
def test_cli_only_preserves_the_exact_phi_permission_sentinel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: PermissionError,
    expected_code: str,
) -> None:
    def fail(*_args: object, **_kwargs: object):
        raise error

    monkeypatch.setattr(cli_module, "build_manuscript_audit", fail)

    assert main(["manuscript-audit", "--project", "public-project", "--draft", "writing/draft.md", "--workspace", str(tmp_path)]) == 2
    captured = capsys.readouterr().err
    assert expected_code in captured
    assert "/poisoned/path" not in captured


def test_cli_phi_error_is_exit_two_without_sensitive_echo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project, draft = _draft_project(tmp_path, "## Abstract\npatient_id: secret\n")

    assert main(["manuscript-audit", "--project", project.name, "--draft", str(draft), "--workspace", str(tmp_path)]) == 2
    error = capsys.readouterr().err
    assert "PHI_SUSPECTED" in error
    assert "patient_id" not in error
    assert "secret" not in error
