import json
import os
import shutil
import subprocess
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
import yaml

from research_os.cycle import (
    advance_cycle,
    approve_active_cycle_idea,
    load_cycle_manifest,
    save_cycle_manifest,
)
import research_os.dashboard as dashboard_module
from research_os.dashboard import build_project_dashboard
from research_os.dashboard_risks import RiskFacts, evaluate_dashboard_risks
from research_os.ideas import (
    IdeaArchive,
    IdeaRecord,
    IdeaScores,
    NoveltyEvidence,
    save_idea_archive,
)
from research_os.guidance import guide_project
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


def _idea(run_id: str, source_id: str, *, checked: bool) -> IdeaRecord:
    return IdeaRecord(
        idea_id="idea-0001",
        parent_ids=(),
        title="反证约束的医疗推理",
        scientific_question="显式反证门禁能否减少不受支持的结论？",
        hypothesis="反证门禁将减少不受支持的结论。",
        contribution="一种可证伪的医疗推理证据门禁。",
        evidence_source_ids=(source_id,),
        novelty=NoveltyEvidence(
            status="checked" if checked else "pending",
            queries=("counterevidence medical reasoning",) if checked else (),
            nearest_source_ids=(source_id,) if checked else (),
            differences="显式检查反证。" if checked else "",
            unresolved_overlap="" if checked else "需要检索。",
        ),
        scores=IdeaScores(8, 7, 7, 6),
        method_risks=("评价泄漏",),
        medical_safety_risks=("不主张临床有效性",),
        failure_criterion="不受支持的结论没有减少。",
        external_experiment="在独立公开基准仓库中比较。",
        status="draft",
        generated_by_run=run_id,
        provenance={"generator": "local", "response_sha256": "a" * 64},
        researcher_decision=None,
    )


def _write_candidates(
    project: Path,
    run_id: str,
    source_id: str,
    *,
    checked: bool,
) -> None:
    save_idea_archive(
        project / "cycles" / run_id / "candidates.yaml",
        IdeaArchive(1, project.name, (_idea(run_id, source_id, checked=checked),)),
    )


def _write_reviews(project: Path, run_id: str) -> None:
    reviews = project / "cycles" / run_id / "reviews"
    reviews.mkdir()
    assessment = {
        "idea_id": "idea-0001",
        "strengths": ["可证伪"],
        "concerns": ["需要限定范围"],
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
                "consensus": ["Idea 可检验。"],
                "conflicts": [],
                "blocking_issues": [],
                "shortlist_ids": ["idea-0001"],
                "rationale_by_idea": {"idea-0001": "证据与成本权衡最好。"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _advance_to_human_decision(
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
    final = advance_cycle(workspace, project.name)
    assert final.state == "awaiting_human_decision"
    return created.run_id


def _write_minimal_knowledge_base(workspace: Path) -> None:
    root = workspace / "library" / "knowledge"
    root.mkdir(parents=True)
    (root / "playbooks").mkdir()
    method = SourceRegistry(workspace / "library" / "sources.jsonl").add(
        "doi:10.1000/dashboard-method"
    )
    catalog = {
        "schema_version": 1,
        "entries": [
            {
                "source_id": method.source_id,
                "canonical": method.canonical,
                "title": "可复核的模型评价方法",
                "authors": ["Methods Group"],
                "year": 2025,
                "source_type": "paper",
                "venue": "Methods Journal",
                "topics": ["evaluation"],
                "methods": ["model-evaluation"],
                "stages": ["problem-definition", "experiment-design"],
                "priority": "core",
                "verification": {
                    "metadata": "verified",
                    "abstract": "verified",
                    "fulltext": "unverified",
                },
                "reviewed_at": "2026-08-12",
                "status": "active",
                "superseded_by": "",
                "access_url": "https://doi.org/10.1000/dashboard-method",
                "license": "unknown",
                "notes": "",
            }
        ],
    }
    (root / "catalog.yaml").write_text(
        yaml.safe_dump(catalog, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (root / "aliases.yaml").write_text(
        "schema_version: 1\naliases: {}\n",
        encoding="utf-8",
    )
    (root / "playbooks" / "evaluation-and-ablation.md").write_text(
        "# 评价与消融方法手册\n",
        encoding="utf-8",
    )


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


def test_dashboard_carries_internal_stage_snapshot(tmp_path: Path) -> None:
    project, _source_id = _write_ready_project(tmp_path)

    snapshot = build_project_dashboard(
        tmp_path,
        project.name,
        as_of=date(2026, 8, 13),
    )

    assert snapshot.stages == guide_project(tmp_path, project.name).stages
    assert snapshot.stages[0].code == "problem_definition"


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


def test_dashboard_reports_empty_and_active_idea_states(tmp_path: Path) -> None:
    project, _source_id = _write_ready_project(tmp_path)

    empty = build_project_dashboard(
        tmp_path, project.name, as_of=date(2026, 8, 12)
    )
    assert empty.idea.run_id == ""
    assert empty.idea.cycle_state == "not_started"
    assert empty.idea.candidate_count == 0
    assert empty.idea.selected_idea_ids == ()
    assert empty.idea.human_decision_required is False
    assert empty.idea.candidate_generation_complete is False
    assert empty.idea.novelty_check_complete is False
    assert empty.idea.independent_review_complete is False
    assert empty.idea.meta_review_complete is False

    created = advance_cycle(tmp_path, project.name, max_ideas=4, max_calls=6)
    active = build_project_dashboard(
        tmp_path, project.name, as_of=date(2026, 8, 12)
    )
    assert active.idea.run_id == created.run_id
    assert active.idea.cycle_state == "candidate_generation"
    assert active.idea.candidate_count == 0
    assert active.idea.calls_used == 0
    assert active.idea.max_calls == 6
    assert active.idea.candidate_generation_complete is False
    assert active.idea.novelty_check_complete is False
    assert active.idea.independent_review_complete is False
    assert active.idea.meta_review_complete is False


def test_dashboard_exposes_each_validated_idea_gate(tmp_path: Path) -> None:
    project, source_id = _write_ready_project(tmp_path)
    created = advance_cycle(tmp_path, project.name)

    _write_candidates(project, created.run_id, source_id, checked=False)
    assert advance_cycle(tmp_path, project.name).state == "novelty_check"
    novelty = build_project_dashboard(
        tmp_path, project.name, as_of=date(2026, 8, 12)
    ).idea
    assert novelty.candidate_generation_complete is True
    assert novelty.novelty_check_complete is False
    assert novelty.independent_review_complete is False
    assert novelty.meta_review_complete is False

    _write_candidates(project, created.run_id, source_id, checked=True)
    assert advance_cycle(tmp_path, project.name).state == "independent_review"
    independent = build_project_dashboard(
        tmp_path, project.name, as_of=date(2026, 8, 12)
    ).idea
    assert independent.candidate_generation_complete is True
    assert independent.novelty_check_complete is True
    assert independent.independent_review_complete is False
    assert independent.meta_review_complete is False

    _write_reviews(project, created.run_id)
    assert advance_cycle(tmp_path, project.name).state == "meta_review"
    meta = build_project_dashboard(
        tmp_path, project.name, as_of=date(2026, 8, 12)
    ).idea
    assert meta.candidate_generation_complete is True
    assert meta.novelty_check_complete is True
    assert meta.independent_review_complete is True
    assert meta.meta_review_complete is False

    _write_meta_review(project, created.run_id)
    assert advance_cycle(tmp_path, project.name).state == "awaiting_human_decision"
    human = build_project_dashboard(
        tmp_path, project.name, as_of=date(2026, 8, 12)
    ).idea
    assert human.candidate_generation_complete is True
    assert human.novelty_check_complete is True
    assert human.independent_review_complete is True
    assert human.meta_review_complete is True


def test_dashboard_does_not_report_gate_ready_when_frozen_artifact_changed(
    tmp_path: Path,
) -> None:
    project, source_id = _write_ready_project(tmp_path)
    created = advance_cycle(tmp_path, project.name)
    _write_candidates(project, created.run_id, source_id, checked=False)
    assert advance_cycle(tmp_path, project.name).state == "novelty_check"
    candidates = project / "cycles" / created.run_id / "candidates.yaml"
    candidates.write_text(
        candidates.read_text(encoding="utf-8") + "# changed after freeze\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="科研循环产物校验失败"):
        build_project_dashboard(
            tmp_path,
            project.name,
            as_of=date(2026, 8, 12),
        )


def test_dashboard_rejects_novelty_gate_without_checked_candidates(
    tmp_path: Path,
) -> None:
    project, source_id = _write_ready_project(tmp_path)
    created = advance_cycle(tmp_path, project.name)
    _write_candidates(project, created.run_id, source_id, checked=False)
    assert advance_cycle(tmp_path, project.name).state == "novelty_check"
    manifest_path = project / "cycles" / created.run_id / "manifest.yaml"
    manifest = load_cycle_manifest(manifest_path)
    save_cycle_manifest(
        manifest_path,
        replace(manifest, state="independent_review"),
    )

    with pytest.raises(ValueError, match="novelty|新颖性"):
        build_project_dashboard(
            tmp_path,
            project.name,
            as_of=date(2026, 8, 12),
        )


def test_dashboard_reports_human_decision_and_selected_idea(tmp_path: Path) -> None:
    project, source_id = _write_ready_project(tmp_path)
    run_id = _advance_to_human_decision(tmp_path, project, source_id)

    awaiting = build_project_dashboard(
        tmp_path, project.name, as_of=date(2026, 8, 12)
    )
    assert awaiting.idea.run_id == run_id
    assert awaiting.idea.cycle_state == "awaiting_human_decision"
    assert awaiting.idea.candidate_count == 1
    assert awaiting.idea.human_decision_required is True
    assert awaiting.idea.selected_idea_ids == ()
    assert awaiting.idea.candidate_generation_complete is True
    assert awaiting.idea.novelty_check_complete is True
    assert awaiting.idea.independent_review_complete is True
    assert awaiting.idea.meta_review_complete is True

    approve_active_cycle_idea(
        tmp_path,
        project.name,
        "idea-0001",
        reason="研究者确认该问题值得推进",
    )
    selected = build_project_dashboard(
        tmp_path, project.name, as_of=date(2026, 8, 12)
    )
    assert selected.idea.cycle_state == "completed"
    assert selected.idea.human_decision_required is False
    assert selected.idea.selected_idea_ids == ("idea-0001",)


def test_risks_expose_observed_trigger_without_guessing() -> None:
    facts = RiskFacts(
        stale_source_ids=("src-stale",),
        ledger_issue_codes=("missing_locator",),
        cycle_state="",
        human_decision_required=False,
        profile_domains=(),
        profile_tracks=(),
        experiment_design_status="未开始",
    )

    risks = evaluate_dashboard_risks(facts)

    assert [(risk.code, risk.state) for risk in risks] == [
        ("EVIDENCE_SOURCE_STALE", "observed"),
        ("EVIDENCE_LOCATOR_MISSING", "observed"),
    ]
    assert all(risk.trigger for risk in risks)


def test_risks_only_apply_medical_and_adaptation_rules_from_profile() -> None:
    unknown = evaluate_dashboard_risks(
        RiskFacts(
            stale_source_ids=(),
            ledger_issue_codes=(),
            cycle_state="",
            human_decision_required=False,
            profile_domains=(),
            profile_tracks=(),
            experiment_design_status="未开始",
        )
    )
    assert unknown == ()

    applicable = evaluate_dashboard_risks(
        RiskFacts(
            stale_source_ids=(),
            ledger_issue_codes=(),
            cycle_state="",
            human_decision_required=False,
            profile_domains=("medical-ai",),
            profile_tracks=("quantization",),
            experiment_design_status="进行中",
        )
    )
    assert [(risk.code, risk.state) for risk in applicable] == [
        ("MEDICAL_DESIGN_GATE_INCOMPLETE", "missing_required"),
        ("MODEL_ADAPTATION_DESIGN_INCOMPLETE", "missing_required"),
    ]
    assert all("进行中" in risk.trigger for risk in applicable)


def test_dashboard_reuses_stage_aware_method_recommendations(tmp_path: Path) -> None:
    project, _source_id = _write_ready_project(tmp_path)
    _write_minimal_knowledge_base(tmp_path)

    guide = guide_project(tmp_path, project.name)
    snapshot = build_project_dashboard(
        tmp_path, project.name, as_of=date(2026, 8, 12)
    )

    assert 1 <= len(snapshot.recommendations) <= 3
    assert snapshot.recommendations == guide.method_references
    assert snapshot.recommendations[-1].kind == "profile-hint"
    assert all(item.cannot_use_for for item in snapshot.recommendations)


def test_actions_prioritize_repair_then_workflow_then_methods(
    tmp_path: Path,
) -> None:
    project = create_project(tmp_path, "失效来源课题", "stale-source")
    link_project_sources(tmp_path, "stale-source", ["src-missing"])
    (project / "02-evidence-ledger.yaml").write_text(
        "schema_version: 1\nclaims: []\n",
        encoding="utf-8",
    )
    _write_minimal_knowledge_base(tmp_path)

    snapshot = build_project_dashboard(
        tmp_path, project.name, as_of=date(2026, 8, 12)
    )

    assert 1 <= len(snapshot.actions) <= 3
    assert snapshot.actions[0].category == "repair"
    assert snapshot.actions[-1].category == "methodology"
    assert [action.priority for action in snapshot.actions] == sorted(
        action.priority for action in snapshot.actions
    )
    assert len({action.command for action in snapshot.actions}) == len(
        snapshot.actions
    )
    assert all(
        action.rationale and action.expected_artifact
        for action in snapshot.actions
    )
    assert snapshot.actions[0].command == guide_project(
        tmp_path, project.name
    ).next_action.command


def test_action_commands_never_include_evidence_statements(tmp_path: Path) -> None:
    project, source_id = _write_ready_project(tmp_path)
    sentinel = "DO-NOT-EXECUTE-EVIDENCE-TEXT"
    ledger = project / "02-evidence-ledger.yaml"
    ledger.write_text(
        ledger.read_text(encoding="utf-8").replace(
            "论文报告了公开任务结果", sentinel
        ),
        encoding="utf-8",
    )
    _write_minimal_knowledge_base(tmp_path)

    snapshot = build_project_dashboard(
        tmp_path, project.name, as_of=date(2026, 8, 12)
    )

    assert source_id
    assert len(snapshot.actions) <= 3
    assert all(sentinel not in action.command for action in snapshot.actions)


@pytest.mark.parametrize("filename", ["project.yaml", "02-evidence-ledger.yaml"])
def test_dashboard_rejects_linked_direct_project_file(
    tmp_path: Path, filename: str
) -> None:
    project = create_project(tmp_path, "Linked", "linked-project")
    original = project / filename
    outside = tmp_path / f"outside-{filename}"
    outside.write_bytes(original.read_bytes())
    original.unlink()
    try:
        original.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"当前环境不能创建文件符号链接: {exc}")

    with pytest.raises(ValueError, match="符号链接|目录联接"):
        build_project_dashboard(
            tmp_path,
            project.name,
            as_of=date(2026, 8, 12),
        )


def test_dashboard_rejects_idea_directory_link(tmp_path: Path) -> None:
    project, _source_id = _write_ready_project(tmp_path)
    advance_cycle(tmp_path, project.name)
    ideas = project / "ideas"
    outside = tmp_path / "outside-ideas"
    ideas.rename(outside)
    try:
        if os.name == "nt":
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(ideas), str(outside)],
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            ideas.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"当前环境不能创建目录链接: {exc}")

    with pytest.raises(ValueError, match="符号链接|目录联接"):
        build_project_dashboard(
            tmp_path,
            project.name,
            as_of=date(2026, 8, 12),
        )


def test_dashboard_excludes_invalid_claim_from_healthy_counts(
    tmp_path: Path,
) -> None:
    project, _source_id = _write_ready_project(tmp_path)
    ledger = project / "02-evidence-ledger.yaml"
    ledger.write_text(
        ledger.read_text(encoding="utf-8").replace(
            "statement: 论文报告了公开任务结果",
            "statement: ''",
        ),
        encoding="utf-8",
    )

    snapshot = build_project_dashboard(
        tmp_path,
        project.name,
        as_of=date(2026, 8, 12),
    )

    assert any(
        issue.code == "missing_statement"
        for issue in snapshot.evidence.validation_issues
    )
    assert snapshot.evidence.claims == 0
    assert snapshot.evidence.support_links == 0
    assert snapshot.evidence.opposition_links == 0
    assert snapshot.evidence.conflicted_claims == 0
    assert snapshot.evidence.claims_with_limitations == 0


def test_dashboard_rejects_idea_archive_from_another_project(
    tmp_path: Path,
) -> None:
    project, _source_id = _write_ready_project(tmp_path)
    advance_cycle(tmp_path, project.name)
    archive = project / "ideas" / "archive.yaml"
    archive.write_text(
        archive.read_text(encoding="utf-8").replace(
            f"project_slug: {project.name}",
            "project_slug: another-project",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Idea archive.*another-project|不同课题"):
        build_project_dashboard(
            tmp_path,
            project.name,
            as_of=date(2026, 8, 12),
        )


def test_dashboard_rechecks_ledger_at_read_time_after_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _source_id = _write_ready_project(tmp_path)
    ledger = project / "02-evidence-ledger.yaml"
    outside = tmp_path / "outside-ledger.yaml"
    outside.write_bytes(ledger.read_bytes())
    original_preflight = dashboard_module._preflight_project_inputs

    def swap_after_preflight(project_path: Path) -> None:
        original_preflight(project_path)
        ledger.unlink()
        ledger.symlink_to(outside)

    monkeypatch.setattr(
        dashboard_module,
        "_preflight_project_inputs",
        swap_after_preflight,
    )

    with pytest.raises(ValueError, match="符号链接|目录联接"):
        build_project_dashboard(
            tmp_path,
            project.name,
            as_of=date(2026, 8, 12),
        )


def test_dashboard_rejects_same_name_project_directory_replacement_before_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _source_id = _write_ready_project(tmp_path)
    moved = tmp_path / "moved-project"
    original_preflight = dashboard_module._preflight_project_inputs
    original_loader = dashboard_module.load_project_manifest
    loader_called_after_replacement = False

    def replace_after_preflight(project_path: Path) -> None:
        original_preflight(project_path)
        project_path.rename(moved)
        shutil.copytree(moved, project_path)

    def tracked_loader(*args: object, **kwargs: object):
        nonlocal loader_called_after_replacement
        loader_called_after_replacement = True
        return original_loader(*args, **kwargs)

    monkeypatch.setattr(
        dashboard_module,
        "_preflight_project_inputs",
        replace_after_preflight,
    )
    monkeypatch.setattr(
        dashboard_module,
        "load_project_manifest",
        tracked_loader,
    )

    with pytest.raises(OSError):
        build_project_dashboard(
            tmp_path,
            project.name,
            as_of=date(2026, 8, 12),
        )

    assert loader_called_after_replacement is False


def test_dashboard_rejects_project_directory_replacement_after_manifest_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _source_id = _write_ready_project(tmp_path)
    moved = tmp_path / "moved-project-after-manifest"
    original_loader = dashboard_module.load_project_manifest

    def replace_after_manifest(*args: object, **kwargs: object):
        manifest = original_loader(*args, **kwargs)
        project.rename(moved)
        shutil.copytree(moved, project)
        return manifest

    monkeypatch.setattr(
        dashboard_module,
        "load_project_manifest",
        replace_after_manifest,
    )

    with pytest.raises(OSError):
        build_project_dashboard(
            tmp_path,
            project.name,
            as_of=date(2026, 8, 12),
        )


def test_dashboard_accepts_captured_project_identity(tmp_path: Path) -> None:
    project, _source_id = _write_ready_project(tmp_path)
    expected = (project.stat().st_dev, project.stat().st_ino)

    snapshot = build_project_dashboard(
        tmp_path,
        project.name,
        as_of=date(2026, 8, 12),
        expected_project_identity=expected,
    )

    assert snapshot.project.slug == project.name
