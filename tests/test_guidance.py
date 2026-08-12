from pathlib import Path

import pytest

from research_os.guidance import guide_project, render_guide
from research_os.project import (
    InvalidSlugError,
    ProjectManifest,
    create_project,
    link_project_sources,
    write_project_manifest,
)
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
        f"# Paper\n\nsource_id: {record.source_id}\n",
        encoding="utf-8",
    )
    (project / "00-research-brief.md").write_text(
        "# A\n\n研究问题已由研究者填写。\n\n"
        "<!-- research-os:stage=brief-complete -->\n",
        encoding="utf-8",
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
    for filename, marker in (
        ("03-literature-review.md", "synthesis-complete"),
        ("04-idea-candidates.md", "idea-complete"),
        ("05-experiment-design.md", "design-complete"),
    ):
        (project / filename).write_text(
            f"# {filename}\n\n已由研究者填写。\n\n"
            f"<!-- research-os:stage={marker} -->\n",
            encoding="utf-8",
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
        "# A\n\n## 一句话研究问题\n方法 X 是否改善任务 Y？\n\n"
        "<!-- research-os:stage=brief-complete -->\n",
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
            f"# {title}\n\n研究问题已填写。\n\n"
            "<!-- research-os:stage=brief-complete -->\n",
            encoding="utf-8",
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


def test_guide_rejects_project_slug_path_traversal(tmp_path: Path) -> None:
    escaped = tmp_path / "escaped"
    escaped.mkdir()
    write_project_manifest(
        escaped,
        ProjectManifest(1, "Escaped", "escaped", "", ()),
    )
    (escaped / "02-evidence-ledger.yaml").write_text(
        "claims: []\n", encoding="utf-8"
    )

    with pytest.raises(InvalidSlugError):
        guide_project(tmp_path, "../escaped")


def test_evidence_source_must_be_linked_to_the_current_project(
    tmp_path: Path,
) -> None:
    project_a = create_project(tmp_path, "A", "topic-a")
    project_b = create_project(tmp_path, "B", "topic-b")
    registry = SourceRegistry(tmp_path / "library" / "sources.jsonl")
    source_a = registry.add("doi:10.1000/topic-a")
    source_b = registry.add("doi:10.1000/topic-b")
    link_project_sources(tmp_path, "topic-a", [source_a.source_id])
    link_project_sources(tmp_path, "topic-b", [source_b.source_id])
    papers = tmp_path / "library" / "papers"
    papers.mkdir(parents=True)
    (papers / "topic-b.md").write_text(
        f"# B paper\n\nsource_id: {source_b.source_id}\n", encoding="utf-8"
    )
    (project_b / "00-research-brief.md").write_text(
        "# B\n\n研究问题已确认。\n\n"
        "<!-- research-os:stage=brief-complete -->\n",
        encoding="utf-8",
    )
    (project_b / "02-evidence-ledger.yaml").write_text(
        f"""project: B
schema_version: 1
claims:
  - claim_id: C001
    statement: 错误引用了 A 课题的来源
    type: fact
    status: verified
    support:
      - source_id: {source_a.source_id}
        locator: p. 1
    opposition: []
    confidence: medium
    limitations: 仅用于隔离测试
""",
        encoding="utf-8",
    )
    (project_b / "03-literature-review.md").write_text(
        "# B：文献综合\n\n已整理。\n\n"
        "<!-- research-os:stage=synthesis-complete -->\n",
        encoding="utf-8",
    )

    report = guide_project(tmp_path, "topic-b")

    assert report.next_action.skill is None
    assert "validate-ledger" in report.next_action.command
    assert any(
        stage.name == "文献综合" and stage.status == "受阻"
        for stage in report.stages
    )
    assert project_a.is_dir()


def test_single_character_edit_does_not_complete_idea_stage(
    tmp_path: Path,
) -> None:
    project = create_progressed_project_through_design(tmp_path)
    idea = project / "04-idea-candidates.md"
    idea.write_text("# A：Idea 候选与反向审查\n\nx\n", encoding="utf-8")
    design = project / "05-experiment-design.md"
    design.write_text("# still untouched by guide\n", encoding="utf-8")

    report = guide_project(tmp_path, project.name)

    idea_stage = next(stage for stage in report.stages if stage.name == "Idea 审查")
    assert idea_stage.status == "进行中"
    assert report.next_action.skill == "idea-review"


def test_unknown_linked_source_gives_actionable_intake_fix_not_ledger_loop(
    tmp_path: Path,
) -> None:
    project = create_project(tmp_path, "A", "topic-a")
    (project / "00-research-brief.md").write_text(
        "# A\n\n已填写。\n\n<!-- research-os:stage=brief-complete -->\n",
        encoding="utf-8",
    )
    link_project_sources(tmp_path, "topic-a", ["src-missing"])

    report = guide_project(tmp_path, "topic-a")

    assert report.next_action.skill == "paper-intake"
    assert "validate-ledger" not in report.next_action.command
    assert "src-missing" in report.next_action.command
