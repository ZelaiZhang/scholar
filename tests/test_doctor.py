from pathlib import Path

from research_os.doctor import EXPECTED_SKILLS, run_doctor
from research_os.project import create_project


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
