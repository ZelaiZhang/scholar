from __future__ import annotations

from dataclasses import fields, replace
from datetime import date
import hashlib
from pathlib import Path

import pytest

import research_os.manuscript_audit as manuscript_audit
from research_os.dashboard import ProjectStatus
from research_os.evidence import ValidationIssue
from research_os.guidance import StageView
from research_os.manuscript_audit import AuditContext, audit_parsed_manuscript
from research_os.manuscript_markup import parse_manuscript
from research_os.manuscript_plan import (
    ManuscriptAction,
    ManuscriptPlan,
    SectionReadiness,
    build_manuscript_plan,
    manuscript_plan_from_brief,
)
from research_os.meeting_brief import (
    BriefClaim,
    BriefIdea,
    BriefIdeaState,
    EvidenceReference,
    ExcludedClaim,
    MeetingBrief,
)
from research_os.result_inputs import (
    ResultArtifact,
    ResultInputSnapshot,
    load_result_inputs,
)
from research_os.io import directory_identity
from research_os.project import create_project


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


def _ready_but_blocked_plan() -> ManuscriptPlan:
    idea = BriefIdea(
        run_id="run-1",
        idea_id="IDEA-1",
        title="Bounded Idea",
        scientific_question="A public research question.",
        hypothesis="A bounded hypothesis.",
        contribution="A bounded contribution.",
        evidence_source_ids=("source-1",),
        novelty_status="checked",
        scores=(("novelty", 1),),
        method_risks=("Risk.",),
        medical_safety_risks=("No clinical decision support.",),
        failure_criterion="A public criterion.",
        external_experiment="A public external experiment.",
        status="selected",
        decision_reason="Approved by researcher.",
    )
    progress = tuple(
        StageView(code, code, "complete", "complete", "complete")
        for code in (
            "problem_definition",
            "evidence_synthesis",
            "idea_review",
            "experiment_design",
            "result_interpretation",
        )
    )
    brief = MeetingBrief(
        schema_version=1,
        as_of="2026-08-13",
        project=PROJECT,
        supported_claims=(_claim("FACT-1", "fact"),),
        conflicted_claims=(),
        open_claims=(),
        excluded_claims=(
            ExcludedClaim(
                "EXCLUDED-1",
                "Excluded routed statement.",
                (ValidationIssue("invalid", "EXCLUDED-1", "Invalid."),),
            ),
        ),
        idea_state=BriefIdeaState("run-1", "completed", False, ("IDEA-1",), True, True, True, True),
        ideas=(idea,),
        questions=(),
        recommendations=(),
        risks=(),
        actions=(),
        stages=progress,
    )
    plan = manuscript_plan_from_brief(brief)
    assert all(section.status == "ready" for section in plan.sections)
    assert plan.overall_status == "blocked"
    return plan


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


def test_blocked_real_manuscript_plan_cannot_pass_even_when_sections_are_ready() -> None:
    plan = _ready_but_blocked_plan()
    context = AuditContext(
        plan,
        ("IDEA-1",),
        ResultInputSnapshot((), "valid", None, None),
    )
    audit = audit_parsed_manuscript(
        parse_manuscript(_valid_document()),
        context,
    )

    plan_issues = [issue for issue in audit.issues if issue.code == "PLAN_BLOCKED"]
    assert audit.status == "issues"
    assert len(plan_issues) == 1
    assert plan_issues[0].section == ""
    assert plan_issues[0].block_index == 0
    assert plan_issues[0].line == 0


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


def test_mixed_limitation_claims_do_not_satisfy_limitation_gate() -> None:
    audit = audit_parsed_manuscript(
        parse_manuscript(
            _document(
                (
                    "Limitations and Ethics",
                    "<!-- research-os:kind=limitation; claims=FACT-1,UNKNOWN -->\nLimit.",
                ),
            )
        ),
        _context(),
    )

    assert {"UNKNOWN_CLAIM", "LIMITATION_MISSING"} <= set(_codes(audit))


def test_limitation_in_disallowed_section_does_not_satisfy_limitation_gate() -> None:
    audit = audit_parsed_manuscript(
        parse_manuscript(
            _document(
                (
                    "Methods",
                    "<!-- research-os:kind=limitation; claims=FACT-1 -->\nLimit.",
                ),
            )
        ),
        _context(),
    )

    assert {"KIND_NOT_ALLOWED_IN_SECTION", "LIMITATION_MISSING"} <= set(_codes(audit))


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


@pytest.mark.parametrize("kind", ["inference", "hypothesis"])
def test_conflicted_research_statement_is_valid_at_its_exact_type(kind: str) -> None:
    claim_id = f"CONFLICT-{kind.upper()}"
    context = _context()
    context = replace(
        context,
        plan=replace(context.plan, conflicts=(_claim(claim_id, kind, status="conflicted"),)),
    )
    audit = audit_parsed_manuscript(
        parse_manuscript(
            _valid_document(
                ("Introduction", f"<!-- research-os:kind={kind}; claims={claim_id} -->\nStatement.")
            )
        ),
        context,
    )

    assert audit.status == "pass"
    assert claim_id in audit.used_claim_ids


def test_conflicted_fact_and_opposite_type_are_not_valid_research_statements() -> None:
    context = _context()
    context = replace(
        context,
        plan=replace(
            context.plan,
            conflicts=(
                _claim("CONFLICT-FACT", "fact", status="conflicted"),
                _claim("CONFLICT-HYPOTHESIS", "hypothesis", status="conflicted"),
            ),
        ),
    )
    audit = audit_parsed_manuscript(
        parse_manuscript(
            _valid_document(
                (
                    "Introduction",
                    "<!-- research-os:kind=inference; claims=CONFLICT-FACT,CONFLICT-HYPOTHESIS -->\nStatement.",
                )
            )
        ),
        context,
    )

    assert _codes(audit).count("CLAIM_KIND_MISMATCH") == 2


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


def test_method_annotation_rejects_retained_selection_from_incomplete_cycle() -> None:
    context = _context(selected_idea_ids=("IDEA-1",))
    context = replace(context, cycle_state="awaiting_human_decision")

    audit = audit_parsed_manuscript(
        parse_manuscript(
            _valid_document(
                ("Methods", "<!-- research-os:kind=method; idea=IDEA-1 -->\nMethod.")
            )
        ),
        context,
    )

    assert audit.status == "issues"
    assert {"IDEA_NOT_SELECTED", "PLAN_BLOCKED"} <= set(_codes(audit))


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


def test_audit_accepts_artifact_from_real_validated_result_snapshot(tmp_path: Path) -> None:
    project = tmp_path / "project"
    artifacts = project / "artifacts"
    artifacts.mkdir(parents=True)
    result = artifacts / "metrics.csv"
    result.write_text("metric,value\nscore,1\n", encoding="utf-8")
    digest = hashlib.sha256(result.read_bytes()).hexdigest()
    (artifacts / "results-manifest.yaml").write_text(
        "schema_version: 1\nresults:\n"
        "  - path: metrics.csv\n"
        f"    sha256: {digest}\n"
        "    source_repository: public-repository\n"
        "    generated_at: '2026-08-13T00:00:00Z'\n",
        encoding="utf-8",
    )
    snapshot = load_result_inputs(project, directory_identity(project))

    audit = audit_parsed_manuscript(
        parse_manuscript(
            _valid_document(
                ("Results", "<!-- research-os:kind=result; artifacts=metrics.csv -->\nFinding.")
            )
        ),
        AuditContext(_context().plan, (), snapshot),
    )

    assert audit.status == "pass"
    assert audit.used_result_artifacts == ("metrics.csv",)


@pytest.mark.parametrize(
    "analysis_body",
    (
        "```markdown\n{binding}\n{marker}\n```",
        "<!-- archived example\n{binding}\n{marker}\n-->",
        "<!-- first --><!-- archived example\n{binding}\n{marker}\n-->",
        "    {binding}\n    {marker}",
        "{marker}\n{binding}",
        "{binding}\n{marker}\n{marker}",
    ),
)
def test_audit_blocks_results_for_non_live_or_invalid_completion(
    tmp_path: Path,
    analysis_body: str,
) -> None:
    project = create_project(tmp_path, "Public project", "public-project")
    (project / "05-experiment-design.md").write_text(
        "# Experiment design\n\nReviewed design.\n\n"
        "<!-- research-os:stage=design-complete -->\n",
        encoding="utf-8",
    )
    result = project / "artifacts" / "metrics.csv"
    result.write_text("metric,value\nscore,1\n", encoding="utf-8")
    digest = hashlib.sha256(result.read_bytes()).hexdigest()
    (project / "artifacts" / "results-manifest.yaml").write_text(
        "schema_version: 1\nresults:\n"
        "  - path: metrics.csv\n"
        f"    sha256: {digest}\n"
        "    source_repository: public-repository\n"
        "    generated_at: '2026-08-13T00:00:00Z'\n",
        encoding="utf-8",
    )
    binding = (
        "<!-- research-os:result-input name=metrics.csv; "
        f"sha256={digest} -->"
    )
    (project / "06-result-analysis.md").write_text(
        "# Result analysis\n\nHuman interpretation.\n\n"
        + analysis_body.format(
            binding=binding,
            marker="<!-- research-os:stage=result-complete -->",
        )
        + "\n",
        encoding="utf-8",
    )
    plan = build_manuscript_plan(
        tmp_path,
        project.name,
        as_of=date(2026, 8, 13),
    )
    snapshot = load_result_inputs(project, directory_identity(project))

    audit = audit_parsed_manuscript(
        parse_manuscript(
            _valid_document(
                (
                    "Results",
                    "<!-- research-os:kind=result; artifacts=metrics.csv -->\nFinding.",
                )
            )
        ),
        AuditContext(plan, (), snapshot),
    )

    assert "SECTION_PARTIAL" in _codes(audit)
    assert next(section for section in plan.sections if section.code == "results").status == "partial"


def test_many_method_and_partial_result_blocks_scale_linearly() -> None:
    assert not hasattr(manuscript_audit, "_has_block_issue")
    artifact = ResultArtifact(
        "registered.csv", Path("registered.csv"), "0" * 64, "public", "2026-08-13T00:00:00Z", (1, 1)
    )

    def audit_many(block_count: int) -> object:
        method_blocks = "\n\n".join(
            "<!-- research-os:kind=method; idea=IDEA-1 -->\nMethod."
            for _ in range(block_count)
        )
        result_blocks = "\n\n".join(
            "<!-- research-os:kind=result; artifacts=registered.csv -->\nFinding."
            for _ in range(block_count)
        )
        return audit_parsed_manuscript(
            parse_manuscript(
                _valid_document(("Methods", method_blocks), ("Results", result_blocks))
            ),
            _context(
                statuses={"methods": "partial", "results": "partial"},
                selected_idea_ids=("IDEA-1",),
                artifacts=(artifact,),
            ),
        )

    small = audit_many(300)
    large = audit_many(2400)

    assert large.block_counts[-2:] == (("method", 2400), ("result", 2400))
    assert _codes(large).count("SECTION_PARTIAL") == 4800
    assert large.used_result_artifacts == ("registered.csv",)
    assert small.status == "issues"


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


def test_non_citable_limitation_issue_message_is_kind_neutral() -> None:
    context = _context()
    context = replace(
        context,
        plan=replace(
            context.plan,
            citation_candidates=(replace(_claim("OPEN-LIMIT", "fact"), support=()),),
        ),
    )
    audit = audit_parsed_manuscript(
        parse_manuscript(
            _document(
                (
                    "Limitations and Ethics",
                    "<!-- research-os:kind=limitation; claims=OPEN-LIMIT -->\nLimit.",
                )
            )
        ),
        context,
    )

    issue = next(issue for issue in audit.issues if issue.code == "CLAIM_NOT_CITABLE")
    assert "Fact annotation" not in issue.message


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
