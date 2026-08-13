from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
import os
import shutil
import subprocess

import pytest

import research_os.cli as cli_module
import research_os.manuscript_audit as audit_module
from research_os.cli import main
from research_os.dashboard import ProjectStatus
from research_os.manuscript_audit import (
    ManuscriptAudit,
    SectionAudit,
    build_manuscript_audit,
    manuscript_audit_payload,
    render_manuscript_audit,
)
from research_os.project import create_project


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
    monkeypatch.setattr(
        cli_module,
        "build_manuscript_audit",
        lambda *_args, **_kwargs: replace(_audit(), status="issues"),
    )

    assert main(["manuscript-audit", "--project", "public-project", "--draft", "writing/draft.md", "--workspace", str(tmp_path)]) == 1


def test_cli_phi_error_is_exit_two_without_sensitive_echo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project, draft = _draft_project(tmp_path, "## Abstract\npatient_id: secret\n")

    assert main(["manuscript-audit", "--project", project.name, "--draft", str(draft), "--workspace", str(tmp_path)]) == 2
    error = capsys.readouterr().err
    assert "PHI_SUSPECTED" in error
    assert "patient_id" not in error
    assert "secret" not in error
