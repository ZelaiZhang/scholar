from __future__ import annotations

from dataclasses import dataclass

from research_os.dashboard import ProjectStatus
from research_os.meeting_brief import BriefClaim, ExcludedClaim, MeetingBrief


@dataclass(frozen=True)
class SectionReadiness:
    code: str
    title: str
    status: str
    reason_codes: tuple[str, ...]
    reasons: tuple[str, ...]
    claim_ids: tuple[str, ...]
    artifact_paths: tuple[str, ...]


@dataclass(frozen=True)
class ManuscriptAction:
    code: str
    reason: str
    target: str
    command: str


@dataclass(frozen=True)
class ManuscriptPlan:
    schema_version: int
    as_of: str
    project: ProjectStatus
    overall_status: str
    sections: tuple[SectionReadiness, ...]
    citation_candidates: tuple[BriefClaim, ...]
    open_facts: tuple[BriefClaim, ...]
    research_statements: tuple[BriefClaim, ...]
    conflicts: tuple[BriefClaim, ...]
    excluded_claims: tuple[ExcludedClaim, ...]
    next_action: ManuscriptAction
    boundaries: tuple[str, ...]


def manuscript_plan_from_brief(brief: MeetingBrief) -> ManuscriptPlan:
    citation_candidates = tuple(
        claim
        for claim in brief.supported_claims
        if claim.claim_type == "fact" and claim.status == "verified"
    )
    open_facts = tuple(
        claim
        for claim in brief.open_claims
        if claim.claim_type == "fact"
        and claim.status in {"unverified", "partially_verified"}
    )
    research_statements = tuple(
        claim
        for claim in (*brief.supported_claims, *brief.open_claims)
        if claim.claim_type in {"inference", "hypothesis"}
    )
    action = ManuscriptAction(
        code="REPAIR_EVIDENCE" if brief.excluded_claims else "ADVANCE_UPSTREAM_GATE",
        reason=(
            "Excluded claims must be repaired before evidence-bound writing."
            if brief.excluded_claims
            else "Complete the next validated research gate before drafting."
        ),
        target="02-evidence-ledger.yaml",
        command=(
            f'research-os validate-ledger "projects/{brief.project.slug}/'
            '02-evidence-ledger.yaml" --workspace .'
        ),
    )
    return ManuscriptPlan(
        schema_version=1,
        as_of=brief.as_of,
        project=brief.project,
        overall_status="blocked" if brief.excluded_claims else "partial",
        sections=(),
        citation_candidates=citation_candidates,
        open_facts=open_facts,
        research_statements=research_statements,
        conflicts=brief.conflicted_claims,
        excluded_claims=brief.excluded_claims,
        next_action=action,
        boundaries=(
            "This plan is not clinical decision support.",
            "Research OS does not execute experiments.",
            "The researcher must approve all manuscript claims and wording.",
        ),
    )
