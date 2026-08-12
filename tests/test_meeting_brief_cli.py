import json
from pathlib import Path

from research_os.cli import main
from research_os.project import create_project, link_project_sources
from research_os.sources import SourceRegistry


def _workspace_bytes(workspace: Path) -> dict[str, bytes]:
    return {
        path.relative_to(workspace).as_posix(): path.read_bytes()
        for path in sorted(workspace.rglob("*"))
        if path.is_file()
    }


def _write_cli_fixture(workspace: Path) -> Path:
    project = create_project(
        workspace, "医疗诊断推理", "medical-reasoning"
    )
    source = SourceRegistry(workspace / "library" / "sources.jsonl").add(
        "doi:10.1000/meeting-brief-cli"
    )
    link_project_sources(workspace, project.name, [source.source_id])
    (project / "00-research-brief.md").write_text(
        "# 医疗诊断推理\n\n问题已经确认。\n\n"
        "<!-- research-os:stage=brief-complete -->\n",
        encoding="utf-8",
    )
    (project / "02-evidence-ledger.yaml").write_text(
        f"""project: 医疗诊断推理
schema_version: 1
claims:
  - claim_id: C001
    statement: 公开基准报告了证据约束推理结果
    type: fact
    status: verified
    support:
      - source_id: {source.source_id}
        locator: p. 4, Table 2
    opposition: []
    confidence: medium
    limitations: 仅限公开基准，不能证明临床效用
""",
        encoding="utf-8",
    )
    return project


def test_meeting_brief_markdown_is_deterministic_and_read_only(
    tmp_path: Path, capsys
) -> None:
    project = _write_cli_fixture(tmp_path)
    before = _workspace_bytes(tmp_path)
    args = [
        "meeting-brief",
        "--project",
        project.name,
        "--as-of",
        "2026-08-12",
        "--workspace",
        str(tmp_path),
    ]

    assert main(args) == 0
    first = capsys.readouterr().out
    assert main(args) == 0
    second = capsys.readouterr().out

    assert first == second
    assert "## 已支持的结论" in first
    assert "source_id" in first
    assert "locator" in first
    assert "仅限公开基准，不能证明临床效用" in first
    assert _workspace_bytes(tmp_path) == before


def test_meeting_brief_json_has_stable_schema_and_bounded_decisions(
    tmp_path: Path, capsys
) -> None:
    project = _write_cli_fixture(tmp_path)

    assert main(
        [
            "meeting-brief",
            "--project",
            project.name,
            "--as-of",
            "2026-08-12",
            "--format",
            "json",
            "--workspace",
            str(tmp_path),
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema_version"] == 1
    assert payload["as_of"] == "2026-08-12"
    assert payload["project"]["slug"] == project.name
    assert payload["evidence"]["supported"][0]["claim_id"] == "C001"
    assert payload["evidence"]["supported"][0]["support"][0]["locator"] == (
        "p. 4, Table 2"
    )
    assert len(payload["discussion_questions"]) <= 3
    assert len(payload["actions"]) <= 3


def test_meeting_brief_invalid_date_returns_two(
    tmp_path: Path, capsys
) -> None:
    project = _write_cli_fixture(tmp_path)

    assert main(
        [
            "meeting-brief",
            "--project",
            project.name,
            "--as-of",
            "2026-02-30",
            "--workspace",
            str(tmp_path),
        ]
    ) == 2
    assert "--as-of 必须是 YYYY-MM-DD 日期" in capsys.readouterr().err
