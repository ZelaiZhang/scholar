from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from research_os.cycle import load_active_cycle
from research_os.dashboard_risks import (
    DashboardRisk,
    RiskFacts,
    evaluate_dashboard_risks,
)
from research_os.evidence import ValidationIssue, load_ledger, validate_ledger
from research_os.guidance import GuideReport, guide_project
from research_os.ideas import load_idea_archive
from research_os.knowledge import load_profile
from research_os.knowledge_recommend import KnowledgeRecommendation
from research_os.project import (
    _is_link_or_reparse_point,
    load_project_manifest,
    resolve_project_path,
    resolve_workspace_directory,
)
from research_os.sources import SourceRegistry


@dataclass(frozen=True)
class ProjectStatus:
    title: str
    slug: str
    stage: str
    state: str
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceHealth:
    linked_sources: int
    verified_sources: int
    stale_or_unknown_source_ids: tuple[str, ...]
    claims: int
    support_links: int
    opposition_links: int
    conflicted_claims: int
    claims_with_limitations: int
    validation_issues: tuple[ValidationIssue, ...]


@dataclass(frozen=True)
class IdeaStatus:
    run_id: str
    cycle_state: str
    candidate_count: int
    selected_idea_ids: tuple[str, ...]
    human_decision_required: bool
    calls_used: int
    max_calls: int


@dataclass(frozen=True)
class DashboardAction:
    code: str
    priority: int
    category: str
    rationale: str
    expected_artifact: str
    command: str


@dataclass(frozen=True)
class ProjectDashboard:
    schema_version: int
    as_of: str
    project: ProjectStatus
    evidence: EvidenceHealth
    idea: IdeaStatus
    recommendations: tuple[KnowledgeRecommendation, ...]
    risks: tuple[DashboardRisk, ...]
    actions: tuple[DashboardAction, ...]


def _safe_direct_file(
    parent: Path,
    name: str,
    *,
    required: bool,
) -> Path | None:
    if Path(name).name != name:
        raise ValueError(f"不安全的内部文件名: {name}")
    path = parent / name
    if _is_link_or_reparse_point(path):
        raise ValueError(f"课题文件不能是符号链接或目录联接: {path}")
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return None
    if not path.is_file() or path.resolve().parent != parent.resolve():
        raise ValueError(f"课题文件必须是父目录内的普通文件: {path}")
    return path


def _safe_direct_directory(
    parent: Path,
    name: str,
    *,
    required: bool,
) -> Path | None:
    if Path(name).name != name:
        raise ValueError(f"不安全的内部目录名: {name}")
    path = parent / name
    if _is_link_or_reparse_point(path):
        raise ValueError(f"课题目录不能是符号链接或目录联接: {path}")
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return None
    if not path.is_dir() or path.resolve().parent != parent.resolve():
        raise ValueError(f"课题目录必须是父目录内的真实目录: {path}")
    return path


def _preflight_project_inputs(project: Path) -> None:
    _safe_direct_file(project, "project.yaml", required=False)
    _safe_direct_file(project, "02-evidence-ledger.yaml", required=True)
    _safe_direct_file(project, "knowledge-profile.yaml", required=False)
    ideas = _safe_direct_directory(project, "ideas", required=False)
    if ideas is not None:
        _safe_direct_file(ideas, "archive.yaml", required=False)


def _project_status(report: GuideReport) -> ProjectStatus:
    active_stage = next(
        (stage for stage in report.stages if stage.status != "已产出"),
        report.stages[-1],
    )
    blockers = tuple(
        stage.detail for stage in report.stages if stage.status == "受阻"
    )
    if blockers:
        state = "blocked"
    elif report.next_action.command.startswith("research-os approve-idea "):
        state = "awaiting_human"
    elif active_stage.status == "进行中":
        state = "in_progress"
    else:
        state = "ready"
    return ProjectStatus(
        title=report.title,
        slug=report.slug,
        stage=active_stage.name,
        state=state,
        blockers=blockers,
    )


def _valid_lane_count(raw_claim: object, lane_name: str, known_ids: set[str]) -> int:
    if not isinstance(raw_claim, dict):
        return 0
    lane = raw_claim.get(lane_name, [])
    if not isinstance(lane, list):
        return 0
    return sum(
        1
        for source in lane
        if isinstance(source, dict)
        and str(source.get("source_id", "")).strip() in known_ids
        and bool(str(source.get("locator", "")).strip())
    )


def _evidence_health(
    ledger: dict[str, object],
    *,
    linked_source_ids: tuple[str, ...],
    verified_source_ids: set[str],
) -> EvidenceHealth:
    known_ids = set(linked_source_ids) & verified_source_ids
    issues = tuple(validate_ledger(ledger, known_source_ids=known_ids))
    raw_claims = ledger.get("claims", [])
    claims = raw_claims if isinstance(raw_claims, list) else []
    mappings = [claim for claim in claims if isinstance(claim, dict)]
    return EvidenceHealth(
        linked_sources=len(linked_source_ids),
        verified_sources=len(known_ids),
        stale_or_unknown_source_ids=tuple(
            source_id
            for source_id in linked_source_ids
            if source_id not in verified_source_ids
        ),
        claims=len(mappings),
        support_links=sum(
            _valid_lane_count(claim, "support", known_ids) for claim in mappings
        ),
        opposition_links=sum(
            _valid_lane_count(claim, "opposition", known_ids) for claim in mappings
        ),
        conflicted_claims=sum(
            1 for claim in mappings if claim.get("status") == "conflicted"
        ),
        claims_with_limitations=sum(
            1 for claim in mappings if str(claim.get("limitations", "")).strip()
        ),
        validation_issues=issues,
    )


def _idea_status(
    workspace: Path,
    project: Path,
    *,
    slug: str,
    allowed_source_ids: set[str],
) -> IdeaStatus:
    if not (project / "cycles").exists():
        return IdeaStatus("", "not_started", 0, (), False, 0, 0)
    _run_dir, manifest = load_active_cycle(workspace, slug)
    ideas = _safe_direct_directory(project, "ideas", required=True)
    if ideas is None:
        raise FileNotFoundError(project / "ideas")
    archive_path = _safe_direct_file(ideas, "archive.yaml", required=True)
    if archive_path is None:
        raise FileNotFoundError(ideas / "archive.yaml")
    archive = load_idea_archive(
        archive_path,
        allowed_source_ids=allowed_source_ids,
    )
    active_ideas = tuple(
        idea for idea in archive.ideas if idea.generated_by_run == manifest.run_id
    )
    selected = tuple(
        idea.idea_id for idea in active_ideas if idea.status == "selected"
    )
    return IdeaStatus(
        run_id=manifest.run_id,
        cycle_state=manifest.state,
        candidate_count=len(active_ideas),
        selected_idea_ids=selected,
        human_decision_required=manifest.state == "awaiting_human_decision",
        calls_used=manifest.calls_used,
        max_calls=manifest.max_calls,
    )


def _profile_facts(project: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    path = _safe_direct_file(
        project,
        "knowledge-profile.yaml",
        required=False,
    )
    if path is None:
        return (), ()
    profile = load_profile(path)
    return profile.domains, profile.tracks


def _dashboard_actions(
    report: GuideReport,
    risks: tuple[DashboardRisk, ...],
) -> tuple[DashboardAction, ...]:
    candidates: list[DashboardAction] = []
    blocking = tuple(risk for risk in risks if risk.severity == "blocking")
    if blocking:
        candidates.append(
            DashboardAction(
                code="REPAIR_PROJECT_BLOCKER",
                priority=10,
                category="repair",
                rationale="；".join(risk.message for risk in blocking),
                expected_artifact="project.yaml / 02-evidence-ledger.yaml",
                command=report.next_action.command,
            )
        )
    candidates.append(
        DashboardAction(
            code="ADVANCE_CURRENT_GATE",
            priority=20,
            category="workflow",
            rationale=report.next_action.reason,
            expected_artifact=report.next_action.target,
            command=report.next_action.command,
        )
    )
    if report.method_references:
        candidates.append(
            DashboardAction(
                code="REVIEW_METHOD_GUIDANCE",
                priority=40,
                category="methodology",
                rationale="当前阶段已有可用的方法学来源、手册或报告规范。",
                expected_artifact="方法学检查记录",
                command=(
                    f"research-os kb recommend --project {report.slug} "
                    "--workspace ."
                ),
            )
        )
    ordered = sorted(candidates, key=lambda action: (action.priority, action.code))
    unique: list[DashboardAction] = []
    seen_commands: set[str] = set()
    for action in ordered:
        if action.command in seen_commands:
            continue
        seen_commands.add(action.command)
        unique.append(action)
    return tuple(unique[:3])


def build_project_dashboard(
    workspace: Path,
    slug: str,
    *,
    as_of: date,
) -> ProjectDashboard:
    if not isinstance(as_of, date):
        raise TypeError("as_of must be a date")
    workspace = workspace.resolve()
    project = resolve_project_path(workspace, slug, require_exists=True)
    _preflight_project_inputs(project)
    manifest = load_project_manifest(project, allow_legacy=True)
    library = resolve_workspace_directory(workspace, "library")
    registry = SourceRegistry(library / "sources.jsonl")
    verified_source_ids = registry.verified_source_ids()
    ledger = load_ledger(project / "02-evidence-ledger.yaml")
    guide = guide_project(workspace, slug)
    if guide.knowledge_issue:
        raise ValueError(guide.knowledge_issue)
    evidence = _evidence_health(
        ledger,
        linked_source_ids=manifest.source_ids,
        verified_source_ids=verified_source_ids,
    )
    idea = _idea_status(
        workspace,
        project,
        slug=slug,
        allowed_source_ids=set(manifest.source_ids),
    )
    profile_domains, profile_tracks = _profile_facts(project)
    experiment_design = next(
        stage for stage in guide.stages if stage.name == "实验设计"
    )
    risks = evaluate_dashboard_risks(
        RiskFacts(
            stale_source_ids=evidence.stale_or_unknown_source_ids,
            ledger_issue_codes=tuple(
                sorted({issue.code for issue in evidence.validation_issues})
            ),
            cycle_state=idea.cycle_state,
            human_decision_required=idea.human_decision_required,
            profile_domains=profile_domains,
            profile_tracks=profile_tracks,
            experiment_design_status=experiment_design.status,
        )
    )
    return ProjectDashboard(
        schema_version=1,
        as_of=as_of.isoformat(),
        project=_project_status(guide),
        evidence=evidence,
        idea=idea,
        recommendations=guide.method_references[:3],
        risks=risks,
        actions=_dashboard_actions(guide, risks),
    )
