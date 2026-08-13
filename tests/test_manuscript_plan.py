from research_os.dashboard import ProjectStatus
from research_os.evidence import ValidationIssue
from research_os.guidance import StageView
from research_os.meeting_brief import (
    BriefClaim,
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


def test_routes_claims_without_status_promotion() -> None:
    plan = manuscript_plan_from_brief(_brief())

    assert [item.claim_id for item in plan.citation_candidates] == ["C001"]
    assert [item.claim_id for item in plan.open_facts] == ["C002"]
    assert [item.claim_id for item in plan.research_statements] == ["C003", "C004"]
    assert [item.claim_id for item in plan.conflicts] == ["C005"]
    assert [item.claim_id for item in plan.excluded_claims] == ["C006"]
    assert plan.citation_candidates[0].support[0].locator == "p. 7, Results"
    assert plan.citation_candidates[0].limitations == "Single public benchmark."
