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


def _write_fixture(workspace: Path) -> Path:
    project = create_project(workspace, "Public medical reasoning", "topic-a")
    source = SourceRegistry(workspace / "library" / "sources.jsonl").add(
        "doi:10.1000/manuscript-plan-cli"
    )
    link_project_sources(workspace, project.name, [source.source_id])
    (project / "00-research-brief.md").write_text(
        "# Public medical reasoning\n\nProblem definition is complete.\n\n"
        "<!-- research-os:stage=brief-complete -->\n",
        encoding="utf-8",
    )
    (project / "02-evidence-ledger.yaml").write_text(
        f"""project: Public medical reasoning
schema_version: 1
claims:
  - claim_id: C001
    statement: A public benchmark reported an evidence-bound result.
    type: fact
    status: verified
    support:
      - source_id: {source.source_id}
        locator: p. 4, Table 2
    opposition: []
    confidence: medium
    limitations: Public benchmark only; no clinical utility claim.
""",
        encoding="utf-8",
    )
    return project


def test_manuscript_plan_json_is_read_only_and_has_one_action(
    tmp_path: Path, capsys
) -> None:
    project = _write_fixture(tmp_path)
    before = _workspace_bytes(tmp_path)

    assert main(
        [
            "manuscript-plan",
            "--project",
            project.name,
            "--as-of",
            "2026-08-13",
            "--format",
            "json",
            "--workspace",
            str(tmp_path),
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["project"]["slug"] == "topic-a"
    assert payload["as_of"] == "2026-08-13"
    assert len(payload["sections"]) == 8
    assert len(payload["next_actions"]) == 1
    assert _workspace_bytes(tmp_path) == before


def test_manuscript_plan_markdown_is_deterministic(
    tmp_path: Path, capsys
) -> None:
    project = _write_fixture(tmp_path)
    args = [
        "manuscript-plan",
        "--project",
        project.name,
        "--as-of",
        "2026-08-13",
        "--workspace",
        str(tmp_path),
    ]

    assert main(args) == 0
    first = capsys.readouterr().out
    assert main(args) == 0
    second = capsys.readouterr().out

    assert first == second
    assert "# 论文就绪计划" in first
    assert "p. 4, Table 2" in first
    assert "## 唯一下一步" in first


def test_manuscript_plan_invalid_date_returns_two(tmp_path: Path, capsys) -> None:
    project = _write_fixture(tmp_path)

    assert main(
        [
            "manuscript-plan",
            "--project",
            project.name,
            "--as-of",
            "2026-02-30",
            "--workspace",
            str(tmp_path),
        ]
    ) == 2
    assert "--as-of" in capsys.readouterr().err


def test_manuscript_plan_broken_evidence_returns_two(tmp_path: Path, capsys) -> None:
    project = _write_fixture(tmp_path)
    (project / "02-evidence-ledger.yaml").write_text(
        "project: [broken", encoding="utf-8"
    )

    assert main(
        [
            "manuscript-plan",
            "--project",
            project.name,
            "--workspace",
            str(tmp_path),
        ]
    ) == 2
    assert capsys.readouterr().err
