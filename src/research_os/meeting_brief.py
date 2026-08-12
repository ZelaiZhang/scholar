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
from research_os.evidence import ValidationIssue, load_ledger, validate_ledger
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
class MeetingBrief:
    schema_version: int
    as_of: str
    project: ProjectStatus
    supported_claims: tuple[BriefClaim, ...]
    conflicted_claims: tuple[BriefClaim, ...]
    open_claims: tuple[BriefClaim, ...]
    excluded_claims: tuple[ExcludedClaim, ...]
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

    assert_directory_identity(project, project_identity, context="project")
    return MeetingBrief(
        schema_version=1,
        as_of=as_of.isoformat(),
        project=snapshot.project,
        supported_claims=tuple(supported),
        conflicted_claims=tuple(conflicted),
        open_claims=tuple(open_claims),
        excluded_claims=tuple(excluded),
        recommendations=snapshot.recommendations,
        risks=snapshot.risks,
        actions=snapshot.actions,
    )
