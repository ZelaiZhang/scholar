from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from research_os.dashboard import (
    DashboardAction,
    DashboardRisk,
    ProjectStatus,
    build_project_dashboard,
)
from research_os.cycle import load_active_cycle, validate_cycle_artifacts
from research_os.evidence import ValidationIssue, load_ledger, validate_ledger
from research_os.ideas import load_idea_archive
from research_os.io import assert_directory_identity, directory_identity
from research_os.knowledge_recommend import KnowledgeRecommendation
from research_os.project import (
    load_project_manifest,
    resolve_project_path,
    resolve_workspace_directory,
)
from research_os.sources import SourceRegistry


@dataclass(frozen=True)
class EvidenceReference:
    source_id: str
    locator: str


@dataclass(frozen=True)
class BriefClaim:
    claim_id: str
    statement: str
    claim_type: str
    status: str
    confidence: str
    support: tuple[EvidenceReference, ...]
    opposition: tuple[EvidenceReference, ...]
    limitations: str


@dataclass(frozen=True)
class ExcludedClaim:
    claim_id: str
    statement: str
    issues: tuple[ValidationIssue, ...]


@dataclass(frozen=True)
class BriefIdea:
    run_id: str
    idea_id: str
    title: str
    scientific_question: str
    hypothesis: str
    contribution: str
    evidence_source_ids: tuple[str, ...]
    novelty_status: str
    scores: tuple[tuple[str, int], ...]
    method_risks: tuple[str, ...]
    medical_safety_risks: tuple[str, ...]
    failure_criterion: str
    external_experiment: str
    status: str
    decision_reason: str


@dataclass(frozen=True)
class DiscussionQuestion:
    code: str
    prompt: str
    rationale: str


@dataclass(frozen=True)
class MeetingBrief:
    schema_version: int
    as_of: str
    project: ProjectStatus
    supported_claims: tuple[BriefClaim, ...]
    conflicted_claims: tuple[BriefClaim, ...]
    open_claims: tuple[BriefClaim, ...]
    excluded_claims: tuple[ExcludedClaim, ...]
    ideas: tuple[BriefIdea, ...]
    questions: tuple[DiscussionQuestion, ...]
    recommendations: tuple[KnowledgeRecommendation, ...]
    risks: tuple[DashboardRisk, ...]
    actions: tuple[DashboardAction, ...]


def _claim_id(raw: dict[str, object], index: int) -> str:
    return str(raw.get("claim_id", "")).strip() or f"item-{index}"


def _references(raw: object) -> tuple[EvidenceReference, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(
        EvidenceReference(
            source_id=str(item["source_id"]).strip(),
            locator=str(item["locator"]).strip(),
        )
        for item in raw
        if isinstance(item, dict)
    )


def _claim(raw: dict[str, object], index: int) -> BriefClaim:
    return BriefClaim(
        claim_id=_claim_id(raw, index),
        statement=str(raw["statement"]).strip(),
        claim_type=str(raw["type"]),
        status=str(raw["status"]),
        confidence=str(raw["confidence"]),
        support=_references(raw.get("support", [])),
        opposition=_references(raw.get("opposition", [])),
        limitations=str(raw["limitations"]).strip(),
    )


def _active_ideas(
    workspace: Path,
    project: Path,
    *,
    slug: str,
    source_ids: set[str],
    project_identity: tuple[int, int],
    expected_run_id: str,
) -> tuple[BriefIdea, ...]:
    if not expected_run_id:
        return ()
    assert_directory_identity(project, project_identity, context="project")
    run_dir, manifest = load_active_cycle(
        workspace,
        slug,
        expected_project_identity=project_identity,
    )
    if manifest.run_id != expected_run_id:
        raise ValueError(
            "active cycle changed while building meeting brief: "
            f"expected {expected_run_id}, found {manifest.run_id}"
        )
    ideas_path = project / "ideas"
    if ideas_path.resolve().parent != project:
        raise ValueError(f"Idea directory escapes project: {ideas_path}")
    ideas_identity = directory_identity(ideas_path)
    archive_path = ideas_path / "archive.yaml"
    archive = load_idea_archive(
        archive_path,
        allowed_source_ids=source_ids,
        expected_parent=ideas_path,
        expected_parent_identity=ideas_identity,
    )
    if archive.project_slug != slug:
        raise ValueError(
            "Idea archive belongs to a different project: "
            f"expected {slug}, found {archive.project_slug}"
        )
    artifact_issues = validate_cycle_artifacts(
        run_dir,
        manifest,
        source_ids=source_ids,
        archive_path=archive_path,
    )
    if artifact_issues:
        raise ValueError(
            "meeting brief cycle artifact validation failed: "
            + "; ".join(artifact_issues)
        )
    assert_directory_identity(project, project_identity, context="project")
    records = sorted(
        (
            idea
            for idea in archive.ideas
            if idea.generated_by_run == expected_run_id
            and idea.status != "rejected"
        ),
        key=lambda idea: idea.idea_id,
    )[:4]
    return tuple(
        BriefIdea(
            run_id=expected_run_id,
            idea_id=idea.idea_id,
            title=idea.title,
            scientific_question=idea.scientific_question,
            hypothesis=idea.hypothesis,
            contribution=idea.contribution,
            evidence_source_ids=idea.evidence_source_ids,
            novelty_status=idea.novelty.status,
            scores=(
                ("interestingness", idea.scores.interestingness),
                ("novelty", idea.scores.novelty),
                ("feasibility", idea.scores.feasibility),
                ("evidence_support", idea.scores.evidence_support),
            ),
            method_risks=idea.method_risks,
            medical_safety_risks=idea.medical_safety_risks,
            failure_criterion=idea.failure_criterion,
            external_experiment=idea.external_experiment,
            status=idea.status,
            decision_reason=(
                idea.researcher_decision.reason
                if idea.researcher_decision is not None
                else ""
            ),
        )
        for idea in records
    )


def _discussion_questions(
    *,
    project: ProjectStatus,
    human_decision_required: bool,
    selected_idea_ids: tuple[str, ...],
    conflicted_claims: tuple[BriefClaim, ...],
    open_claims: tuple[BriefClaim, ...],
    ideas: tuple[BriefIdea, ...],
) -> tuple[DiscussionQuestion, ...]:
    questions: list[DiscussionQuestion] = []
    if project.blockers:
        questions.append(
            DiscussionQuestion(
                code="CONFIRM_BLOCKER_REPAIR",
                prompt="当前阻塞应如何修复，修复后用什么产物证明已解除？",
                rationale="课题状态包含结构化阻塞，继续推进会越过质量门禁。",
            )
        )
    if human_decision_required:
        questions.append(
            DiscussionQuestion(
                code="REVIEW_IDEA_SHORTLIST",
                prompt="候选 Idea 中哪一个值得由研究者批准，为什么？",
                rationale="三路评审与 meta-review 已完成，但系统不能替代人工选择。",
            )
        )
    elif selected_idea_ids:
        questions.append(
            DiscussionQuestion(
                code="REVIEW_SELECTED_IDEA_BOUNDARY",
                prompt="已选 Idea 的失败判据和外部实验边界是否足够严格？",
                rationale=(
                    "已选 Idea 为 " + ", ".join(selected_idea_ids)
                    + "；进入实验设计前应确认什么结果会推翻它。"
                ),
            )
        )
    if conflicted_claims:
        questions.append(
            DiscussionQuestion(
                code="PRIORITIZE_CONFLICT_RESOLUTION",
                prompt="哪些冲突 claim 最影响选题，下一轮检索应优先解决哪一个？",
                rationale=(
                    "冲突 claim: "
                    + ", ".join(item.claim_id for item in conflicted_claims)
                ),
            )
        )
    elif open_claims:
        questions.append(
            DiscussionQuestion(
                code="PRIORITIZE_EVIDENCE_GAP",
                prompt="哪些待核验 claim 必须先补证，哪些只保留为假设？",
                rationale=(
                    "待核验 claim: "
                    + ", ".join(item.claim_id for item in open_claims)
                ),
            )
        )
    if len(questions) < 3 and any(idea.method_risks for idea in ideas):
        questions.append(
            DiscussionQuestion(
                code="REVIEW_METHOD_RISK",
                prompt="当前 Idea 的首要方法风险需要什么对照或消融来排除？",
                rationale="Idea 档案已经显式记录方法风险，实验设计需逐项响应。",
            )
        )
    unique: list[DiscussionQuestion] = []
    seen: set[str] = set()
    for question in questions:
        if question.code in seen:
            continue
        seen.add(question.code)
        unique.append(question)
    return tuple(unique[:3])


def build_meeting_brief(
    workspace: Path,
    slug: str,
    *,
    as_of: date,
) -> MeetingBrief:
    if not isinstance(as_of, date):
        raise TypeError("as_of must be a date")
    workspace = workspace.resolve()
    project = resolve_project_path(workspace, slug, require_exists=True)
    project_identity = directory_identity(project)
    snapshot = build_project_dashboard(
        workspace,
        slug,
        as_of=as_of,
        expected_project_identity=project_identity,
    )
    manifest = load_project_manifest(
        project,
        allow_legacy=True,
        expected_directory_identity=project_identity,
    )
    library = resolve_workspace_directory(workspace, "library")
    verified_source_ids = SourceRegistry(
        library / "sources.jsonl"
    ).verified_source_ids()
    known_source_ids = set(manifest.source_ids) & verified_source_ids
    ledger = load_ledger(
        project / "02-evidence-ledger.yaml",
        expected_parent=project,
        expected_parent_identity=project_identity,
    )
    issues = tuple(validate_ledger(ledger, known_source_ids=known_source_ids))
    issues_by_id: dict[str, list[ValidationIssue]] = {}
    for issue in issues:
        issues_by_id.setdefault(issue.claim_id, []).append(issue)

    supported: list[BriefClaim] = []
    conflicted: list[BriefClaim] = []
    open_claims: list[BriefClaim] = []
    excluded: list[ExcludedClaim] = []
    raw_claims = ledger.get("claims", [])
    for index, raw in enumerate(raw_claims if isinstance(raw_claims, list) else [], 1):
        claim_id = (
            _claim_id(raw, index) if isinstance(raw, dict) else f"item-{index}"
        )
        claim_issues = tuple(issues_by_id.get(claim_id, ()))
        if not isinstance(raw, dict) or claim_issues:
            excluded.append(
                ExcludedClaim(
                    claim_id=claim_id,
                    statement=(
                        str(raw.get("statement", "")).strip()
                        if isinstance(raw, dict)
                        else ""
                    ),
                    issues=claim_issues,
                )
            )
            continue
        item = _claim(raw, index)
        if item.status == "conflicted":
            conflicted.append(item)
        elif item.status == "verified":
            supported.append(item)
        else:
            open_claims.append(item)

    ideas = _active_ideas(
        workspace,
        project,
        slug=slug,
        source_ids=set(manifest.source_ids),
        project_identity=project_identity,
        expected_run_id=snapshot.idea.run_id,
    )
    supported_tuple = tuple(supported)
    conflicted_tuple = tuple(conflicted)
    open_tuple = tuple(open_claims)
    questions = _discussion_questions(
        project=snapshot.project,
        human_decision_required=snapshot.idea.human_decision_required,
        selected_idea_ids=snapshot.idea.selected_idea_ids,
        conflicted_claims=conflicted_tuple,
        open_claims=open_tuple,
        ideas=ideas,
    )
    assert_directory_identity(project, project_identity, context="project")
    return MeetingBrief(
        schema_version=1,
        as_of=as_of.isoformat(),
        project=snapshot.project,
        supported_claims=supported_tuple,
        conflicted_claims=conflicted_tuple,
        open_claims=open_tuple,
        excluded_claims=tuple(excluded),
        ideas=ideas,
        questions=questions,
        recommendations=snapshot.recommendations,
        risks=snapshot.risks,
        actions=snapshot.actions,
    )
