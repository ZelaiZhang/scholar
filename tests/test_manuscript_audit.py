from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path

import pytest

from research_os.dashboard import ProjectStatus
from research_os.manuscript_audit import AuditContext, audit_parsed_manuscript
from research_os.manuscript_markup import parse_manuscript
from research_os.manuscript_plan import (
    ManuscriptAction,
    ManuscriptPlan,
    SectionReadiness,
)
from research_os.meeting_brief import BriefClaim, EvidenceReference
from research_os.meeting_brief import ExcludedClaim
from research_os.result_inputs import ResultArtifact, ResultInputSnapshot


PROJECT = ProjectStatus(
    title="Public research project",
    slug="public-project",
    stage="writing",
    state="active",
    blockers=(),
)
SECTION_TITLES = (
    ("abstract", "Abstract"),
    ("introduction", "Introduction"),
    ("related_work", "Related Work"),
    ("methods", "Methods"),
    ("experiments", "Experiments"),
    ("results", "Results"),
    ("limitations_ethics", "Limitations and Ethics"),
    ("conclusion", "Conclusion"),
)


def _claim(claim_id: str, claim_type: str, *, status: str = "verified") -> BriefClaim:
    return BriefClaim(
        claim_id=claim_id,
        statement="A routed research statement.",
        claim_type=claim_type,
        status=status,
        confidence="high",
        support=(EvidenceReference("source-1", "p. 1"),),
        opposition=(),
        limitations="A bounded limitation.",
    )


def _context(
    *,
    statuses: dict[str, str] | None = None,
    selected_idea_ids: tuple[str, ...] = (),
    artifacts: tuple[ResultArtifact, ...] = (),
) -> AuditContext:
    statuses = statuses or {}
    sections = tuple(
        SectionReadiness(code, title, statuses.get(code, "ready"), (), (), (), ())
        for code, title in SECTION_TITLES
    )
    plan = ManuscriptPlan(
        schema_version=1,
        as_of="2026-08-13",
        project=PROJECT,
        overall_status="ready_for_outline",
        sections=sections,
        citation_candidates=(_claim("FACT-1", "fact"),),
        open_facts=(),
        research_statements=(
            _claim("INFERENCE-1", "inference"),
            _claim("HYPOTHESIS-1", "hypothesis"),
        ),
        conflicts=(),
        excluded_claims=(),
        next_action=ManuscriptAction("DRAFT", "Bounded drafting.", "draft", "draft"),
        boundaries=(),
    )
    return AuditContext(
        plan,
        selected_idea_ids,
        ResultInputSnapshot(artifacts, "valid", None, None),
    )


def _document(*blocks: tuple[str, str]) -> str:
    grouped = {title: [] for _, title in SECTION_TITLES}
    for section, content in blocks:
        grouped[section].append(content)
    lines: list[str] = []
    for _, section in SECTION_TITLES:
        lines.extend((f"## {section}", *grouped[section], ""))
    return "\n".join(lines)


def _valid_document(*extra_blocks: tuple[str, str]) -> str:
    return _document(
        ("Abstract", "<!-- research-os:kind=fact; claims=FACT-1 -->\nPublic summary."),
        (
            "Limitations and Ethics",
            "<!-- research-os:kind=limitation; claims=FACT-1 -->\nBounded limitation.",
        ),
        *extra_blocks,
    )


def _codes(audit: object) -> list[str]:
    return [issue.code for issue in audit.issues]  # type: ignore[attr-defined]


def test_audit_accepts_verified_fact_and_research_statement_annotations() -> None:
    parsed = parse_manuscript(
        "## Abstract\n"
        "<!-- research-os:kind=fact; claims=FACT-1 -->\n"
        "Public summary.\n\n"
        "<!-- research-os:kind=inference; claims=INFERENCE-1 -->\n"
        "Bounded inference.\n\n"
        "<!-- research-os:kind=limitation; claims=FACT-1 -->\n"
        "Bounded limitation.\n\n"
        "## Introduction\n"
        "<!-- research-os:kind=hypothesis; claims=HYPOTHESIS-1 -->\n"
        "Research hypothesis.\n\n"
        "## Related Work\n\n"
        "## Methods\n\n"
        "## Experiments\n\n"
        "## Results\n\n"
        "## Limitations and Ethics\n\n"
        "## Conclusion\n"
    )

    audit = audit_parsed_manuscript(parsed, _context())

    assert audit.status == "pass"
    assert audit.used_claim_ids == ("FACT-1", "HYPOTHESIS-1", "INFERENCE-1")
    assert "ANNOTATION_NOT_ENTAILMENT" in audit.boundaries


def test_fact_annotation_rejects_unknown_claim() -> None:
    audit = audit_parsed_manuscript(
        parse_manuscript(
            _valid_document(
                ("Introduction", "<!-- research-os:kind=fact; claims=UNKNOWN -->\nStatement.")
            )
        ),
        _context(),
    )

    assert "UNKNOWN_CLAIM" in _codes(audit)
    assert "UNKNOWN" not in audit.used_claim_ids


def test_fact_annotation_rejects_research_statement_kind() -> None:
    audit = audit_parsed_manuscript(
        parse_manuscript(
            _valid_document(
                (
                    "Introduction",
                    "<!-- research-os:kind=fact; claims=INFERENCE-1 -->\nStatement.",
                )
            )
        ),
        _context(),
    )

    assert "CLAIM_KIND_MISMATCH" in _codes(audit)


def test_fact_annotation_requires_verified_citation_candidate() -> None:
    context = _context()
    context = replace(
        context,
        plan=replace(
            context.plan,
            citation_candidates=(
                _claim("NOT-VERIFIED", "fact", status="unverified"),
                _claim("FACT-1", "fact"),
            ),
        ),
    )
    audit = audit_parsed_manuscript(
        parse_manuscript(
            _document(
                (
                    "Abstract",
                    "<!-- research-os:kind=fact; claims=NOT-VERIFIED -->\nSummary.",
                ),
                    (
                        "Limitations and Ethics",
                    "<!-- research-os:kind=limitation; claims=FACT-1 -->\nLimit.",
                ),
            )
        ),
        context,
    )

    assert "CLAIM_NOT_CITABLE" in _codes(audit)
    assert "NOT-VERIFIED" not in audit.used_claim_ids


def test_fact_annotation_requires_source_locator_and_limitation_provenance() -> None:
    context = _context()
    bad_fact = replace(_claim("BAD-FACT", "fact"), support=(), limitations="")
    context = replace(
        context,
        plan=replace(context.plan, citation_candidates=(bad_fact, _claim("FACT-1", "fact"))),
    )
    audit = audit_parsed_manuscript(
        parse_manuscript(
            _valid_document(
                ("Introduction", "<!-- research-os:kind=fact; claims=BAD-FACT -->\nStatement.")
            )
        ),
        context,
    )

    assert "CLAIM_NOT_CITABLE" in _codes(audit)
    assert "BAD-FACT" not in audit.used_claim_ids


def test_limitation_annotation_accepts_valid_routed_research_statement() -> None:
    audit = audit_parsed_manuscript(
        parse_manuscript(
            _document(
                ("Abstract", "<!-- research-os:kind=fact; claims=FACT-1 -->\nSummary."),
                (
                    "Limitations and Ethics",
                    "<!-- research-os:kind=limitation; claims=INFERENCE-1 -->\nLimit.",
                ),
            )
        ),
        _context(),
    )

    assert audit.status == "pass"
    assert "INFERENCE-1" in audit.used_claim_ids


def test_limitation_annotation_rejects_verified_fact_without_source_locator() -> None:
    context = _context()
    bad_fact = replace(_claim("BAD-LIMIT", "fact"), support=())
    context = replace(
        context,
        plan=replace(context.plan, citation_candidates=(bad_fact,)),
    )
    audit = audit_parsed_manuscript(
        parse_manuscript(
            _document(
                (
                    "Limitations and Ethics",
                    "<!-- research-os:kind=limitation; claims=BAD-LIMIT -->\nLimit.",
                ),
            )
        ),
        context,
    )

    assert {"CLAIM_NOT_CITABLE", "LIMITATION_MISSING"} <= set(_codes(audit))
    assert "BAD-LIMIT" not in audit.used_claim_ids


@pytest.mark.parametrize(
    ("claim_id", "field", "expected_code"),
    [
        ("OPEN", "open_facts", "CLAIM_NOT_CITABLE"),
        ("CONFLICT", "conflicts", "CLAIM_NOT_CITABLE"),
        ("EXCLUDED", "excluded_claims", "CLAIM_INVALID"),
    ],
)
def test_fact_annotation_rejects_non_citable_or_invalid_routed_claims(
    claim_id: str, field: str, expected_code: str
) -> None:
    context = _context()
    value: object
    if field == "excluded_claims":
        value = (ExcludedClaim(claim_id, "Excluded statement.", ()),)
    else:
        value = (_claim(claim_id, "fact", status="unverified"),)
    context = replace(context, plan=replace(context.plan, **{field: value}))

    audit = audit_parsed_manuscript(
        parse_manuscript(
            _valid_document(
                ("Introduction", f"<!-- research-os:kind=fact; claims={claim_id} -->\nStatement.")
            )
        ),
        context,
    )

    assert expected_code in _codes(audit)
    assert claim_id not in audit.used_claim_ids


@pytest.mark.parametrize(
    ("kind", "claim_id", "expected_code"),
    [
        ("inference", "HYPOTHESIS-1", "CLAIM_KIND_MISMATCH"),
        ("hypothesis", "INFERENCE-1", "CLAIM_KIND_MISMATCH"),
        ("inference", "EXCLUDED-STATEMENT", "CLAIM_INVALID"),
    ],
)
def test_research_statement_annotations_require_same_valid_type(
    kind: str, claim_id: str, expected_code: str
) -> None:
    context = _context()
    if claim_id == "EXCLUDED-STATEMENT":
        context = replace(
            context,
            plan=replace(
                context.plan,
                excluded_claims=(ExcludedClaim(claim_id, "Excluded statement.", ()),),
            ),
        )
    audit = audit_parsed_manuscript(
        parse_manuscript(
            _valid_document(
                ("Introduction", f"<!-- research-os:kind={kind}; claims={claim_id} -->\nStatement.")
            )
        ),
        context,
    )

    assert expected_code in _codes(audit)


def test_audit_requires_at_least_one_valid_limitation_annotation() -> None:
    audit = audit_parsed_manuscript(
        parse_manuscript(
            _document(
                ("Abstract", "<!-- research-os:kind=fact; claims=FACT-1 -->\nSummary.")
            )
        ),
        _context(),
    )

    assert "LIMITATION_MISSING" in _codes(audit)


def test_method_annotation_requires_researcher_selected_idea() -> None:
    audit = audit_parsed_manuscript(
        parse_manuscript(
            _valid_document(
                ("Methods", "<!-- research-os:kind=method; idea=IDEA-1 -->\nMethod.")
            )
        ),
        _context(),
    )

    assert "IDEA_NOT_SELECTED" in _codes(audit)


def test_method_annotation_reports_selection_and_methods_gate_independently() -> None:
    audit = audit_parsed_manuscript(
        parse_manuscript(
            _valid_document(
                ("Experiments", "<!-- research-os:kind=method; idea=IDEA-1 -->\nMethod.")
            )
        ),
        _context(statuses={"methods": "blocked"}),
    )

    assert {"IDEA_NOT_SELECTED", "SECTION_BLOCKED"} <= set(_codes(audit))


def test_selected_method_annotation_passes_when_methods_is_ready() -> None:
    audit = audit_parsed_manuscript(
        parse_manuscript(
            _valid_document(
                ("Methods", "<!-- research-os:kind=method; idea=IDEA-1 -->\nMethod.")
            )
        ),
        _context(selected_idea_ids=("IDEA-1",)),
    )

    assert audit.status == "pass"
    assert audit.used_claim_ids == ("FACT-1",)


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [("partial", "SECTION_PARTIAL"), ("blocked", "SECTION_BLOCKED")],
)
def test_annotated_blocks_respect_section_readiness(
    status: str, expected_code: str
) -> None:
    audit = audit_parsed_manuscript(
        parse_manuscript(_valid_document()),
        _context(statuses={"abstract": status}),
    )

    assert expected_code in _codes(audit)


def test_result_annotation_requires_registered_artifact_and_results_readiness() -> None:
    artifact = ResultArtifact(
        "registered.csv", Path("registered.csv"), "0" * 64, "public", "2026-08-13T00:00:00Z", (1, 1)
    )
    registered = audit_parsed_manuscript(
        parse_manuscript(
            _valid_document(
                (
                    "Results",
                    "<!-- research-os:kind=result; artifacts=registered.csv -->\nFinding.",
                )
            )
        ),
        _context(artifacts=(artifact,)),
    )
    unregistered = audit_parsed_manuscript(
        parse_manuscript(
            _valid_document(
                ("Results", "<!-- research-os:kind=result; artifacts=missing.csv -->\nFinding.")
            )
        ),
        _context(statuses={"results": "partial"}, artifacts=(artifact,)),
    )

    assert registered.status == "pass"
    assert registered.used_result_artifacts == ("registered.csv",)
    assert {"UNKNOWN_RESULT_ARTIFACT", "SECTION_PARTIAL"} <= set(_codes(unregistered))
    assert len([issue for issue in unregistered.issues if issue.code == "SECTION_PARTIAL"]) == 1
    assert "missing.csv" not in unregistered.used_result_artifacts


def test_kind_restriction_and_unannotated_prose_are_reported_without_prose_leakage() -> None:
    audit = audit_parsed_manuscript(
        parse_manuscript(
            _valid_document(
                ("Introduction", "<!-- research-os:kind=result; artifacts=missing.csv -->\nFinding."),
                ("Related Work", "Sensitive manuscript prose."),
            )
        ),
        _context(),
    )

    assert {"KIND_NOT_ALLOWED_IN_SECTION", "UNANNOTATED_BLOCK"} <= set(_codes(audit))
    assert "prose" not in {field.name for field in fields(audit.issues[0])}
    assert all("Sensitive manuscript prose." not in issue.message for issue in audit.issues)


def test_missing_and_duplicate_sections_and_parser_issues_are_carried_to_audit() -> None:
    duplicate = audit_parsed_manuscript(
        parse_manuscript(
            "## Abstract\n"
            "<!-- research-os:kind=fact; claims=FACT-1 -->\nSummary.\n\n"
            "## Abstract\n"
            "<!-- research-os:kind=fact; claims=FACT-1 -->\nRepeated summary.\n\n"
            "## Introduction\n"
            "<!-- research-os:kind=fact; claims=FACT-1 -->\nIntroduction.\n\n"
            "## Related Work\n\n## Methods\n\n## Experiments\n\n## Results\n\n"
            "## Limitations and Ethics\n"
            "<!-- research-os:kind=limitation; claims=FACT-1 -->\nLimit.\n\n"
            "## Conclusion\n"
        ),
        _context(),
    )
    malformed = audit_parsed_manuscript(
        parse_manuscript(
            _valid_document(
                ("Introduction", "<!-- research-os:kind=fact; claims=FACT-1; bad=x -->\nText."),
                ("Related Work", "<!-- research-os:kind=fact; claims=FACT-1 -->"),
            )
        ),
        _context(),
    )

    assert "DUPLICATE_SECTION" in _codes(duplicate)
    assert len([issue for issue in duplicate.issues if issue.code == "DUPLICATE_SECTION"]) == 1
    assert "INVALID_ANNOTATION" in _codes(malformed)
    assert "ORPHAN_ANNOTATION" in _codes(malformed)


def test_missing_required_section_is_reported() -> None:
    audit = audit_parsed_manuscript(
        parse_manuscript(
            _valid_document().replace("## Conclusion\n", "")
        ),
        _context(),
    )

    assert "MISSING_SECTION" in _codes(audit)


def test_issues_are_sorted_stably_by_line_code_claim_ids_and_artifact_names() -> None:
    audit = audit_parsed_manuscript(
        parse_manuscript(
            _valid_document(
                ("Introduction", "<!-- research-os:kind=result; artifacts=missing.csv -->\nFinding."),
                ("Related Work", "<!-- research-os:kind=fact; claims=UNKNOWN -->\nStatement."),
            )
        ),
        _context(),
    )

    assert list(audit.issues) == sorted(
        audit.issues,
        key=lambda issue: (issue.line, issue.code, issue.claim_ids, issue.artifact_names),
    )
