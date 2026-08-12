import json
import os
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

import research_os.meeting_brief as meeting_brief_module
from research_os.cycle import advance_cycle, approve_active_cycle_idea
from research_os.ideas import (
    IdeaArchive,
    IdeaRecord,
    IdeaScores,
    NoveltyEvidence,
    save_idea_archive,
)
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


def _candidate(run_id: str, source_id: str, *, checked: bool) -> IdeaRecord:
    return IdeaRecord(
        idea_id="idea-0001",
        parent_ids=(),
        title="反证约束的医疗推理",
        scientific_question="显式反证门禁能否减少不受支持的诊断结论？",
        hypothesis="反证门禁将减少不受支持的诊断结论。",
        contribution="一种可证伪的医疗诊断推理证据门禁。",
        evidence_source_ids=(source_id,),
        novelty=NoveltyEvidence(
            status="checked" if checked else "pending",
            queries=("counterevidence medical diagnosis reasoning",) if checked else (),
            nearest_source_ids=(source_id,) if checked else (),
            differences="显式检查反证。" if checked else "",
            unresolved_overlap="" if checked else "需要检索。",
        ),
        scores=IdeaScores(8, 7, 7, 6),
        method_risks=("评价泄漏",),
        medical_safety_risks=("不能主张临床效用",),
        failure_criterion="Unsupported conclusions do not decrease.",
        external_experiment="只在独立公开基准仓库中比较。",
        status="draft",
        generated_by_run=run_id,
        provenance={"fixture": "meeting-brief"},
        researcher_decision=None,
    )


def _write_candidates(
    project: Path, run_id: str, source_id: str, *, checked: bool
) -> None:
    save_idea_archive(
        project / "cycles" / run_id / "candidates.yaml",
        IdeaArchive(
            1,
            project.name,
            (_candidate(run_id, source_id, checked=checked),),
        ),
    )


def _write_reviews(project: Path, run_id: str) -> None:
    reviews = project / "cycles" / run_id / "reviews"
    reviews.mkdir()
    assessment = {
        "idea_id": "idea-0001",
        "strengths": ["问题可证伪"],
        "concerns": ["必须限定为公开基准"],
        "blocking_issues": [],
        "recommendation": "advance",
        "confidence": 4,
    }
    for role in ("novelty", "methods", "medical-safety"):
        (reviews / f"{role}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "run_id": run_id,
                    "role": role,
                    "assessments": [assessment],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


def _write_meta_review(project: Path, run_id: str) -> None:
    (project / "cycles" / run_id / "meta-review.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_id,
                "consensus": ["问题可检验。"],
                "conflicts": [],
                "blocking_issues": [],
                "shortlist_ids": ["idea-0001"],
                "rationale_by_idea": {"idea-0001": "证据和成本权衡最好。"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _advance_and_approve_one_idea(
    workspace: Path, project: Path, source_id: str
) -> str:
    created = advance_cycle(workspace, project.name)
    _write_candidates(project, created.run_id, source_id, checked=False)
    advance_cycle(workspace, project.name)
    _write_candidates(project, created.run_id, source_id, checked=True)
    advance_cycle(workspace, project.name)
    _write_reviews(project, created.run_id)
    advance_cycle(workspace, project.name)
    _write_meta_review(project, created.run_id)
    assert advance_cycle(workspace, project.name).state == "awaiting_human_decision"
    approve_active_cycle_idea(
        workspace,
        project.name,
        "idea-0001",
        reason="Evidence and cost are acceptable.",
    )
    return created.run_id


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


def test_completed_idea_keeps_failure_boundary_and_human_reason(
    tmp_path: Path,
) -> None:
    project, source_id = _write_meeting_project(tmp_path)
    _write_claims(project, source_id)
    run_id = _advance_and_approve_one_idea(tmp_path, project, source_id)

    brief = build_meeting_brief(
        tmp_path,
        project.name,
        as_of=date(2026, 8, 12),
    )

    assert brief.ideas[0].run_id == run_id
    assert brief.ideas[0].failure_criterion == (
        "Unsupported conclusions do not decrease."
    )
    assert brief.ideas[0].decision_reason == "Evidence and cost are acceptable."
    assert any(
        item.code == "REVIEW_SELECTED_IDEA_BOUNDARY"
        for item in brief.questions
    )


def test_meeting_brief_exposes_human_idea_gate_explicitly(
    tmp_path: Path,
) -> None:
    project, source_id = _write_meeting_project(tmp_path)
    _write_claims(project, source_id)
    created = advance_cycle(tmp_path, project.name)
    _write_candidates(project, created.run_id, source_id, checked=False)
    advance_cycle(tmp_path, project.name)
    _write_candidates(project, created.run_id, source_id, checked=True)
    advance_cycle(tmp_path, project.name)
    _write_reviews(project, created.run_id)
    advance_cycle(tmp_path, project.name)
    _write_meta_review(project, created.run_id)
    assert advance_cycle(tmp_path, project.name).state == "awaiting_human_decision"

    brief = build_meeting_brief(
        tmp_path,
        project.name,
        as_of=date(2026, 8, 12),
    )

    assert brief.idea_state.run_id == created.run_id
    assert brief.idea_state.cycle_state == "awaiting_human_decision"
    assert brief.idea_state.human_decision_required is True
    assert brief.idea_state.selected_idea_ids == ()
    assert any(
        item.code == "REVIEW_IDEA_SHORTLIST"
        for item in brief.questions
    )


def test_meeting_brief_rejects_same_run_approval_after_dashboard_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, source_id = _write_meeting_project(tmp_path)
    _write_claims(project, source_id)
    created = advance_cycle(tmp_path, project.name)
    _write_candidates(project, created.run_id, source_id, checked=False)
    advance_cycle(tmp_path, project.name)
    _write_candidates(project, created.run_id, source_id, checked=True)
    advance_cycle(tmp_path, project.name)
    _write_reviews(project, created.run_id)
    advance_cycle(tmp_path, project.name)
    _write_meta_review(project, created.run_id)
    assert advance_cycle(tmp_path, project.name).state == "awaiting_human_decision"

    real_build_dashboard = meeting_brief_module.build_project_dashboard

    def approve_after_snapshot(*args: object, **kwargs: object) -> object:
        snapshot = real_build_dashboard(*args, **kwargs)
        approve_active_cycle_idea(
            tmp_path,
            project.name,
            "idea-0001",
            reason="Approved while the meeting brief was being built.",
        )
        return snapshot

    monkeypatch.setattr(
        meeting_brief_module,
        "build_project_dashboard",
        approve_after_snapshot,
    )

    with pytest.raises(ValueError, match="active cycle changed"):
        build_meeting_brief(
            tmp_path,
            project.name,
            as_of=date(2026, 8, 12),
        )


def test_meeting_brief_rejects_junction_backed_review_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, source_id = _write_meeting_project(tmp_path)
    _write_claims(project, source_id)
    created = advance_cycle(tmp_path, project.name)
    _write_candidates(project, created.run_id, source_id, checked=False)
    advance_cycle(tmp_path, project.name)
    _write_candidates(project, created.run_id, source_id, checked=True)
    advance_cycle(tmp_path, project.name)
    _write_reviews(project, created.run_id)
    advance_cycle(tmp_path, project.name)
    _write_meta_review(project, created.run_id)
    assert advance_cycle(tmp_path, project.name).state == "awaiting_human_decision"

    reviews = project / "cycles" / created.run_id / "reviews"
    outside = tmp_path / "outside-reviews"
    real_build_dashboard = meeting_brief_module.build_project_dashboard

    def replace_reviews_after_snapshot(*args: object, **kwargs: object) -> object:
        snapshot = real_build_dashboard(*args, **kwargs)
        reviews.replace(outside)
        try:
            if os.name == "nt":
                subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(reviews), str(outside)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            else:
                reviews.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"cannot create a directory link in this environment: {exc}")
        return snapshot

    monkeypatch.setattr(
        meeting_brief_module,
        "build_project_dashboard",
        replace_reviews_after_snapshot,
    )

    with pytest.raises(ValueError, match="link|reparse|artifact validation failed"):
        build_meeting_brief(
            tmp_path,
            project.name,
            as_of=date(2026, 8, 12),
        )


@pytest.mark.parametrize("replaced_directory", ["reviews", "run"])
def test_meeting_brief_rejects_same_content_cycle_directory_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replaced_directory: str,
) -> None:
    project, source_id = _write_meeting_project(tmp_path)
    _write_claims(project, source_id)
    created = advance_cycle(tmp_path, project.name)
    _write_candidates(project, created.run_id, source_id, checked=False)
    advance_cycle(tmp_path, project.name)
    _write_candidates(project, created.run_id, source_id, checked=True)
    advance_cycle(tmp_path, project.name)
    _write_reviews(project, created.run_id)
    advance_cycle(tmp_path, project.name)
    _write_meta_review(project, created.run_id)
    assert advance_cycle(tmp_path, project.name).state == "awaiting_human_decision"

    run_dir = project / "cycles" / created.run_id
    target = run_dir / "reviews" if replaced_directory == "reviews" else run_dir
    outside = tmp_path / f"original-{replaced_directory}"
    real_build_dashboard = meeting_brief_module.build_project_dashboard

    def replace_after_snapshot(*args: object, **kwargs: object) -> object:
        snapshot = real_build_dashboard(*args, **kwargs)
        target.replace(outside)
        shutil.copytree(outside, target)
        return snapshot

    monkeypatch.setattr(
        meeting_brief_module,
        "build_project_dashboard",
        replace_after_snapshot,
    )

    with pytest.raises(ValueError, match="active cycle changed"):
        build_meeting_brief(
            tmp_path,
            project.name,
            as_of=date(2026, 8, 12),
        )
