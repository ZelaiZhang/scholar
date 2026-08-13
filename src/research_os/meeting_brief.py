from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from research_os.dashboard import (
    DashboardAction,
    DashboardRisk,
    IdeaStatus,
    ProjectStatus,
    build_project_dashboard,
)
from research_os.cycle import (
    cycle_snapshot_token,
    load_active_cycle_snapshot,
    validate_cycle_artifacts,
)
from research_os.evidence import ValidationIssue, load_ledger, validate_ledger
from research_os.guidance import StageView
from research_os.ideas import load_idea_archive
from research_os.io import (
    assert_directory_identity,
    direct_file_identity,
    directory_identity,
)
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
class BriefIdeaState:
    run_id: str
    cycle_state: str
    human_decision_required: bool
    selected_idea_ids: tuple[str, ...]
    candidate_generation_complete: bool
    novelty_check_complete: bool
    independent_review_complete: bool
    meta_review_complete: bool


@dataclass(frozen=True)
class MeetingBrief:
    schema_version: int
    as_of: str
    project: ProjectStatus
    supported_claims: tuple[BriefClaim, ...]
    conflicted_claims: tuple[BriefClaim, ...]
    open_claims: tuple[BriefClaim, ...]
    excluded_claims: tuple[ExcludedClaim, ...]
    idea_state: BriefIdeaState
    ideas: tuple[BriefIdea, ...]
    questions: tuple[DiscussionQuestion, ...]
    recommendations: tuple[KnowledgeRecommendation, ...]
    risks: tuple[DashboardRisk, ...]
    actions: tuple[DashboardAction, ...]
    stages: tuple[StageView, ...]


def _reference_payload(reference: EvidenceReference) -> dict[str, str]:
    return {
        "source_id": reference.source_id,
        "locator": reference.locator,
    }


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


def meeting_brief_payload(brief: MeetingBrief) -> dict[str, object]:
    return {
        "schema_version": brief.schema_version,
        "as_of": brief.as_of,
        "project": {
            "title": brief.project.title,
            "slug": brief.project.slug,
            "stage": brief.project.stage,
            "state": brief.project.state,
            "blockers": list(brief.project.blockers),
        },
        "evidence": {
            "supported": [_claim_payload(item) for item in brief.supported_claims],
            "conflicted": [_claim_payload(item) for item in brief.conflicted_claims],
            "open": [_claim_payload(item) for item in brief.open_claims],
            "excluded": [
                {
                    "claim_id": item.claim_id,
                    "statement": item.statement,
                    "issues": [
                        {
                            "code": issue.code,
                            "message": issue.message,
                        }
                        for issue in item.issues
                    ],
                }
                for item in brief.excluded_claims
            ],
        },
        "idea_state": {
            "run_id": brief.idea_state.run_id,
            "cycle_state": brief.idea_state.cycle_state,
            "human_decision_required": (
                brief.idea_state.human_decision_required
            ),
            "selected_idea_ids": list(brief.idea_state.selected_idea_ids),
            "candidate_generation_complete": (
                brief.idea_state.candidate_generation_complete
            ),
            "novelty_check_complete": (
                brief.idea_state.novelty_check_complete
            ),
            "independent_review_complete": (
                brief.idea_state.independent_review_complete
            ),
            "meta_review_complete": brief.idea_state.meta_review_complete,
        },
        "ideas": [
            {
                "run_id": item.run_id,
                "idea_id": item.idea_id,
                "title": item.title,
                "scientific_question": item.scientific_question,
                "hypothesis": item.hypothesis,
                "contribution": item.contribution,
                "evidence_source_ids": list(item.evidence_source_ids),
                "novelty_status": item.novelty_status,
                "scores": dict(item.scores),
                "method_risks": list(item.method_risks),
                "medical_safety_risks": list(item.medical_safety_risks),
                "failure_criterion": item.failure_criterion,
                "external_experiment": item.external_experiment,
                "status": item.status,
                "decision_reason": item.decision_reason,
            }
            for item in brief.ideas
        ],
        "discussion_questions": [
            {
                "code": item.code,
                "prompt": item.prompt,
                "rationale": item.rationale,
            }
            for item in brief.questions
        ],
        "recommendations": [
            {
                "kind": item.kind,
                "title": item.title,
                "source_id": item.source_id,
                "reason": item.reason,
                "verification_scope": item.verification_scope,
                "can_use_for": item.can_use_for,
                "cannot_use_for": item.cannot_use_for,
                "path": str(item.path) if item.path is not None else None,
            }
            for item in brief.recommendations
        ],
        "risks": [
            {
                "code": item.code,
                "severity": item.severity,
                "state": item.state,
                "message": item.message,
                "trigger": item.trigger,
            }
            for item in brief.risks
        ],
        "actions": [
            {
                "code": item.code,
                "priority": item.priority,
                "category": item.category,
                "rationale": item.rationale,
                "expected_artifact": item.expected_artifact,
                "command": item.command,
            }
            for item in brief.actions
        ],
    }


def _render_references(references: tuple[EvidenceReference, ...]) -> str:
    if not references:
        return "-"
    return "；".join(
        f"source_id=`{item.source_id}`，locator=`{item.locator}`"
        for item in references
    )


def _render_claim_section(
    title: str,
    claims: tuple[BriefClaim, ...],
) -> list[str]:
    lines = [f"## {title}", ""]
    if not claims:
        return lines + ["- 无。", ""]
    for item in claims:
        lines.extend(
            [
                f"### {item.claim_id} · {item.claim_type}/{item.status}",
                "",
                f"- 陈述: {item.statement}",
                f"- 置信度: {item.confidence}",
                f"- 支持: {_render_references(item.support)}",
                f"- 反对: {_render_references(item.opposition)}",
                f"- 限制: {item.limitations}",
                "",
            ]
        )
    return lines


def render_meeting_brief(brief: MeetingBrief) -> str:
    lines = [
        f"# {brief.project.title} · 组会研究决策简报",
        "",
        f"- 课题: `{brief.project.slug}`",
        f"- 截止日期: {brief.as_of}",
        f"- 当前阶段/状态: {brief.project.stage} / {brief.project.state}",
        (
            f"- Idea 循环: {brief.idea_state.cycle_state}；"
            f"人工决策={'需要' if brief.idea_state.human_decision_required else '当前不需要'}；"
            f"已选={', '.join(brief.idea_state.selected_idea_ids) or '-'}"
        ),
        "- 边界: 只读、本地、无外部 API；本简报不是临床决策支持。",
        "",
    ]
    lines.extend(_render_claim_section("已支持的结论", brief.supported_claims))
    lines.extend(_render_claim_section("存在冲突的结论", brief.conflicted_claims))
    lines.extend(_render_claim_section("仍待核验的主张", brief.open_claims))
    lines.extend(["## 因证据问题而排除", ""])
    if brief.excluded_claims:
        for item in brief.excluded_claims:
            issue_text = "；".join(
                f"{issue.code}: {issue.message}" for issue in item.issues
            )
            lines.append(
                f"- `{item.claim_id}` {item.statement or '-'}（{issue_text or '结构无效'}）"
            )
        lines.append("")
    else:
        lines.extend(["- 无。", ""])
    lines.extend(["## 当前 Idea 与失败边界", ""])
    if brief.ideas:
        for idea in brief.ideas:
            scores = "，".join(f"{key}={value}" for key, value in idea.scores)
            lines.extend(
                [
                    f"### {idea.idea_id} · {idea.title} [{idea.status}]",
                    "",
                    f"- 科学问题: {idea.scientific_question}",
                    f"- 假设: {idea.hypothesis}",
                    f"- 贡献: {idea.contribution}",
                    f"- 证据来源: {', '.join(idea.evidence_source_ids) or '-'}",
                    f"- 新颖性/评分: {idea.novelty_status}；{scores}",
                    f"- 方法风险: {'；'.join(idea.method_risks) or '-'}",
                    f"- 医疗安全风险: {'；'.join(idea.medical_safety_risks) or '-'}",
                    f"- 失败判据: {idea.failure_criterion}",
                    f"- 外部实验边界: {idea.external_experiment}",
                    f"- 人工决定理由: {idea.decision_reason or '-'}",
                    "",
                ]
            )
    else:
        lines.extend(["- 尚未启动或尚无通过当前门禁的 Idea。", ""])
    lines.extend(["## 需要导师讨论的问题", ""])
    if brief.questions:
        for index, item in enumerate(brief.questions, 1):
            lines.extend(
                [
                    f"{index}. **{item.prompt}**",
                    f"   - 依据: {item.rationale}",
                ]
            )
        lines.append("")
    else:
        lines.extend(["- 当前没有可由结构化事实安全生成的问题。", ""])
    lines.extend(
        [
            "## 方法学参考",
            "",
            "以下条目只用于方法指导，不会自动成为当前课题引用证据。",
        ]
    )
    if brief.recommendations:
        lines.extend(
            f"- **{item.title}** [{item.verification_scope}]：{item.reason}"
            for item in brief.recommendations
        )
    else:
        lines.append("- 当前没有可用推荐。")
    lines.extend(["", "## 下一步", ""])
    if brief.actions:
        for index, item in enumerate(brief.actions, 1):
            lines.extend(
                [
                    f"### {index}. {item.code}",
                    "",
                    f"- 原因: {item.rationale}",
                    f"- 预期产物: `{item.expected_artifact}`",
                    "",
                    "```text",
                    item.command,
                    "```",
                    "",
                ]
            )
    else:
        lines.append("- 当前没有可安全执行的行动。")
    return "\n".join(lines).rstrip() + "\n"


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
    expected: IdeaStatus,
) -> tuple[BriefIdea, ...]:
    if not expected.run_id:
        return ()
    assert_directory_identity(project, project_identity, context="project")
    run_dir, manifest, artifact_identity = load_active_cycle_snapshot(
        workspace,
        slug,
        expected_project_identity=project_identity,
    )
    if manifest.run_id != expected.run_id:
        raise ValueError(
            "active cycle changed while building meeting brief: "
            f"expected {expected.run_id}, found {manifest.run_id}"
        )
    if artifact_identity != expected.artifact_identity:
        raise ValueError(
            "active cycle changed while building meeting brief; regenerate the brief"
        )
    ideas_path = project / "ideas"
    if ideas_path.resolve().parent != project:
        raise ValueError(f"Idea directory escapes project: {ideas_path}")
    ideas_identity = directory_identity(ideas_path)
    archive_path = ideas_path / "archive.yaml"
    archive_identity = direct_file_identity(
        archive_path,
        expected_parent=ideas_path,
        expected_parent_identity=ideas_identity,
    )
    if archive_identity != expected.archive_identity:
        raise ValueError(
            "active cycle changed while building meeting brief; regenerate the brief"
        )
    archive = load_idea_archive(
        archive_path,
        allowed_source_ids=source_ids,
        expected_parent=ideas_path,
        expected_parent_identity=ideas_identity,
    )
    if direct_file_identity(
        archive_path,
        expected_parent=ideas_path,
        expected_parent_identity=ideas_identity,
    ) != expected.archive_identity:
        raise ValueError(
            "active cycle changed while building meeting brief; regenerate the brief"
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
        expected_identity=expected.artifact_identity,
    )
    if artifact_issues:
        raise ValueError(
            "meeting brief cycle artifact validation failed: "
            + "; ".join(artifact_issues)
        )
    if cycle_snapshot_token(manifest, archive) != expected.snapshot_token:
        raise ValueError(
            "active cycle changed while building meeting brief; regenerate the brief"
        )
    final_run_dir, final_manifest, final_artifact_identity = (
        load_active_cycle_snapshot(
            workspace,
            slug,
            expected_project_identity=project_identity,
        )
    )
    if final_run_dir != run_dir or final_artifact_identity != expected.artifact_identity:
        raise ValueError(
            "active cycle changed while building meeting brief; regenerate the brief"
        )
    final_archive = load_idea_archive(
        archive_path,
        allowed_source_ids=source_ids,
        expected_parent=ideas_path,
        expected_parent_identity=ideas_identity,
    )
    if direct_file_identity(
        archive_path,
        expected_parent=ideas_path,
        expected_parent_identity=ideas_identity,
    ) != expected.archive_identity:
        raise ValueError(
            "active cycle changed while building meeting brief; regenerate the brief"
        )
    if cycle_snapshot_token(final_manifest, final_archive) != expected.snapshot_token:
        raise ValueError(
            "active cycle changed while building meeting brief; regenerate the brief"
        )
    manifest = final_manifest
    archive = final_archive
    assert_directory_identity(project, project_identity, context="project")
    records = sorted(
        (
            idea
            for idea in archive.ideas
            if idea.generated_by_run == expected.run_id
            and idea.status != "rejected"
        ),
        key=lambda idea: idea.idea_id,
    )[:4]
    return tuple(
        BriefIdea(
            run_id=expected.run_id,
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
        expected=snapshot.idea,
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
    idea_state = BriefIdeaState(
        run_id=snapshot.idea.run_id,
        cycle_state=snapshot.idea.cycle_state,
        human_decision_required=snapshot.idea.human_decision_required,
        selected_idea_ids=snapshot.idea.selected_idea_ids,
        candidate_generation_complete=snapshot.idea.candidate_generation_complete,
        novelty_check_complete=snapshot.idea.novelty_check_complete,
        independent_review_complete=snapshot.idea.independent_review_complete,
        meta_review_complete=snapshot.idea.meta_review_complete,
    )
    return MeetingBrief(
        schema_version=1,
        as_of=as_of.isoformat(),
        project=snapshot.project,
        supported_claims=supported_tuple,
        conflicted_claims=conflicted_tuple,
        open_claims=open_tuple,
        excluded_claims=tuple(excluded),
        idea_state=idea_state,
        ideas=ideas,
        questions=questions,
        recommendations=snapshot.recommendations,
        risks=snapshot.risks,
        actions=snapshot.actions,
        stages=snapshot.stages,
    )
