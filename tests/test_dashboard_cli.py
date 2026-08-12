from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_os.cli import build_parser, main
from research_os.project import create_project


def _workspace_bytes(workspace: Path) -> dict[str, bytes]:
    return {
        path.relative_to(workspace).as_posix(): path.read_bytes()
        for path in sorted(workspace.rglob("*"))
        if path.is_file()
    }


def _project(workspace: Path) -> str:
    create_project(workspace, "医疗推理", "medical-reasoning")
    return "medical-reasoning"


def test_dashboard_json_is_deterministic_and_read_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    slug = _project(tmp_path)
    before = _workspace_bytes(tmp_path)
    argv = [
        "dashboard",
        "--project",
        slug,
        "--workspace",
        str(tmp_path),
        "--as-of",
        "2026-08-12",
        "--format",
        "json",
    ]

    assert main(argv) == 0
    first = capsys.readouterr().out
    assert main(argv) == 0
    second = capsys.readouterr().out

    payload = json.loads(first)
    assert first == second
    assert list(payload) == [
        "schema_version",
        "as_of",
        "project",
        "evidence",
        "idea",
        "recommendations",
        "risks",
        "actions",
    ]
    assert payload["schema_version"] == 1
    assert payload["as_of"] == "2026-08-12"
    assert payload["project"]["slug"] == slug
    assert payload["idea"]["candidate_generation_complete"] is False
    assert payload["idea"]["novelty_check_complete"] is False
    assert payload["idea"]["independent_review_complete"] is False
    assert payload["idea"]["meta_review_complete"] is False
    assert len(payload["actions"]) <= 3
    assert _workspace_bytes(tmp_path) == before


def test_dashboard_text_has_six_daily_sections(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    slug = _project(tmp_path)

    assert main(
        [
            "dashboard",
            "--project",
            slug,
            "--workspace",
            str(tmp_path),
            "--as-of",
            "2026-08-12",
        ]
    ) == 0

    output = capsys.readouterr().out
    for heading in (
        "## 课题状态",
        "## 证据健康度",
        "## Idea 与决策",
        "## 方法学参考",
        "## 风险雷达",
        "## 今日三个行动",
    ):
        assert output.count(heading) == 1
    assert "只读" in output
    assert "不会自动成为当前课题引用证据" in output


def test_dashboard_invalid_date_returns_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    slug = _project(tmp_path)

    code = main(
        [
            "dashboard",
            "--project",
            slug,
            "--workspace",
            str(tmp_path),
            "--as-of",
            "not-a-date",
        ]
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "--as-of 必须是 YYYY-MM-DD 日期" in captured.err


def test_dashboard_requires_explicit_project() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["dashboard"])

    assert exc_info.value.code == 2


def test_dashboard_malformed_ledger_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    slug = _project(tmp_path)
    ledger = tmp_path / "projects" / slug / "02-evidence-ledger.yaml"
    ledger.write_text("claims: [", encoding="utf-8")

    code = main(
        [
            "dashboard",
            "--project",
            slug,
            "--workspace",
            str(tmp_path),
            "--as-of",
            "2026-08-12",
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "证据账本 YAML 无法解析" in captured.err


def test_dashboard_malformed_knowledge_base_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    slug = _project(tmp_path)
    knowledge = tmp_path / "library" / "knowledge"
    knowledge.mkdir(parents=True)
    (knowledge / "catalog.yaml").write_text("entries: [", encoding="utf-8")

    code = main(
        [
            "dashboard",
            "--project",
            slug,
            "--workspace",
            str(tmp_path),
            "--as-of",
            "2026-08-12",
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "kb doctor" in captured.err
