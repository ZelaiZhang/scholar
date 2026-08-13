from __future__ import annotations

from dataclasses import dataclass

from research_os.dashboard import ProjectStatus
from research_os.meeting_brief import BriefClaim, ExcludedClaim, MeetingBrief


_SECTION_TITLES = {
    "abstract": "Abstract",
    "introduction": "Introduction",
    "related_work": "Related Work",
    "methods": "Methods",
    "experiments": "Experiments",
    "results": "Results",
    "limitations_ethics": "Limitations and Ethics",
    "conclusion": "Conclusion",
}

_SECTION_ORDER = tuple(_SECTION_TITLES)


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


def _readiness(
    *,
    code: str,
    requirements: tuple[tuple[bool, str, str], ...],
    claim_ids: tuple[str, ...] = (),
    artifact_paths: tuple[str, ...] = (),
) -> SectionReadiness:
    passed = tuple(item[0] for item in requirements)
    if all(passed):
        status = "ready"
    elif any(passed):
        status = "partial"
    else:
        status = "blocked"
    missing = tuple(item for item in requirements if not item[0])
    return SectionReadiness(
        code=code,
        title=_SECTION_TITLES[code],
        status=status,
        reason_codes=tuple(item[1] for item in missing),
        reasons=tuple(item[2] for item in missing),
        claim_ids=claim_ids,
        artifact_paths=artifact_paths,
    )


def _section_readiness(
    brief: MeetingBrief,
    *,
    citation_candidates: tuple[BriefClaim, ...],
) -> tuple[SectionReadiness, ...]:
    progress = {stage.code: stage.progress for stage in brief.stages}
    citation_ids = tuple(claim.claim_id for claim in citation_candidates)
    has_citation = bool(citation_candidates)
    has_limitation = any(claim.limitations.strip() for claim in citation_candidates)
    selected_ids = set(brief.idea_state.selected_idea_ids)
    selected_ideas = tuple(
        idea for idea in brief.ideas if idea.idea_id in selected_ids
    )
    has_selected_idea = bool(selected_ids) and bool(selected_ideas)
    has_medical_safety_boundary = not has_selected_idea or all(
        idea.medical_safety_risks for idea in selected_ideas
    )
    brief_complete = progress.get("problem_definition") == "complete"
    evidence_complete = progress.get("evidence_synthesis") == "complete"
    design_complete = progress.get("experiment_design") == "complete"
    result_progress = progress.get("result_interpretation", "unstarted")
    has_result_inputs = result_progress in {"in_progress", "complete"}
    result_complete = result_progress == "complete"

    common_citation = (
        has_citation,
        "MISSING_VERIFIED_CITATION",
        "At least one verified fact with a source locator is required.",
    )
    selected_requirement = (
        has_selected_idea,
        "MISSING_SELECTED_IDEA",
        "A researcher-approved Idea is required.",
    )
    design_requirement = (
        design_complete,
        "EXPERIMENT_DESIGN_INCOMPLETE",
        "Complete the experiment design gate without executing experiments here.",
    )
    result_input_requirement = (
        has_result_inputs,
        "RESULT_INPUTS_MISSING",
        "Import external result inputs before writing experimental findings.",
    )
    result_complete_requirement = (
        result_complete,
        "RESULT_INTERPRETATION_INCOMPLETE",
        "Complete conservative result interpretation before drafting conclusions.",
    )

    sections = {
        "abstract": _readiness(
            code="abstract",
            requirements=(
                selected_requirement,
                result_complete_requirement,
                common_citation,
            ),
            claim_ids=citation_ids,
            artifact_paths=(
                "04-idea-candidates.md",
                "07-result-interpretation.md",
                "02-evidence-ledger.yaml",
            ),
        ),
        "introduction": _readiness(
            code="introduction",
            requirements=(
                (
                    brief_complete,
                    "RESEARCH_BRIEF_INCOMPLETE",
                    "Complete the research problem definition.",
                ),
                common_citation,
            ),
            claim_ids=citation_ids,
            artifact_paths=("00-research-brief.md", "02-evidence-ledger.yaml"),
        ),
        "related_work": _readiness(
            code="related_work",
            requirements=(
                (
                    evidence_complete,
                    "EVIDENCE_SYNTHESIS_INCOMPLETE",
                    "Complete evidence synthesis, including conflicts and limitations.",
                ),
                common_citation,
            ),
            claim_ids=citation_ids,
            artifact_paths=("01-literature-matrix.md", "02-evidence-ledger.yaml"),
        ),
        "methods": _readiness(
            code="methods",
            requirements=(selected_requirement, design_requirement),
            artifact_paths=("04-idea-candidates.md", "05-experiment-design.md"),
        ),
        "experiments": _readiness(
            code="experiments",
            requirements=(design_requirement, result_input_requirement),
            artifact_paths=("05-experiment-design.md", "06-result-inputs/"),
        ),
        "results": _readiness(
            code="results",
            requirements=(result_input_requirement, result_complete_requirement),
            artifact_paths=("06-result-inputs/", "07-result-interpretation.md"),
        ),
        "limitations_ethics": _readiness(
            code="limitations_ethics",
            requirements=(
                (
                    has_limitation,
                    "MISSING_EVIDENCE_LIMITATION",
                    "Record at least one limitation on a verified citation candidate.",
                ),
                (
                    has_medical_safety_boundary,
                    "MISSING_MEDICAL_SAFETY_BOUNDARY",
                    "The selected medical Idea needs an explicit safety boundary.",
                ),
            ),
            claim_ids=citation_ids,
            artifact_paths=("02-evidence-ledger.yaml", "04-idea-candidates.md"),
        ),
        "conclusion": _readiness(
            code="conclusion",
            requirements=(
                selected_requirement,
                result_complete_requirement,
                common_citation,
            ),
            claim_ids=citation_ids,
            artifact_paths=(
                "04-idea-candidates.md",
                "07-result-interpretation.md",
                "02-evidence-ledger.yaml",
            ),
        ),
    }
    return tuple(sections[code] for code in _SECTION_ORDER)


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
    sections = _section_readiness(
        brief,
        citation_candidates=citation_candidates,
    )
    by_code = {section.code: section for section in sections}
    has_selected_idea = bool(brief.idea_state.selected_idea_ids)
    if brief.excluded_claims:
        overall_status = "blocked"
        action = ManuscriptAction(
            code="REPAIR_EVIDENCE",
            reason="Excluded claims must be repaired before evidence-bound writing.",
            target="02-evidence-ledger.yaml",
            command=(
                f'research-os validate-ledger "projects/{brief.project.slug}/'
                '02-evidence-ledger.yaml" --workspace .'
            ),
        )
    elif (
        citation_candidates
        and has_selected_idea
        and by_code["introduction"].status == "ready"
        and by_code["related_work"].status == "ready"
    ):
        overall_status = "ready_for_outline"
        action = ManuscriptAction(
            code="DRAFT_EVIDENCE_OUTLINE",
            reason="The evidence and human Idea gates are ready for a bounded outline.",
            target="08-manuscript-draft.md",
            command=(
                f"$manuscript-assistant 基于 {brief.project.slug} 的 manuscript-plan "
                "和核验证据账本创建论文大纲，不补写缺失引用或结果"
            ),
        )
    else:
        overall_status = "partial"
        if brief.actions:
            upstream = brief.actions[0]
            action = ManuscriptAction(
                code="ADVANCE_UPSTREAM_GATE",
                reason=upstream.rationale,
                target=upstream.expected_artifact,
                command=upstream.command,
            )
        else:
            action = ManuscriptAction(
                code="ADVANCE_UPSTREAM_GATE",
                reason="Refresh the validated research guidance before drafting.",
                target="project workflow",
                command=(
                    f"research-os guide --project {brief.project.slug} --workspace ."
                ),
            )
    return ManuscriptPlan(
        schema_version=1,
        as_of=brief.as_of,
        project=brief.project,
        overall_status=overall_status,
        sections=sections,
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
