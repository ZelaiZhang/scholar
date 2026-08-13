from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from research_os.dashboard import ProjectStatus
from research_os.meeting_brief import (
    BriefClaim,
    EvidenceReference,
    ExcludedClaim,
    MeetingBrief,
    build_meeting_brief,
)


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


def _reference_payload(reference: EvidenceReference) -> dict[str, str]:
    return {"source_id": reference.source_id, "locator": reference.locator}


def _claim_payload(claim: BriefClaim) -> dict[str, object]:
    return {
        "claim_id": claim.claim_id,
        "statement": claim.statement,
        "type": claim.claim_type,
        "status": claim.status,
        "confidence": claim.confidence,
        "support": [_reference_payload(item) for item in claim.support],
        "opposition": [_reference_payload(item) for item in claim.opposition],
        "limitations": claim.limitations,
    }


def _excluded_payload(claim: ExcludedClaim) -> dict[str, object]:
    return {
        "claim_id": claim.claim_id,
        "statement": claim.statement,
        "issues": [
            {
                "code": issue.code,
                "claim_id": issue.claim_id,
                "message": issue.message,
            }
            for issue in claim.issues
        ],
    }


def _section_payload(section: SectionReadiness) -> dict[str, object]:
    return {
        "code": section.code,
        "title": section.title,
        "status": section.status,
        "reason_codes": list(section.reason_codes),
        "reasons": list(section.reasons),
        "claim_ids": list(section.claim_ids),
        "artifact_paths": list(section.artifact_paths),
    }


def manuscript_plan_payload(plan: ManuscriptPlan) -> dict[str, object]:
    return {
        "schema_version": plan.schema_version,
        "as_of": plan.as_of,
        "project": {
            "title": plan.project.title,
            "slug": plan.project.slug,
            "stage": plan.project.stage,
            "state": plan.project.state,
            "blockers": list(plan.project.blockers),
        },
        "overall_status": plan.overall_status,
        "sections": [_section_payload(item) for item in plan.sections],
        "citation_candidates": [
            _claim_payload(item) for item in plan.citation_candidates
        ],
        "open_facts": [_claim_payload(item) for item in plan.open_facts],
        "research_statements": [
            _claim_payload(item) for item in plan.research_statements
        ],
        "conflicts": [_claim_payload(item) for item in plan.conflicts],
        "excluded_claims": [
            _excluded_payload(item) for item in plan.excluded_claims
        ],
        "next_actions": [
            {
                "code": plan.next_action.code,
                "reason": plan.next_action.reason,
                "target": plan.next_action.target,
                "command": plan.next_action.command,
            }
        ],
        "boundaries": list(plan.boundaries),
    }


def _markdown_text(value: str) -> str:
    return " ".join(value.splitlines()).replace("|", "\\|").strip()


def _render_claim_group(title: str, claims: tuple[BriefClaim, ...]) -> list[str]:
    lines = [f"## {title}", ""]
    if not claims:
        return [*lines, "- 无。", ""]
    for claim in claims:
        lines.append(
            f"- **{claim.claim_id}** `[{claim.claim_type}]` "
            f"`[{claim.status}]`：{_markdown_text(claim.statement)}"
        )
        for label, references in (
            ("支持", claim.support),
            ("反对", claim.opposition),
        ):
            for reference in references:
                lines.append(
                    f"  - {label}: `{reference.source_id}` @ "
                    f"{_markdown_text(reference.locator)}"
                )
        lines.append(f"  - 局限: {_markdown_text(claim.limitations) or '-'}")
    lines.append("")
    return lines


def render_manuscript_plan(plan: ManuscriptPlan) -> str:
    lines = [
        f"# 论文就绪计划：{_markdown_text(plan.project.title)}",
        "",
        f"- 课题: `{plan.project.slug}`",
        f"- 截止日期: {plan.as_of}",
        f"- 总体状态: `{plan.overall_status}`",
        "",
        "## 章节就绪度",
        "",
        "| Section | Status | Missing gates | Evidence | Artifacts |",
        "| --- | --- | --- | --- | --- |",
    ]
    for section in plan.sections:
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_text(section.title),
                    f"`{section.status}`",
                    _markdown_text("; ".join(section.reasons) or "-"),
                    _markdown_text(", ".join(section.claim_ids) or "-"),
                    _markdown_text(", ".join(section.artifact_paths) or "-"),
                )
            )
            + " |"
        )
    lines.append("")
    lines.extend(_render_claim_group("可引用事实候选", plan.citation_candidates))
    lines.extend(_render_claim_group("待核验事实", plan.open_facts))
    lines.extend(_render_claim_group("推断与假设", plan.research_statements))
    lines.extend(_render_claim_group("冲突证据", plan.conflicts))
    lines.extend(["## 已排除陈述", ""])
    if plan.excluded_claims:
        for claim in plan.excluded_claims:
            lines.append(f"- **{claim.claim_id}**：{_markdown_text(claim.statement)}")
            for issue in claim.issues:
                lines.append(
                    f"  - `{issue.code}`: {_markdown_text(issue.message)}"
                )
    else:
        lines.append("- 无。")
    lines.extend(
        [
            "",
            "## 唯一下一步",
            "",
            f"- 动作: `{plan.next_action.code}`",
            f"- 原因: {_markdown_text(plan.next_action.reason)}",
            f"- 目标: `{_markdown_text(plan.next_action.target)}`",
            f"- 命令: `{_markdown_text(plan.next_action.command)}`",
            "",
            "## 安全边界",
            "",
        ]
    )
    lines.extend(f"- {_markdown_text(boundary)}" for boundary in plan.boundaries)
    return "\n".join(lines).rstrip() + "\n"


def build_manuscript_plan(
    workspace: Path,
    slug: str,
    *,
    as_of: date,
) -> ManuscriptPlan:
    return manuscript_plan_from_brief(
        build_meeting_brief(workspace, slug, as_of=as_of)
    )


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
    has_medical_safety_boundary = not brief.ideas or all(
        idea.medical_safety_risks for idea in brief.ideas
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
                "06-result-analysis.md",
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
            artifact_paths=("05-experiment-design.md", "artifacts/"),
        ),
        "results": _readiness(
            code="results",
            requirements=(result_input_requirement, result_complete_requirement),
            artifact_paths=("artifacts/", "06-result-analysis.md"),
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
                "06-result-analysis.md",
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
    elif not citation_candidates:
        overall_status = "blocked"
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
                reason="Build at least one verified, locator-bound fact before writing.",
                target="02-evidence-ledger.yaml",
                command=(
                    f"research-os guide --project {brief.project.slug} --workspace ."
                ),
            )
    elif all(section.status == "ready" for section in sections):
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
