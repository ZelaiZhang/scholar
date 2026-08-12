from pathlib import Path

from research_os.guidance import guide_project, render_guide
from research_os.project import create_project, link_project_sources
from research_os.sources import SourceRegistry


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
        f"""project: A
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
""",
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


def test_new_project_recommends_research_brief(tmp_path: Path) -> None:
    create_project(tmp_path, "医疗推理", "medical-reasoning")

    report = guide_project(tmp_path, "medical-reasoning")

    assert report.next_action.skill == "research-project-init"
    assert report.next_action.target == "00-research-brief.md"
    assert report.stages[0].status == "未开始"


def test_edited_brief_without_linked_sources_recommends_intake(
    tmp_path: Path,
) -> None:
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


def test_invalid_evidence_blocks_idea_progression(tmp_path: Path) -> None:
    project = create_progressed_project_through_design(tmp_path)
    (project / "02-evidence-ledger.yaml").write_text(
        "claims: [broken", encoding="utf-8"
    )

    report = guide_project(tmp_path, project.name)

    assert report.next_action.skill is None
    assert "validate-ledger" in report.next_action.command
    assert any(stage.status == "受阻" for stage in report.stages)


def test_result_artifact_recommends_conservative_interpretation(
    tmp_path: Path,
) -> None:
    project = create_progressed_project_through_design(tmp_path)
    (project / "artifacts" / "aggregate-results.csv").write_text(
        "metric,value\naccuracy,0.8\n", encoding="utf-8"
    )

    report = guide_project(tmp_path, project.name)

    assert report.next_action.skill == "result-interpreter"
    assert report.next_action.target == "06-result-analysis.md"
    assert "$result-interpreter" in report.next_action.command


def test_render_guide_contains_exactly_one_next_action(tmp_path: Path) -> None:
    create_project(tmp_path, "A", "topic-a")

    rendered = render_guide(guide_project(tmp_path, "topic-a"))

    assert rendered.count("## 下一步") == 1
    assert "| 阶段 | 状态 | 说明 |" in rendered
