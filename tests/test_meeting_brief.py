import shutil
from datetime import date
from pathlib import Path

import pytest

import research_os.meeting_brief as meeting_brief_module
from research_os.meeting_brief import build_meeting_brief
from research_os.project import create_project, link_project_sources
from research_os.sources import SourceRegistry


def _write_meeting_project(
    workspace: Path,
    *,
    title: str = "医疗诊断推理",
    slug: str = "medical-reasoning",
) -> tuple[Path, str]:
    project = create_project(workspace, title, slug)
    source = SourceRegistry(workspace / "library" / "sources.jsonl").add(
        "doi:10.1000/meeting-brief"
    )
    link_project_sources(workspace, slug, [source.source_id])
    (project / "00-research-brief.md").write_text(
        f"# {title}\n\n研究问题已经过人工确认。\n\n"
        "<!-- research-os:stage=brief-complete -->\n",
        encoding="utf-8",
    )
    return project, source.source_id


def _write_claims(project: Path, source_id: str) -> None:
    (project / "02-evidence-ledger.yaml").write_text(
        f"""project: 医疗诊断推理
schema_version: 1
claims:
  - claim_id: C001
    statement: 公开基准上证据约束减少了不受支持的诊断结论
    type: fact
    status: verified
    support:
      - source_id: {source_id}
        locator: p. 4, Table 2
    opposition: []
    confidence: medium
    limitations: 仅限公开基准，不能证明临床效用
  - claim_id: C002
    statement: 推理轨迹监督是否稳定改善诊断表现仍有冲突
    type: fact
    status: conflicted
    support:
      - source_id: {source_id}
        locator: p. 5, Results
    opposition:
      - source_id: {source_id}
        locator: p. 7, Ablation
    confidence: low
    limitations: 支持与反对结果来自不同设置
  - claim_id: C003
    statement: 显式反证搜索可能提高推理可靠性
    type: hypothesis
    status: unverified
    support: []
    opposition: []
    confidence: low
    limitations: 尚未在独立实验中检验
  - claim_id: C004
    statement: 这条记录缺少可复核定位
    type: fact
    status: verified
    support:
      - source_id: {source_id}
        locator: ""
    opposition: []
    confidence: medium
    limitations: 定位缺失，不能进入简报结论
""",
        encoding="utf-8",
    )


def test_meeting_brief_routes_claims_without_promoting_invalid_evidence(
    tmp_path: Path,
) -> None:
    project, source_id = _write_meeting_project(tmp_path)
    _write_claims(project, source_id)

    brief = build_meeting_brief(
        tmp_path, project.name, as_of=date(2026, 8, 12)
    )

    assert [item.claim_id for item in brief.supported_claims] == ["C001"]
    assert [item.claim_id for item in brief.conflicted_claims] == ["C002"]
    assert [item.claim_id for item in brief.open_claims] == ["C003"]
    assert {item.claim_id for item in brief.excluded_claims} == {"C004"}
    assert brief.supported_claims[0].support[0].locator == "p. 4, Table 2"
    assert brief.supported_claims[0].limitations == (
        "仅限公开基准，不能证明临床效用"
    )


def test_meeting_brief_rejects_project_replacement_after_dashboard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, source_id = _write_meeting_project(tmp_path)
    _write_claims(project, source_id)
    moved = tmp_path / "moved-medical-reasoning"
    original_builder = meeting_brief_module.build_project_dashboard

    def replace_after_dashboard(*args: object, **kwargs: object):
        snapshot = original_builder(*args, **kwargs)
        project.rename(moved)
        shutil.copytree(moved, project)
        return snapshot

    monkeypatch.setattr(
        meeting_brief_module,
        "build_project_dashboard",
        replace_after_dashboard,
    )

    with pytest.raises(OSError):
        build_meeting_brief(
            tmp_path,
            project.name,
            as_of=date(2026, 8, 12),
        )
