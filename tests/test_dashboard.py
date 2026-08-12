from datetime import date
from pathlib import Path

from research_os.dashboard import build_project_dashboard
from research_os.project import create_project, link_project_sources
from research_os.sources import SourceRegistry


def _write_ready_project(
    workspace: Path,
    *,
    title: str = "医疗推理",
    slug: str = "medical-reasoning",
    doi: str = "10.1000/medical-reasoning",
) -> tuple[Path, str]:
    project = create_project(workspace, title, slug)
    source = SourceRegistry(workspace / "library" / "sources.jsonl").add(
        f"doi:{doi}"
    )
    link_project_sources(workspace, slug, [source.source_id])
    (project / "00-research-brief.md").write_text(
        f"# {title}\n\n研究问题已经过人工确认。\n\n"
        "<!-- research-os:stage=brief-complete -->\n",
        encoding="utf-8",
    )
    (project / "02-evidence-ledger.yaml").write_text(
        f"""project: {title}
schema_version: 1
claims:
  - claim_id: C001
    statement: 论文报告了公开任务结果
    type: fact
    status: verified
    support:
      - source_id: {source.source_id}
        locator: p. 4
    opposition: []
    confidence: medium
    limitations: 仅限论文报告的数据集与任务设置
""",
        encoding="utf-8",
    )
    return project, source.source_id


def test_dashboard_reports_project_scoped_evidence(tmp_path: Path) -> None:
    _project, source_id = _write_ready_project(tmp_path)

    snapshot = build_project_dashboard(
        tmp_path,
        "medical-reasoning",
        as_of=date(2026, 8, 12),
    )

    assert snapshot.schema_version == 1
    assert snapshot.as_of == "2026-08-12"
    assert snapshot.project.slug == "medical-reasoning"
    assert snapshot.evidence.linked_sources == 1
    assert snapshot.evidence.verified_sources == 1
    assert snapshot.evidence.stale_or_unknown_source_ids == ()
    assert snapshot.evidence.claims == 1
    assert snapshot.evidence.support_links == 1
    assert snapshot.evidence.opposition_links == 0
    assert snapshot.evidence.conflicted_claims == 0
    assert snapshot.evidence.claims_with_limitations == 1
    assert snapshot.evidence.validation_issues == ()
    assert source_id not in snapshot.project.blockers


def test_dashboard_does_not_count_another_projects_sources(tmp_path: Path) -> None:
    _write_ready_project(
        tmp_path,
        title="课题 A",
        slug="topic-a",
        doi="10.1000/topic-a",
    )
    _write_ready_project(
        tmp_path,
        title="课题 B",
        slug="topic-b",
        doi="10.1000/topic-b",
    )

    snapshot = build_project_dashboard(
        tmp_path,
        "topic-a",
        as_of=date(2026, 8, 12),
    )

    assert snapshot.project.slug == "topic-a"
    assert snapshot.evidence.linked_sources == 1
    assert snapshot.evidence.verified_sources == 1
    assert snapshot.evidence.claims == 1
    assert snapshot.evidence.support_links == 1


def test_dashboard_marks_unknown_linked_source_as_blocking(tmp_path: Path) -> None:
    project = create_project(tmp_path, "失效来源课题", "stale-source")
    link_project_sources(tmp_path, "stale-source", ["src-missing"])
    (project / "02-evidence-ledger.yaml").write_text(
        "schema_version: 1\nclaims: []\n",
        encoding="utf-8",
    )

    snapshot = build_project_dashboard(
        tmp_path,
        "stale-source",
        as_of=date(2026, 8, 12),
    )

    assert snapshot.project.state == "blocked"
    assert snapshot.evidence.linked_sources == 1
    assert snapshot.evidence.verified_sources == 0
    assert snapshot.evidence.stale_or_unknown_source_ids == ("src-missing",)
    assert any("src-missing" in blocker for blocker in snapshot.project.blockers)
