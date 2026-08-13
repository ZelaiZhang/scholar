import json
import hashlib
from datetime import date
from pathlib import Path

import pytest

import research_os.dashboard as dashboard_module
from research_os.cli import main
from research_os.manuscript_plan import build_manuscript_plan
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


@pytest.mark.parametrize(
    "analysis_body",
    (
        "```markdown\n{binding}\n{marker}\n```",
        "<!-- archived example\n{binding}\n{marker}\n-->",
        "<!-- first --><!-- archived example\n{binding}\n{marker}\n-->",
        "    {binding}\n    {marker}",
        "{marker}\n{binding}",
        "{binding}\n{marker}\n{marker}",
    ),
)
def test_manuscript_plan_keeps_results_partial_for_non_live_or_invalid_completion(
    tmp_path: Path,
    analysis_body: str,
) -> None:
    project = _write_fixture(tmp_path)
    (project / "05-experiment-design.md").write_text(
        "# Experiment design\n\nReviewed design.\n\n"
        "<!-- research-os:stage=design-complete -->\n",
        encoding="utf-8",
    )
    result = project / "artifacts" / "aggregate-results.csv"
    result.write_text("metric,value\naccuracy,0.8\n", encoding="utf-8")
    digest = hashlib.sha256(result.read_bytes()).hexdigest()
    (project / "artifacts" / "results-manifest.yaml").write_text(
        "schema_version: 1\nresults:\n"
        "  - path: aggregate-results.csv\n"
        f"    sha256: {digest}\n"
        "    source_repository: public-experiment-repository\n"
        "    generated_at: '2026-08-13T00:00:00Z'\n",
        encoding="utf-8",
    )
    binding = (
        "<!-- research-os:result-input name=aggregate-results.csv; "
        f"sha256={digest} -->"
    )
    (project / "06-result-analysis.md").write_text(
        "# Result analysis\n\nHuman interpretation.\n\n"
        + analysis_body.format(
            binding=binding,
            marker="<!-- research-os:stage=result-complete -->",
        )
        + "\n",
        encoding="utf-8",
    )

    plan = build_manuscript_plan(
        tmp_path,
        project.name,
        as_of=date(2026, 8, 13),
    )
    results = next(section for section in plan.sections if section.code == "results")

    assert results.status == "partial"
    assert "RESULT_INTERPRETATION_INCOMPLETE" in results.reason_codes


def test_manuscript_plan_rejects_stage_document_changed_after_guide(
    tmp_path: Path, monkeypatch
) -> None:
    project = _write_fixture(tmp_path)
    result_path = project / "06-result-analysis.md"
    result_path.write_text(
        "# Result analysis\n\nReviewed.\n\n"
        "<!-- research-os:stage=result-complete -->\n",
        encoding="utf-8",
    )
    original = dashboard_module.guide_project

    def changing_guide(*args, **kwargs):
        report = original(*args, **kwargs)
        result_path.write_text(
            "# Result analysis\n\nChanged after stage capture.\n",
            encoding="utf-8",
        )
        return report

    monkeypatch.setattr(dashboard_module, "guide_project", changing_guide)

    with pytest.raises(OSError, match="stage document"):
        build_manuscript_plan(tmp_path, project.name, as_of=date(2026, 8, 13))


def test_manuscript_plan_rejects_same_content_stage_document_replacement(
    tmp_path: Path, monkeypatch
) -> None:
    project = _write_fixture(tmp_path)
    result_path = project / "06-result-analysis.md"
    result_path.write_text("# Result analysis\n\nStable text.\n", encoding="utf-8")
    original = dashboard_module.guide_project

    def changing_guide(*args, **kwargs):
        report = original(*args, **kwargs)
        replacement = project / "result-replacement.tmp"
        replacement.write_bytes(result_path.read_bytes())
        replacement.replace(result_path)
        return report

    monkeypatch.setattr(dashboard_module, "guide_project", changing_guide)

    with pytest.raises(OSError, match="stage document"):
        build_manuscript_plan(tmp_path, project.name, as_of=date(2026, 8, 13))


def test_manuscript_plan_rejects_result_inputs_changed_after_guide(
    tmp_path: Path, monkeypatch
) -> None:
    project = _write_fixture(tmp_path)
    result_path = project / "artifacts" / "aggregate-results.csv"
    result_path.write_text("metric,value\naccuracy,0.8\n", encoding="utf-8")
    digest = hashlib.sha256(result_path.read_bytes()).hexdigest()
    manifest_path = project / "artifacts" / "results-manifest.yaml"
    manifest_path.write_text(
        "schema_version: 1\nresults:\n"
        "  - path: aggregate-results.csv\n"
        f"    sha256: {digest}\n"
        "    source_repository: public-experiment-repository\n"
        "    generated_at: '2026-08-13T00:00:00Z'\n",
        encoding="utf-8",
    )
    original = dashboard_module.guide_project

    def changing_guide(*args, **kwargs):
        report = original(*args, **kwargs)
        manifest_path.write_text("schema_version: 1\nresults: []\n", encoding="utf-8")
        return report

    monkeypatch.setattr(dashboard_module, "guide_project", changing_guide)

    with pytest.raises(OSError, match="result inputs"):
        build_manuscript_plan(tmp_path, project.name, as_of=date(2026, 8, 13))


def test_manuscript_plan_rejects_same_content_result_manifest_replacement(
    tmp_path: Path, monkeypatch
) -> None:
    project = _write_fixture(tmp_path)
    result_path = project / "artifacts" / "aggregate-results.csv"
    result_path.write_text("metric,value\naccuracy,0.8\n", encoding="utf-8")
    digest = hashlib.sha256(result_path.read_bytes()).hexdigest()
    manifest_path = project / "artifacts" / "results-manifest.yaml"
    manifest_path.write_text(
        "schema_version: 1\nresults:\n"
        "  - path: aggregate-results.csv\n"
        f"    sha256: {digest}\n"
        "    source_repository: public-experiment-repository\n"
        "    generated_at: '2026-08-13T00:00:00Z'\n",
        encoding="utf-8",
    )
    original = dashboard_module.guide_project

    def changing_guide(*args, **kwargs):
        report = original(*args, **kwargs)
        replacement = manifest_path.with_suffix(".replacement")
        replacement.write_bytes(manifest_path.read_bytes())
        replacement.replace(manifest_path)
        return report

    monkeypatch.setattr(dashboard_module, "guide_project", changing_guide)

    with pytest.raises(OSError, match="result inputs"):
        build_manuscript_plan(tmp_path, project.name, as_of=date(2026, 8, 13))
