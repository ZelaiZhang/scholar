import os
import subprocess
from pathlib import Path

import pytest

from research_os.doctor import EXPECTED_SKILLS, run_doctor
from research_os.project import create_project, link_project_sources
from research_os.cycle import advance_cycle


def make_healthy_workspace(path: Path) -> None:
    for folder in ("projects", "library", "inbox", ".agents/skills"):
        (path / folder).mkdir(parents=True, exist_ok=True)
    for skill in EXPECTED_SKILLS:
        skill_path = path / ".agents" / "skills" / skill
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text(
            f"---\nname: {skill}\n---\n", encoding="utf-8"
        )
    (path / "config").mkdir()
    (path / "config" / "research.yaml").write_text(
        "version: 1\n", encoding="utf-8"
    )


def test_doctor_reports_healthy_workspace(tmp_path: Path) -> None:
    make_healthy_workspace(tmp_path)

    report = run_doctor(
        tmp_path, stdout_encoding="utf-8", python_version=(3, 11, 0)
    )

    assert report.exit_code == 0
    assert not [item for item in report.items if item.level == "fail"]


def test_doctor_fails_for_missing_workspace_structure(tmp_path: Path) -> None:
    report = run_doctor(
        tmp_path, stdout_encoding="utf-8", python_version=(3, 11, 0)
    )

    assert report.exit_code == 1
    assert any(
        item.name == "workspace" and item.level == "fail"
        for item in report.items
    )


def test_doctor_warns_for_non_utf8_console(tmp_path: Path) -> None:
    report = run_doctor(
        tmp_path, stdout_encoding="cp936", python_version=(3, 11, 0)
    )

    console = next(item for item in report.items if item.name == "console")
    assert console.level == "warn"
    assert "PYTHONUTF8" in console.fix


def test_doctor_turns_broken_source_registry_into_failure(tmp_path: Path) -> None:
    make_healthy_workspace(tmp_path)
    (tmp_path / "library" / "sources.jsonl").write_text(
        "not-json\n", encoding="utf-8"
    )

    report = run_doctor(
        tmp_path, stdout_encoding="utf-8", python_version=(3, 11, 0)
    )

    registry = next(item for item in report.items if item.name == "sources")
    assert registry.level == "fail"
    assert report.exit_code == 1


def test_doctor_fails_when_project_core_file_is_missing(tmp_path: Path) -> None:
    make_healthy_workspace(tmp_path)
    project = create_project(tmp_path, "A", "topic-a")
    (project / "02-evidence-ledger.yaml").unlink()

    report = run_doctor(
        tmp_path, stdout_encoding="utf-8", python_version=(3, 11, 0)
    )

    projects = next(item for item in report.items if item.name == "projects")
    assert projects.level == "fail"
    assert "02-evidence-ledger.yaml" in projects.message


def test_doctor_reports_broken_project_yaml_without_crashing(
    tmp_path: Path,
) -> None:
    make_healthy_workspace(tmp_path)
    project = create_project(tmp_path, "A", "topic-a")
    (project / "project.yaml").write_text(
        "schema_version: [broken", encoding="utf-8"
    )

    report = run_doctor(
        tmp_path, stdout_encoding="utf-8", python_version=(3, 11, 0)
    )

    projects = next(item for item in report.items if item.name == "projects")
    assert projects.level == "fail"
    assert "YAML 无法解析" in projects.message


def test_doctor_reports_source_schema_error_without_crashing(
    tmp_path: Path,
) -> None:
    make_healthy_workspace(tmp_path)
    (tmp_path / "library" / "sources.jsonl").write_text(
        '{"source_id":"src-x","kind":"file","canonical":null,'
        '"imported_at":""}\n',
        encoding="utf-8",
    )

    report = run_doctor(
        tmp_path, stdout_encoding="utf-8", python_version=(3, 11, 0)
    )

    sources = next(item for item in report.items if item.name == "sources")
    assert sources.level == "fail"
    assert report.exit_code == 1


def test_doctor_rejects_files_where_workspace_directories_are_required(
    tmp_path: Path,
) -> None:
    make_healthy_workspace(tmp_path)
    for name in ("library", "inbox"):
        path = tmp_path / name
        path.rmdir()
        path.write_text("not a directory", encoding="utf-8")

    report = run_doctor(
        tmp_path, stdout_encoding="utf-8", python_version=(3, 11, 0)
    )

    workspace = next(item for item in report.items if item.name == "workspace")
    assert workspace.level == "fail"
    assert report.exit_code == 1


def test_doctor_rejects_workspace_directory_link(
    tmp_path: Path,
) -> None:
    make_healthy_workspace(tmp_path)
    library = tmp_path / "library"
    library.rmdir()
    outside = tmp_path / "outside-library"
    outside.mkdir()
    try:
        if os.name == "nt":
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(library), str(outside)],
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            library.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"无法在当前环境创建目录链接: {exc}")

    report = run_doctor(
        tmp_path, stdout_encoding="utf-8", python_version=(3, 11, 0)
    )

    workspace = next(item for item in report.items if item.name == "workspace")
    sources = next(item for item in report.items if item.name == "sources")
    assert workspace.level == "fail"
    assert sources.level == "fail"
    assert report.exit_code == 1


def test_doctor_reports_project_source_ids_missing_from_registry(
    tmp_path: Path,
) -> None:
    make_healthy_workspace(tmp_path)
    create_project(tmp_path, "A", "topic-a")
    link_project_sources(tmp_path, "topic-a", ["src-missing"])

    report = run_doctor(
        tmp_path, stdout_encoding="utf-8", python_version=(3, 11, 0)
    )

    projects = next(item for item in report.items if item.name == "projects")
    assert projects.level == "fail"
    assert "src-missing" in projects.message


def test_doctor_reports_corrupt_idea_archive_without_crashing(
    tmp_path: Path,
) -> None:
    make_healthy_workspace(tmp_path)
    project = create_project(tmp_path, "A", "topic-a")
    ideas = project / "ideas"
    ideas.mkdir()
    (ideas / "archive.yaml").write_text("schema_version: [broken", encoding="utf-8")

    report = run_doctor(
        tmp_path, stdout_encoding="utf-8", python_version=(3, 11, 0)
    )

    projects = next(item for item in report.items if item.name == "projects")
    assert projects.level == "fail"
    assert "archive" in projects.message


def test_doctor_checks_corrupt_inactive_cycle_manifest(
    tmp_path: Path,
) -> None:
    make_healthy_workspace(tmp_path)
    project = create_project(tmp_path, "A", "topic-a")
    first = advance_cycle(tmp_path, "topic-a")
    advance_cycle(tmp_path, "topic-a", new_run=True)
    (project / "cycles" / first.run_id / "manifest.yaml").write_text(
        "schema_version: [broken", encoding="utf-8"
    )

    report = run_doctor(
        tmp_path, stdout_encoding="utf-8", python_version=(3, 11, 0)
    )

    projects = next(item for item in report.items if item.name == "projects")
    assert projects.level == "fail"
    assert first.run_id in projects.message


def test_doctor_detects_tampered_research_journal(tmp_path: Path) -> None:
    make_healthy_workspace(tmp_path)
    project = create_project(tmp_path, "A", "topic-a")
    advance_cycle(tmp_path, "topic-a")
    journal = project / "research-journal.jsonl"
    journal.write_text(
        journal.read_text(encoding="utf-8").replace("bounded", "tampered", 1),
        encoding="utf-8",
    )

    report = run_doctor(
        tmp_path, stdout_encoding="utf-8", python_version=(3, 11, 0)
    )

    projects = next(item for item in report.items if item.name == "projects")
    assert projects.level == "fail"
    assert "journal" in projects.message or "日志" in projects.message
