"""Provenance and section-gate audit for parsed Research OS manuscripts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path

from research_os.dashboard import ProjectStatus
from research_os.cycle_context import IDENTIFIABLE_MEDICAL_MARKERS
from research_os.io import (
    assert_directory_identity,
    direct_file_identity,
    directory_identity,
    read_stable_direct_text,
)
from research_os.manuscript_markup import (
    AUDITED_SECTIONS,
    ManuscriptBlock,
    ParsedManuscript,
    parse_manuscript,
)
from research_os.manuscript_plan import (
    ManuscriptPlan,
    SectionReadiness,
    manuscript_plan_from_brief,
    manuscript_plan_payload,
)
from research_os.meeting_brief import BriefClaim, ExcludedClaim, build_meeting_brief
from research_os.project import resolve_project_path
from research_os.result_inputs import ResultInputSnapshot, load_result_inputs


_KIND_ORDER = ("fact", "inference", "hypothesis", "limitation", "method", "result")
_SECTION_CODES = {
    "Abstract": "abstract",
    "Introduction": "introduction",
    "Related Work": "related_work",
    "Methods": "methods",
    "Experiments": "experiments",
    "Results": "results",
    "Limitations and Ethics": "limitations_ethics",
    "Conclusion": "conclusion",
}
_ALLOWED_SECTIONS = {
    "fact": AUDITED_SECTIONS,
    "inference": AUDITED_SECTIONS,
    "hypothesis": AUDITED_SECTIONS,
    "method": frozenset({"Methods", "Experiments"}),
    "result": frozenset({"Abstract", "Experiments", "Results", "Conclusion"}),
    "limitation": frozenset(
        {"Abstract", "Introduction", "Results", "Limitations and Ethics", "Conclusion"}
    ),
}
_PHI_MARKERS = IDENTIFIABLE_MEDICAL_MARKERS
_AUDIT_BOUNDARIES = (
    "ANNOTATION_NOT_ENTAILMENT",
    "This audit is not clinical decision support.",
    "Research OS did not rewrite the manuscript or execute experiments.",
    "The researcher must verify semantic entailment and approve every statement.",
)


@dataclass(frozen=True)
class ManuscriptAuditIssue:
    code: str
    severity: str
    section: str
    block_index: int
    line: int
    claim_ids: tuple[str, ...]
    artifact_names: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class SectionAudit:
    code: str
    title: str
    readiness: str
    block_count: int
    annotated_block_count: int
    issue_count: int


@dataclass(frozen=True)
class ManuscriptAudit:
    schema_version: int
    as_of: str
    project: ProjectStatus
    draft_path: str
    draft_sha256: str
    status: str
    block_counts: tuple[tuple[str, int], ...]
    sections: tuple[SectionAudit, ...]
    issues: tuple[ManuscriptAuditIssue, ...]
    used_claim_ids: tuple[str, ...]
    used_result_artifacts: tuple[str, ...]
    boundaries: tuple[str, ...]


@dataclass(frozen=True)
class AuditContext:
    plan: ManuscriptPlan
    selected_idea_ids: tuple[str, ...]
    result_inputs: ResultInputSnapshot


@dataclass(frozen=True)
class _ClaimIndex:
    citable_facts: dict[str, BriefClaim]
    noncitable_facts: dict[str, BriefClaim]
    open_facts: dict[str, BriefClaim]
    research_statements: dict[str, BriefClaim]
    conflicts: dict[str, BriefClaim]
    excluded: dict[str, ExcludedClaim]


def audit_parsed_manuscript(
    parsed: ParsedManuscript,
    context: AuditContext,
    *,
    as_of: str | None = None,
    project: ProjectStatus | None = None,
    draft_path: str = "",
    draft_sha256: str = "",
) -> ManuscriptAudit:
    """Evaluate parsed annotations against one already-routed manuscript plan."""
    plan = context.plan
    claim_index = _claim_index(plan)
    readiness = {item.title: item for item in plan.sections}
    artifact_names = frozenset(artifact.name for artifact in context.result_inputs.artifacts)
    issues: list[ManuscriptAuditIssue] = []
    used_claim_ids: set[str] = set()
    used_artifacts: set[str] = set()
    valid_limitation = False

    if plan.overall_status == "blocked":
        issues.append(_issue("PLAN_BLOCKED", "", 0, 0))

    occurrence_counts: dict[str, int] = {}
    for section, line in parsed.section_occurrences:
        occurrence_counts[section] = occurrence_counts.get(section, 0) + 1
        if section in _SECTION_CODES and occurrence_counts[section] > 1:
            issues.append(_issue("DUPLICATE_SECTION", section, 0, line))
    seen_sections = {section for section, _ in parsed.section_occurrences}
    for section in _SECTION_CODES:
        if section not in seen_sections:
            issues.append(_issue("MISSING_SECTION", section, 0, 0))

    for syntax_issue in parsed.syntax_issues:
        issues.append(
            _issue(
                syntax_issue.code,
                syntax_issue.section,
                syntax_issue.block_index,
                syntax_issue.line,
            )
        )

    for block in parsed.blocks:
        if block.section not in _SECTION_CODES:
            continue
        if block.annotation is None:
            issues.append(_issue("UNANNOTATED_BLOCK", block.section, block.block_index, block.line))
            continue
        annotation = block.annotation
        if block.section not in _ALLOWED_SECTIONS[annotation.kind]:
            issues.append(_issue("KIND_NOT_ALLOWED_IN_SECTION", block.section, block.block_index, block.line))
        section_readiness = readiness.get(block.section)
        section_gate: str | None = None
        if section_readiness is not None and section_readiness.status != "ready":
            section_gate = _section_gate_code(section_readiness.status)
            issues.append(
                _issue(
                    section_gate,
                    block.section,
                    block.block_index,
                    block.line,
                )
            )
        if annotation.kind == "fact":
            valid_ids = _validate_fact_claims(block, claim_index, issues)
            used_claim_ids.update(valid_ids)
        elif annotation.kind == "limitation":
            valid_ids, all_valid = _validate_limitation_claims(
                block, claim_index, issues
            )
            used_claim_ids.update(valid_ids)
            if all_valid and block.section in _ALLOWED_SECTIONS[annotation.kind]:
                valid_limitation = True
        elif annotation.kind in {"inference", "hypothesis"}:
            valid_ids = _validate_research_claims(block, claim_index, issues)
            used_claim_ids.update(valid_ids)
        elif annotation.kind == "method":
            if annotation.idea_id not in context.selected_idea_ids:
                issues.append(
                    _issue("IDEA_NOT_SELECTED", block.section, block.block_index, block.line)
                )
            methods_status = _readiness_status(plan, "Methods")
            methods_gate = _section_gate_code(methods_status)
            if methods_status != "ready" and section_gate != methods_gate:
                issues.append(_issue(methods_gate, block.section, block.block_index, block.line))
        elif annotation.kind == "result":
            for artifact_name in annotation.artifact_names:
                if artifact_name not in artifact_names:
                    issues.append(
                        _issue(
                            "UNKNOWN_RESULT_ARTIFACT",
                            block.section,
                            block.block_index,
                            block.line,
                            artifact_names=(artifact_name,),
                        )
                    )
                else:
                    used_artifacts.add(artifact_name)
            results_status = _readiness_status(plan, "Results")
            results_gate = _section_gate_code(results_status)
            if results_status != "ready" and section_gate != results_gate:
                issues.append(
                    _issue(
                        results_gate,
                        block.section,
                        block.block_index,
                        block.line,
                    )
                )

    if not valid_limitation:
        issues.append(_issue("LIMITATION_MISSING", "", 0, 0))

    sorted_issues = tuple(
        sorted(
            issues,
            key=lambda item: (item.line, item.code, item.claim_ids, item.artifact_names),
        )
    )
    sections = _section_audits(parsed, plan, sorted_issues)
    return ManuscriptAudit(
        schema_version=1,
        as_of=plan.as_of if as_of is None else as_of,
        project=plan.project if project is None else project,
        draft_path=draft_path,
        draft_sha256=draft_sha256,
        status="pass" if not sorted_issues else "issues",
        block_counts=tuple(
            (kind, sum(1 for block in parsed.blocks if block.annotation and block.annotation.kind == kind))
            for kind in _KIND_ORDER
        ),
        sections=sections,
        issues=sorted_issues,
        used_claim_ids=tuple(sorted(used_claim_ids)),
        used_result_artifacts=tuple(sorted(used_artifacts)),
        boundaries=_AUDIT_BOUNDARIES,
    )


def build_manuscript_audit(
    workspace: Path,
    slug: str,
    draft: Path,
    *,
    as_of: date,
) -> ManuscriptAudit:
    """Build a read-only audit from one stable, direct project writing file."""
    if not isinstance(as_of, date):
        raise TypeError("as_of must be a date")
    workspace = workspace.resolve()
    project = resolve_project_path(workspace, slug, require_exists=True)
    project_identity = directory_identity(project)
    writing = project / "writing"
    writing_identity = directory_identity(writing)
    draft_path = _safe_draft_path(project, writing, draft)
    draft_identity = direct_file_identity(
        draft_path,
        expected_parent=writing,
        expected_parent_identity=writing_identity,
    )

    first_brief = build_meeting_brief(workspace, slug, as_of=as_of)
    first_plan = manuscript_plan_from_brief(first_brief)
    _assert_audit_directories(project, project_identity, writing, writing_identity)

    draft_text = read_stable_direct_text(
        draft_path,
        expected_parent=writing,
        expected_parent_identity=writing_identity,
        max_bytes=4 * 1024 * 1024,
    )
    if (
        direct_file_identity(
            draft_path,
            expected_parent=writing,
            expected_parent_identity=writing_identity,
        )
        != draft_identity
    ):
        raise OSError("draft changed during stable read")
    _assert_no_phi(draft_text)
    parsed = parse_manuscript(draft_text)
    draft_sha256 = hashlib.sha256(draft_text.encode("utf-8")).hexdigest()

    second_brief = build_meeting_brief(workspace, slug, as_of=as_of)
    second_plan = manuscript_plan_from_brief(second_brief)
    if _canonical_plan(first_plan) != _canonical_plan(second_plan):
        raise OSError("research state changed during manuscript audit")
    if _selected_ids(first_brief) != _selected_ids(second_brief):
        raise OSError("selected Idea IDs changed during manuscript audit")
    result_inputs = load_result_inputs(project, project_identity)
    audit = audit_parsed_manuscript(
        parsed,
        AuditContext(second_plan, _selected_ids(second_brief), result_inputs),
        as_of=as_of.isoformat(),
        project=second_plan.project,
        draft_path=draft_path.relative_to(project).as_posix(),
        draft_sha256=draft_sha256,
    )

    _assert_audit_directories(project, project_identity, writing, writing_identity)
    if (
        direct_file_identity(
            draft_path,
            expected_parent=writing,
            expected_parent_identity=writing_identity,
        )
        != draft_identity
    ):
        raise OSError("draft changed during manuscript audit")
    final_text = read_stable_direct_text(
        draft_path,
        expected_parent=writing,
        expected_parent_identity=writing_identity,
        max_bytes=4 * 1024 * 1024,
    )
    if hashlib.sha256(final_text.encode("utf-8")).hexdigest() != draft_sha256:
        raise OSError("draft content changed during manuscript audit")
    return audit


def _safe_draft_path(project: Path, writing: Path, draft: Path) -> Path:
    candidate = draft if draft.is_absolute() else project / draft
    if candidate.suffix != ".md" or candidate.parent.resolve() != writing:
        raise ValueError("draft must be a direct .md file below project writing/")
    return candidate


def _assert_audit_directories(
    project: Path,
    project_identity: tuple[int, int],
    writing: Path,
    writing_identity: tuple[int, int],
) -> None:
    assert_directory_identity(project, project_identity, context="project")
    assert_directory_identity(writing, writing_identity, context="writing")


def _assert_no_phi(draft_text: str) -> None:
    lowered = draft_text.casefold()
    if any(marker.casefold() in lowered for marker in _PHI_MARKERS):
        raise PermissionError("PHI_SUSPECTED")


def _canonical_plan(plan: ManuscriptPlan) -> bytes:
    return json.dumps(
        manuscript_plan_payload(plan),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _selected_ids(brief: object) -> tuple[str, ...]:
    return tuple(brief.idea_state.selected_idea_ids)  # type: ignore[attr-defined]


def manuscript_audit_payload(audit: ManuscriptAudit) -> dict[str, object]:
    """Return the stable public projection of an audit, without input prose."""
    return {
        "schema_version": audit.schema_version,
        "as_of": audit.as_of,
        "project": {
            "title": audit.project.title,
            "slug": audit.project.slug,
            "stage": audit.project.stage,
            "state": audit.project.state,
            "blockers": list(audit.project.blockers),
        },
        "draft_path": audit.draft_path,
        "draft_sha256": audit.draft_sha256,
        "status": audit.status,
        "block_counts": [
            {"kind": kind, "count": count} for kind, count in audit.block_counts
        ],
        "sections": [
            {
                "code": section.code,
                "title": section.title,
                "readiness": section.readiness,
                "block_count": section.block_count,
                "annotated_block_count": section.annotated_block_count,
                "issue_count": section.issue_count,
            }
            for section in audit.sections
        ],
        "issues": [
            {
                "code": issue.code,
                "severity": issue.severity,
                "section": issue.section,
                "block_index": issue.block_index,
                "line": issue.line,
                "claim_ids": list(issue.claim_ids),
                "artifact_names": list(issue.artifact_names),
                "message": issue.message,
            }
            for issue in audit.issues
        ],
        "used_claim_ids": list(audit.used_claim_ids),
        "used_result_artifacts": list(audit.used_result_artifacts),
        "boundaries": list(audit.boundaries),
    }


def render_manuscript_audit(audit: ManuscriptAudit) -> str:
    """Render audit metadata and annotation findings without draft prose."""
    lines = [
        "# Manuscript audit",
        "",
        f"- Project: `{audit.project.slug}`",
        f"- Draft: `{audit.draft_path}`",
        f"- As of: {audit.as_of}",
        f"- Status: `{audit.status}`",
        "",
        "## Sections",
        "",
        "| Section | Readiness | Blocks | Annotated | Issues |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for section in audit.sections:
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_cell(section.title),
                    f"`{section.readiness}`",
                    str(section.block_count),
                    str(section.annotated_block_count),
                    str(section.issue_count),
                )
            )
            + " |"
        )
    lines.extend(("", "## Annotation kind counts", ""))
    for kind, count in audit.block_counts:
        lines.append(f"- `{kind}`: {count}")
    lines.extend(("", "## Issues", ""))
    if not audit.issues:
        lines.append("- None.")
    else:
        for issue in audit.issues:
            identifiers = ", ".join((*issue.claim_ids, *issue.artifact_names)) or "-"
            location = f"line {issue.line}" if issue.line else "no line"
            section = issue.section or "project"
            lines.append(
                f"- `{issue.code}` ({location}; {section}; IDs: {identifiers})"
            )
    lines.extend(("", "## Used evidence and results", ""))
    lines.append("- Claims: " + (", ".join(audit.used_claim_ids) or "-"))
    lines.append("- Result artifacts: " + (", ".join(audit.used_result_artifacts) or "-"))
    lines.extend(("", "## Boundaries", ""))
    lines.extend(f"- {boundary}" for boundary in audit.boundaries)
    return "\n".join(lines) + "\n"


def _markdown_cell(value: str) -> str:
    return " ".join(value.splitlines()).replace("|", "\\|").strip()


def _claim_index(plan: ManuscriptPlan) -> _ClaimIndex:
    return _ClaimIndex(
        citable_facts={
            claim.claim_id: claim
            for claim in plan.citation_candidates
            if _is_citable_fact(claim)
        },
        noncitable_facts={
            claim.claim_id: claim
            for claim in plan.citation_candidates
            if claim.claim_type == "fact" and not _is_citable_fact(claim)
        },
        open_facts={
            claim.claim_id: claim
            for claim in (*plan.citation_candidates, *plan.open_facts)
            if claim.claim_type == "fact" and claim.status != "verified"
        },
        research_statements={claim.claim_id: claim for claim in plan.research_statements},
        conflicts={claim.claim_id: claim for claim in plan.conflicts},
        excluded={claim.claim_id: claim for claim in plan.excluded_claims},
    )


def _validate_fact_claims(
    block: ManuscriptBlock, index: _ClaimIndex, issues: list[ManuscriptAuditIssue]
) -> tuple[str, ...]:
    valid: list[str] = []
    assert block.annotation is not None
    for claim_id in block.annotation.claim_ids:
        if claim_id in index.citable_facts:
            valid.append(claim_id)
        elif claim_id in index.excluded:
            issues.append(_issue("CLAIM_INVALID", block.section, block.block_index, block.line, claim_ids=(claim_id,)))
        elif (
            claim_id in index.noncitable_facts
            or claim_id in index.open_facts
            or claim_id in index.conflicts
        ):
            issues.append(_issue("CLAIM_NOT_CITABLE", block.section, block.block_index, block.line, claim_ids=(claim_id,)))
        elif claim_id in index.research_statements:
            issues.append(_issue("CLAIM_KIND_MISMATCH", block.section, block.block_index, block.line, claim_ids=(claim_id,)))
        else:
            issues.append(_issue("UNKNOWN_CLAIM", block.section, block.block_index, block.line, claim_ids=(claim_id,)))
    return tuple(valid)


def _validate_limitation_claims(
    block: ManuscriptBlock, index: _ClaimIndex, issues: list[ManuscriptAuditIssue]
) -> tuple[tuple[str, ...], bool]:
    valid: list[str] = []
    candidates = {
        **index.citable_facts,
        **index.open_facts,
        **index.research_statements,
        **index.conflicts,
    }
    assert block.annotation is not None
    for claim_id in block.annotation.claim_ids:
        claim = candidates.get(claim_id)
        if claim is not None and claim.limitations.strip():
            valid.append(claim_id)
        elif claim_id in index.excluded:
            issues.append(_issue("CLAIM_INVALID", block.section, block.block_index, block.line, claim_ids=(claim_id,)))
        elif claim_id in index.noncitable_facts:
            issues.append(_issue("CLAIM_NOT_CITABLE", block.section, block.block_index, block.line, claim_ids=(claim_id,)))
        elif claim is not None:
            issues.append(_issue("CLAIM_NOT_CITABLE", block.section, block.block_index, block.line, claim_ids=(claim_id,)))
        else:
            issues.append(_issue("UNKNOWN_CLAIM", block.section, block.block_index, block.line, claim_ids=(claim_id,)))
    valid_ids = tuple(valid)
    return valid_ids, len(valid_ids) == len(block.annotation.claim_ids)


def _validate_research_claims(
    block: ManuscriptBlock, index: _ClaimIndex, issues: list[ManuscriptAuditIssue]
) -> tuple[str, ...]:
    valid: list[str] = []
    assert block.annotation is not None
    for claim_id in block.annotation.claim_ids:
        if claim_id in index.excluded:
            issues.append(_issue("CLAIM_INVALID", block.section, block.block_index, block.line, claim_ids=(claim_id,)))
            continue
        claim = index.research_statements.get(claim_id) or index.conflicts.get(claim_id)
        if claim is not None and claim.claim_type == block.annotation.kind:
            valid.append(claim_id)
        elif claim is not None or claim_id in index.citable_facts or claim_id in index.open_facts:
            issues.append(_issue("CLAIM_KIND_MISMATCH", block.section, block.block_index, block.line, claim_ids=(claim_id,)))
        else:
            issues.append(_issue("UNKNOWN_CLAIM", block.section, block.block_index, block.line, claim_ids=(claim_id,)))
    return tuple(valid)


def _is_citable_fact(claim: BriefClaim) -> bool:
    return (
        claim.claim_type == "fact"
        and claim.status == "verified"
        and bool(claim.limitations.strip())
        and any(reference.source_id.strip() and reference.locator.strip() for reference in claim.support)
    )


def _readiness_status(plan: ManuscriptPlan, title: str) -> str:
    return next((section.status for section in plan.sections if section.title == title), "blocked")


def _section_gate_code(status: str) -> str:
    return "SECTION_PARTIAL" if status == "partial" else "SECTION_BLOCKED"


def _section_audits(
    parsed: ParsedManuscript,
    plan: ManuscriptPlan,
    issues: tuple[ManuscriptAuditIssue, ...],
) -> tuple[SectionAudit, ...]:
    audits: list[SectionAudit] = []
    for section in plan.sections:
        blocks = tuple(block for block in parsed.blocks if block.section == section.title)
        audits.append(
            SectionAudit(
                code=section.code,
                title=section.title,
                readiness=section.status,
                block_count=len(blocks),
                annotated_block_count=sum(block.annotation is not None for block in blocks),
                issue_count=sum(issue.section == section.title for issue in issues),
            )
        )
    return tuple(audits)


def _issue(
    code: str,
    section: str,
    block_index: int,
    line: int,
    *,
    claim_ids: tuple[str, ...] = (),
    artifact_names: tuple[str, ...] = (),
) -> ManuscriptAuditIssue:
    messages = {
        "UNKNOWN_CLAIM": "Annotation references an unknown routed claim.",
        "CLAIM_KIND_MISMATCH": "Annotation kind does not match the routed claim type.",
        "CLAIM_NOT_CITABLE": "Annotation references a routed claim that is not citable.",
        "CLAIM_INVALID": "Annotation references an excluded routed claim.",
        "LIMITATION_MISSING": "At least one valid limitation annotation is required.",
        "IDEA_NOT_SELECTED": "Method annotation references an Idea not selected by the researcher.",
        "UNKNOWN_RESULT_ARTIFACT": "Result annotation references an unregistered result artifact.",
        "UNANNOTATED_BLOCK": "Audited prose block has no Research OS annotation.",
        "MISSING_SECTION": "Required audited section is missing.",
        "DUPLICATE_SECTION": "Required audited section occurs more than once.",
        "INVALID_ANNOTATION": "Research OS annotation is invalid.",
        "ORPHAN_ANNOTATION": "Research OS annotation is not attached to a prose block.",
        "KIND_NOT_ALLOWED_IN_SECTION": "Annotation kind is not allowed in this section.",
        "SECTION_BLOCKED": "Annotated block is in a blocked manuscript section.",
        "SECTION_PARTIAL": "Annotated block is in a partial manuscript section.",
        "PLAN_BLOCKED": "The routed manuscript plan is blocked.",
    }
    return ManuscriptAuditIssue(
        code, "error", section, block_index, line, claim_ids, artifact_names, messages[code]
    )
