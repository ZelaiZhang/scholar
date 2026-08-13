from dataclasses import replace

import pytest

from research_os.dashboard import DashboardAction, ProjectStatus
from research_os.evidence import ValidationIssue
from research_os.guidance import StageView
from research_os.meeting_brief import (
    BriefClaim,
    BriefIdea,
    BriefIdeaState,
    EvidenceReference,
    ExcludedClaim,
    MeetingBrief,
)
from research_os.manuscript_plan import manuscript_plan_from_brief


def _claim(
    claim_id: str,
    *,
    claim_type: str,
    status: str,
    locator: str = "p. 7, Results",
) -> BriefClaim:
    support = (
        (EvidenceReference("src-public", locator),)
        if locator
        else ()
    )
    return BriefClaim(
        claim_id=claim_id,
        statement=f"Statement for {claim_id}",
        claim_type=claim_type,
        status=status,
        confidence="medium",
        support=support,
        opposition=(),
        limitations="Single public benchmark.",
    )


def _brief() -> MeetingBrief:
    return MeetingBrief(
        schema_version=1,
        as_of="2026-08-13",
        project=ProjectStatus(
            title="Public diagnostic reasoning",
            slug="topic-a",
            stage="evidence-synthesis",
            state="in_progress",
            blockers=(),
        ),
        supported_claims=(
            _claim("C001", claim_type="fact", status="verified"),
            _claim("C003", claim_type="inference", status="verified"),
        ),
        conflicted_claims=(
            BriefClaim(
                **{
                    **_claim(
                        "C005",
                        claim_type="fact",
                        status="conflicted",
                    ).__dict__,
                    "opposition": (
                        EvidenceReference("src-public", "p. 9, Limitations"),
                    ),
                }
            ),
        ),
        open_claims=(
            _claim("C002", claim_type="fact", status="partially_verified"),
            _claim("C004", claim_type="hypothesis", status="unverified", locator=""),
        ),
        excluded_claims=(
            ExcludedClaim(
                claim_id="C006",
                statement="Invalid locator must remain excluded.",
                issues=(
                    ValidationIssue(
                        code="missing_locator",
                        claim_id="C006",
                        message="support source lacks a locator",
                    ),
                ),
            ),
        ),
        idea_state=BriefIdeaState(
            run_id="",
            cycle_state="not_started",
            human_decision_required=False,
            selected_idea_ids=(),
            candidate_generation_complete=False,
            novelty_check_complete=False,
            independent_review_complete=False,
            meta_review_complete=False,
        ),
        ideas=(),
        questions=(),
        recommendations=(),
        risks=(),
        actions=(),
        stages=(
            StageView(
                code="evidence_synthesis",
                name="Evidence synthesis",
                progress="in_progress",
                status="in progress",
                detail="Claims exist but synthesis is incomplete.",
            ),
        ),
    )


def _selected_idea(*, medical_safety: bool = True) -> BriefIdea:
    return BriefIdea(
        run_id="run-20260813T000000000000Z-00000000",
        idea_id="idea-0001",
        title="Evidence-gated diagnostic reasoning",
        scientific_question="Does an evidence gate reduce unsupported conclusions?",
        hypothesis="The gate reduces unsupported conclusions.",
        contribution="A falsifiable evidence gate.",
        evidence_source_ids=("src-public",),
        novelty_status="checked",
        scores=(("interestingness", 8), ("novelty", 7)),
        method_risks=("Evaluation leakage",),
        medical_safety_risks=("No clinical utility claim",) if medical_safety else (),
        failure_criterion="Unsupported conclusions do not decrease.",
        external_experiment="Independent public benchmark repository only.",
        status="selected",
        decision_reason="Evidence and cost are acceptable.",
    )


def _brief_with_stage_progress(
    stage_progress: dict[str, str],
    *,
    selected: bool,
    medical_safety: bool = True,
) -> MeetingBrief:
    codes = (
        "problem_definition",
        "source_intake",
        "paper_deep_read",
        "evidence_synthesis",
        "idea_review",
        "experiment_design",
        "result_interpretation",
        "manuscript_writing",
        "mock_review",
    )
    stages = tuple(
        StageView(
            code=code,
            name=code,
            progress=stage_progress.get(code, "unstarted"),
            status=stage_progress.get(code, "unstarted"),
            detail="fixture",
        )
        for code in codes
    )
    selected_ids = ("idea-0001",) if selected else ()
    return replace(
        _brief(),
        supported_claims=(_claim("C001", claim_type="fact", status="verified"),),
        conflicted_claims=(),
        open_claims=(),
        excluded_claims=(),
        idea_state=replace(
            _brief().idea_state,
            run_id="run-20260813T000000000000Z-00000000" if selected else "",
            cycle_state="completed" if selected else "not_started",
            selected_idea_ids=selected_ids,
        ),
        ideas=(_selected_idea(medical_safety=medical_safety),) if selected else (),
        stages=stages,
    )


def test_routes_claims_without_status_promotion() -> None:
    plan = manuscript_plan_from_brief(_brief())

    assert [item.claim_id for item in plan.citation_candidates] == ["C001"]
    assert [item.claim_id for item in plan.open_facts] == ["C002"]
    assert [item.claim_id for item in plan.research_statements] == ["C003", "C004"]
    assert [item.claim_id for item in plan.conflicts] == ["C005"]
    assert [item.claim_id for item in plan.excluded_claims] == ["C006"]
    assert plan.citation_candidates[0].support[0].locator == "p. 7, Results"
    assert plan.citation_candidates[0].limitations == "Single public benchmark."


@pytest.mark.parametrize(
    ("stage_progress", "selected", "expected"),
    [
        (
            {"problem_definition": "complete", "evidence_synthesis": "complete"},
            False,
            {"introduction": "ready", "methods": "blocked", "results": "blocked"},
        ),
        (
            {
                "problem_definition": "complete",
                "evidence_synthesis": "complete",
                "idea_review": "complete",
            },
            True,
            {"methods": "partial", "abstract": "partial"},
        ),
        (
            {
                "problem_definition": "complete",
                "evidence_synthesis": "complete",
                "experiment_design": "complete",
                "result_interpretation": "unstarted",
            },
            True,
            {"methods": "ready", "experiments": "partial", "results": "blocked"},
        ),
        (
            {
                "problem_definition": "complete",
                "evidence_synthesis": "complete",
                "experiment_design": "complete",
                "result_interpretation": "in_progress",
            },
            True,
            {"experiments": "ready", "results": "partial"},
        ),
        (
            {
                "problem_definition": "complete",
                "evidence_synthesis": "complete",
                "experiment_design": "complete",
                "result_interpretation": "complete",
            },
            True,
            {"abstract": "ready", "results": "ready", "conclusion": "ready"},
        ),
    ],
)
def test_section_readiness_is_deterministic(
    stage_progress: dict[str, str],
    selected: bool,
    expected: dict[str, str],
) -> None:
    plan = manuscript_plan_from_brief(
        _brief_with_stage_progress(stage_progress, selected=selected)
    )

    actual = {section.code: section.status for section in plan.sections}
    assert {code: actual[code] for code in expected} == expected


def test_medical_idea_requires_explicit_safety_risk_for_ethics_section() -> None:
    brief = _brief_with_stage_progress(
        {
            "problem_definition": "complete",
            "evidence_synthesis": "complete",
            "idea_review": "complete",
        },
        selected=True,
        medical_safety=False,
    )

    plan = manuscript_plan_from_brief(brief)
    ethics = next(section for section in plan.sections if section.code == "limitations_ethics")

    assert ethics.status == "partial"
    assert "MISSING_MEDICAL_SAFETY_BOUNDARY" in ethics.reason_codes


def test_excluded_claims_make_evidence_repair_the_only_next_action() -> None:
    plan = manuscript_plan_from_brief(_brief())

    assert plan.overall_status == "blocked"
    assert plan.next_action.code == "REPAIR_EVIDENCE"
    assert plan.next_action.target == "02-evidence-ledger.yaml"
    assert plan.next_action.command.startswith("research-os validate-ledger ")


def test_upstream_action_reuses_the_validated_dashboard_action() -> None:
    brief = replace(
        _brief_with_stage_progress(
            {"problem_definition": "complete", "evidence_synthesis": "complete"},
            selected=False,
        ),
        actions=(
            DashboardAction(
                code="REVIEW_IDEA",
                priority=1,
                category="research",
                rationale="Complete human Idea review.",
                expected_artifact="04-idea-candidates.md",
                command="$idea-review 审查 topic-a 的候选 Idea",
            ),
        ),
    )

    plan = manuscript_plan_from_brief(brief)

    assert plan.overall_status == "partial"
    assert plan.next_action.code == "ADVANCE_UPSTREAM_GATE"
    assert plan.next_action.reason == "Complete human Idea review."
    assert plan.next_action.target == "04-idea-candidates.md"
    assert plan.next_action.command == "$idea-review 审查 topic-a 的候选 Idea"


def test_ready_outline_has_one_fixed_evidence_bound_writing_action() -> None:
    brief = _brief_with_stage_progress(
        {
            "problem_definition": "complete",
            "evidence_synthesis": "complete",
            "idea_review": "complete",
            "experiment_design": "complete",
            "result_interpretation": "complete",
        },
        selected=True,
    )

    plan = manuscript_plan_from_brief(brief)

    assert plan.overall_status == "ready_for_outline"
    assert plan.next_action.code == "DRAFT_EVIDENCE_OUTLINE"
    assert plan.next_action.target == "08-manuscript-draft.md"
    assert plan.next_action.command == (
        "$manuscript-assistant 基于 topic-a 的 manuscript-plan 和核验证据账本创建论文大纲，"
        "不补写缺失引用或结果"
    )
