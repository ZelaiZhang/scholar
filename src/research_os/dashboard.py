from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from research_os.evidence import ValidationIssue, load_ledger, validate_ledger
from research_os.guidance import GuideReport, guide_project
from research_os.project import (
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
class ProjectDashboard:
    schema_version: int
    as_of: str
    project: ProjectStatus
    evidence: EvidenceHealth


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
    manifest = load_project_manifest(project, allow_legacy=True)
    library = resolve_workspace_directory(workspace, "library")
    registry = SourceRegistry(library / "sources.jsonl")
    verified_source_ids = registry.verified_source_ids()
    ledger = load_ledger(project / "02-evidence-ledger.yaml")
    guide = guide_project(workspace, slug)
    return ProjectDashboard(
        schema_version=1,
        as_of=as_of.isoformat(),
        project=_project_status(guide),
        evidence=_evidence_health(
            ledger,
            linked_source_ids=manifest.source_ids,
            verified_source_ids=verified_source_ids,
        ),
    )
