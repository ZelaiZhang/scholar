from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

import yaml

from research_os.ideas import (
    IdeaArchive,
    IdeaRecord,
    idea_content_hash,
    load_idea_archive,
    save_idea_archive,
)
from research_os.io import atomic_write_text
from research_os.journal import append_event
from research_os.project import (
    _is_link_or_reparse_point,
    load_project_manifest,
    resolve_project_path,
)
from research_os.review import load_meta_review, load_review_bundle


DEFAULT_MAX_IDEAS = 4
DEFAULT_MAX_CALLS = 6
MAX_ARTIFACT_BYTES = 1024 * 1024
RUN_ID_PATTERN = re.compile(r"^run-[0-9]{8}T[0-9]{12}Z-[0-9a-f]{8}$")
RUN_STATES = {
    "candidate_generation",
    "novelty_check",
    "independent_review",
    "meta_review",
    "awaiting_human_decision",
    "completed",
}
MANIFEST_KEYS = {
    "schema_version",
    "run_id",
    "project_slug",
    "state",
    "created_at",
    "updated_at",
    "max_ideas",
    "max_calls",
    "calls_used",
    "candidate_sha256",
    "reviews_sha256",
    "meta_review_sha256",
    "last_error",
}


@dataclass(frozen=True)
class CycleManifest:
    schema_version: int
    run_id: str
    project_slug: str
    state: str
    created_at: str
    updated_at: str
    max_ideas: int
    max_calls: int
    calls_used: int
    candidate_sha256: str
    reviews_sha256: str
    meta_review_sha256: str
    last_error: str


@dataclass(frozen=True)
class CycleAction:
    run_id: str
    state: str
    next_action: str
    target: Path | None
    reason: str
    manifest: CycleManifest


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"run-{stamp}-{secrets.token_hex(4)}"


def _validate_bound(value: int | None, *, name: str, default: int, upper: int) -> int:
    if value is None:
        return default
    if type(value) is not int or not 1 <= value <= upper:
        raise ValueError(f"{name} must be an integer from 1 to {upper}")
    return value


def _directory_identity(path: Path) -> tuple[int, int]:
    metadata = path.stat()
    return metadata.st_dev, metadata.st_ino


def _direct_directory(parent: Path, name: str, *, create: bool) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", name):
        raise ValueError(f"unsafe internal directory name: {name}")
    candidate = parent / name
    if _is_link_or_reparse_point(candidate):
        raise ValueError(f"internal directory cannot be a link or reparse point: {candidate}")
    if create and not candidate.exists():
        parent_identity = _directory_identity(parent)
        candidate.mkdir()
        if _directory_identity(parent) != parent_identity:
            raise OSError(f"parent directory changed while creating {candidate}")
    resolved = candidate.resolve()
    if resolved.parent != parent.resolve():
        raise ValueError(f"internal directory escapes project: {resolved}")
    if not resolved.is_dir():
        raise ValueError(f"expected an internal directory: {resolved}")
    return resolved


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_payload(manifest: CycleManifest) -> dict[str, object]:
    return {
        "schema_version": manifest.schema_version,
        "run_id": manifest.run_id,
        "project_slug": manifest.project_slug,
        "state": manifest.state,
        "created_at": manifest.created_at,
        "updated_at": manifest.updated_at,
        "max_ideas": manifest.max_ideas,
        "max_calls": manifest.max_calls,
        "calls_used": manifest.calls_used,
        "candidate_sha256": manifest.candidate_sha256,
        "reviews_sha256": manifest.reviews_sha256,
        "meta_review_sha256": manifest.meta_review_sha256,
        "last_error": manifest.last_error,
    }


def save_cycle_manifest(path: Path, manifest: CycleManifest) -> None:
    _validate_manifest(manifest, expected_run_id=path.parent.name)
    identity = _directory_identity(path.parent)
    atomic_write_text(
        path,
        yaml.safe_dump(_manifest_payload(manifest), allow_unicode=True, sort_keys=False),
        expected_parent_identity=identity,
    )


def _required_string(raw: object, *, field: str, allow_empty: bool = False) -> str:
    if not isinstance(raw, str) or (not allow_empty and not raw.strip()):
        raise ValueError(f"cycle manifest {field} is invalid")
    return raw.strip()


def _validate_hash(raw: str, *, field: str, allow_empty: bool = True) -> None:
    if allow_empty and raw == "":
        return
    if not re.fullmatch(r"[0-9a-f]{64}", raw):
        raise ValueError(f"cycle manifest {field} is not a SHA-256 hash")


def _validate_manifest(
    manifest: CycleManifest, *, expected_run_id: str | None = None
) -> None:
    if manifest.schema_version != 1:
        raise ValueError("cycle manifest schema_version must be 1")
    if not RUN_ID_PATTERN.fullmatch(manifest.run_id):
        raise ValueError("cycle manifest run_id is invalid")
    if expected_run_id is not None and manifest.run_id != expected_run_id:
        raise ValueError("cycle manifest run_id does not match its directory")
    if manifest.state not in RUN_STATES:
        raise ValueError(f"unknown cycle state: {manifest.state}")
    _validate_bound(manifest.max_ideas, name="max_ideas", default=4, upper=10)
    _validate_bound(manifest.max_calls, name="max_calls", default=6, upper=20)
    if (
        type(manifest.calls_used) is not int
        or manifest.calls_used < 0
        or manifest.calls_used > manifest.max_calls
    ):
        raise ValueError("cycle manifest calls_used is invalid")
    for field in ("candidate_sha256", "reviews_sha256", "meta_review_sha256"):
        _validate_hash(getattr(manifest, field), field=field)
    for field in ("project_slug", "created_at", "updated_at"):
        _required_string(getattr(manifest, field), field=field)


def load_cycle_manifest(path: Path) -> CycleManifest:
    try:
        if path.stat().st_size > MAX_ARTIFACT_BYTES:
            raise ValueError("cycle manifest exceeds the 1 MiB limit")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cycle manifest cannot be read: {path}") from exc
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"cycle manifest is malformed: {path}") from exc
    if not isinstance(raw, dict) or set(raw) != MANIFEST_KEYS:
        raise ValueError("cycle manifest fields are invalid")
    if type(raw["schema_version"]) is not int:
        raise ValueError("cycle manifest schema_version is invalid")
    manifest = CycleManifest(
        schema_version=raw["schema_version"],
        run_id=_required_string(raw["run_id"], field="run_id"),
        project_slug=_required_string(raw["project_slug"], field="project_slug"),
        state=_required_string(raw["state"], field="state"),
        created_at=_required_string(raw["created_at"], field="created_at"),
        updated_at=_required_string(raw["updated_at"], field="updated_at"),
        max_ideas=raw["max_ideas"],
        max_calls=raw["max_calls"],
        calls_used=raw["calls_used"],
        candidate_sha256=_required_string(
            raw["candidate_sha256"], field="candidate_sha256", allow_empty=True
        ),
        reviews_sha256=_required_string(
            raw["reviews_sha256"], field="reviews_sha256", allow_empty=True
        ),
        meta_review_sha256=_required_string(
            raw["meta_review_sha256"], field="meta_review_sha256", allow_empty=True
        ),
        last_error=_required_string(raw["last_error"], field="last_error", allow_empty=True),
    )
    _validate_manifest(manifest, expected_run_id=path.parent.name)
    return manifest


def _write_work_packet(project: Path, run_dir: Path, manifest: CycleManifest) -> Path:
    template = (
        resources.files("research_os.templates")
        .joinpath("cycle-work-packet.md")
        .read_text(encoding="utf-8")
    )
    content = (
        template.replace("{{PROJECT_SLUG}}", manifest.project_slug)
        .replace("{{RUN_ID}}", manifest.run_id)
        .replace("{{MAX_IDEAS}}", str(manifest.max_ideas))
        .replace("{{MAX_CALLS}}", str(manifest.max_calls))
    )
    path = run_dir / "work-packet.md"
    atomic_write_text(path, content, expected_parent_identity=_directory_identity(run_dir))
    return path


def _record(
    project: Path,
    *,
    event_type: str,
    run_id: str,
    artifact: Path,
    summary: str,
) -> None:
    relative = artifact.resolve().relative_to(project.resolve()).as_posix()
    append_event(
        project / "research-journal.jsonl",
        event_type=event_type,
        run_id=run_id,
        actor="system",
        artifact_path=relative,
        artifact_hash=_sha256_file(artifact),
        summary=summary,
    )


def _create_run(
    project: Path,
    slug: str,
    *,
    max_ideas: int,
    max_calls: int,
) -> tuple[Path, CycleManifest]:
    cycles = _direct_directory(project, "cycles", create=True)
    run_id = _new_run_id()
    while (cycles / run_id).exists():
        run_id = _new_run_id()
    run_dir = _direct_directory(cycles, run_id, create=True)
    now = _utc_now()
    manifest = CycleManifest(
        schema_version=1,
        run_id=run_id,
        project_slug=slug,
        state="candidate_generation",
        created_at=now,
        updated_at=now,
        max_ideas=max_ideas,
        max_calls=max_calls,
        calls_used=0,
        candidate_sha256="",
        reviews_sha256="",
        meta_review_sha256="",
        last_error="",
    )
    manifest_path = run_dir / "manifest.yaml"
    save_cycle_manifest(manifest_path, manifest)
    work_packet = _write_work_packet(project, run_dir, manifest)
    atomic_write_text(
        cycles / "active-run.txt",
        run_id + "\n",
        expected_parent_identity=_directory_identity(cycles),
    )
    _record(
        project,
        event_type="run_created",
        run_id=run_id,
        artifact=manifest_path,
        summary="Created a bounded local research cycle.",
    )
    _record(
        project,
        event_type="work_packet_created",
        run_id=run_id,
        artifact=work_packet,
        summary="Created the supervised cycle work packet.",
    )
    return run_dir, manifest


def _active_run(project: Path) -> tuple[Path, CycleManifest]:
    cycles = _direct_directory(project, "cycles", create=False)
    pointer = cycles / "active-run.txt"
    try:
        run_id = pointer.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError("cycle active-run pointer is missing or unreadable") from exc
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("cycle active-run pointer is invalid")
    run_dir = _direct_directory(cycles, run_id, create=False)
    manifest = load_cycle_manifest(run_dir / "manifest.yaml")
    if manifest.project_slug != project.name:
        raise ValueError("active cycle belongs to a different project")
    return run_dir, manifest


def _ensure_archive(project: Path, slug: str, source_ids: set[str]) -> Path:
    ideas_dir = _direct_directory(project, "ideas", create=True)
    archive_path = ideas_dir / "archive.yaml"
    if archive_path.exists():
        archive = load_idea_archive(archive_path, allowed_source_ids=source_ids)
        if archive.project_slug != slug:
            raise ValueError("Idea archive belongs to a different project")
    else:
        save_idea_archive(archive_path, IdeaArchive(1, slug, ()))
    return archive_path


def _load_candidates(
    path: Path,
    *,
    manifest: CycleManifest,
    source_ids: set[str],
) -> IdeaArchive:
    if path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError("candidate artifact exceeds the 1 MiB limit")
    archive = load_idea_archive(path, allowed_source_ids=source_ids)
    if archive.project_slug != manifest.project_slug:
        raise ValueError("candidate artifact belongs to a different project")
    if not archive.ideas:
        raise ValueError("candidate artifact contains no Ideas")
    if len(archive.ideas) > manifest.max_ideas:
        raise ValueError("candidate artifact exceeds max_ideas")
    for idea in archive.ideas:
        if idea.generated_by_run != manifest.run_id:
            raise ValueError(f"candidate {idea.idea_id} belongs to a different run")
        if idea.status != "draft" or idea.researcher_decision is not None:
            raise ValueError("candidate artifacts may contain draft Ideas only")
    return archive


def _synchronize_archive(
    path: Path,
    candidates: IdeaArchive,
    *,
    source_ids: set[str],
    statuses: dict[str, str],
) -> IdeaArchive:
    current = load_idea_archive(path, allowed_source_ids=source_ids)
    ordered = list(current.ideas)
    positions = {idea.idea_id: index for index, idea in enumerate(ordered)}
    for candidate in candidates.ideas:
        prior = ordered[positions[candidate.idea_id]] if candidate.idea_id in positions else None
        if prior is not None and prior.generated_by_run != candidate.generated_by_run:
            raise ValueError(f"Idea ID already belongs to another run: {candidate.idea_id}")
        if prior is not None and prior.researcher_decision is not None:
            raise ValueError(f"cannot replace researcher-approved Idea: {candidate.idea_id}")
        replacement = replace(
            candidate,
            status=statuses[candidate.idea_id],
            researcher_decision=None,
        )
        if prior is None:
            positions[candidate.idea_id] = len(ordered)
            ordered.append(replacement)
        else:
            ordered[positions[candidate.idea_id]] = replacement
    updated = IdeaArchive(1, current.project_slug, tuple(ordered))
    save_idea_archive(path, updated)
    return updated


def _transition(
    project: Path,
    run_dir: Path,
    manifest: CycleManifest,
    new_state: str,
    **changes: str,
) -> CycleManifest:
    updated = replace(
        manifest,
        state=new_state,
        updated_at=_utc_now(),
        last_error="",
        **changes,
    )
    manifest_path = run_dir / "manifest.yaml"
    save_cycle_manifest(manifest_path, updated)
    _record(
        project,
        event_type="state_transition",
        run_id=manifest.run_id,
        artifact=manifest_path,
        summary=f"Advanced research cycle from {manifest.state} to {new_state}.",
    )
    return updated


def _action(
    manifest: CycleManifest,
    *,
    state: str | None = None,
    next_action: str,
    target: Path | None,
    reason: str,
) -> CycleAction:
    return CycleAction(
        run_id=manifest.run_id,
        state=state or manifest.state,
        next_action=next_action,
        target=target,
        reason=reason,
        manifest=manifest,
    )


def _blocked(
    manifest: CycleManifest, *, next_action: str, target: Path, reason: str
) -> CycleAction:
    return _action(
        manifest,
        state="blocked",
        next_action=next_action,
        target=target,
        reason=reason,
    )


def _reviews_digest(folder: Path) -> str:
    parts = [f"{role}:{_sha256_file(folder / f'{role}.json')}" for role in (
        "novelty",
        "methods",
        "medical-safety",
    )]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _novelty_complete(idea: IdeaRecord) -> bool:
    return (
        idea.novelty.status == "checked"
        and bool(idea.novelty.queries)
        and bool(idea.novelty.nearest_source_ids)
        and bool(idea.novelty.differences)
    )


def advance_cycle(
    workspace: Path,
    slug: str,
    *,
    new_run: bool = False,
    max_ideas: int | None = None,
    max_calls: int | None = None,
    provider: object | None = None,
) -> CycleAction:
    requested_max_ideas = _validate_bound(
        max_ideas, name="max_ideas", default=DEFAULT_MAX_IDEAS, upper=10
    )
    requested_max_calls = _validate_bound(
        max_calls, name="max_calls", default=DEFAULT_MAX_CALLS, upper=20
    )
    project = resolve_project_path(workspace, slug, require_exists=True)
    project_manifest = load_project_manifest(project)
    source_ids = set(project_manifest.source_ids)
    archive_path = _ensure_archive(project, slug, source_ids)
    cycles_path = project / "cycles"
    if new_run or not cycles_path.exists():
        run_dir, manifest = _create_run(
            project,
            slug,
            max_ideas=requested_max_ideas,
            max_calls=requested_max_calls,
        )
    else:
        run_dir, manifest = _active_run(project)
        if max_ideas is not None and requested_max_ideas != manifest.max_ideas:
            raise ValueError("max_ideas cannot change while resuming a run")
        if max_calls is not None and requested_max_calls != manifest.max_calls:
            raise ValueError("max_calls cannot change while resuming a run")

    candidates_path = run_dir / "candidates.yaml"
    reviews_dir = run_dir / "reviews"
    meta_path = run_dir / "meta-review.json"

    if provider is not None and manifest.calls_used >= manifest.max_calls:
        return _action(
            manifest,
            state="budget_exhausted",
            next_action="increase_budget_or_continue_locally",
            target=run_dir / "work-packet.md",
            reason="The provider call budget is exhausted before dispatch.",
        )

    if manifest.state == "candidate_generation":
        if not candidates_path.is_file():
            return _action(
                manifest,
                next_action="create_candidates",
                target=candidates_path,
                reason="Create a strict local candidate artifact; no model call was made.",
            )
        try:
            candidates = _load_candidates(
                candidates_path, manifest=manifest, source_ids=source_ids
            )
            _synchronize_archive(
                archive_path,
                candidates,
                source_ids=source_ids,
                statuses={idea.idea_id: "needs_novelty_check" for idea in candidates.ideas},
            )
        except (OSError, UnicodeError, ValueError) as exc:
            return _blocked(
                manifest,
                next_action="repair_candidates",
                target=candidates_path,
                reason=str(exc),
            )
        manifest = _transition(
            project,
            run_dir,
            manifest,
            "novelty_check",
            candidate_sha256=_sha256_file(candidates_path),
        )

    if manifest.state == "novelty_check":
        try:
            candidates = _load_candidates(
                candidates_path, manifest=manifest, source_ids=source_ids
            )
        except (OSError, UnicodeError, ValueError) as exc:
            return _blocked(
                manifest,
                next_action="repair_candidates",
                target=candidates_path,
                reason=str(exc),
            )
        if not all(_novelty_complete(idea) for idea in candidates.ideas):
            return _action(
                manifest,
                next_action="document_novelty",
                target=candidates_path,
                reason="Every Idea needs reproducible queries, a registered neighbour, and a concrete difference.",
            )
        try:
            _synchronize_archive(
                archive_path,
                candidates,
                source_ids=source_ids,
                statuses={idea.idea_id: "reviewed" for idea in candidates.ideas},
            )
        except ValueError as exc:
            return _blocked(
                manifest,
                next_action="repair_idea_archive",
                target=archive_path,
                reason=str(exc),
            )
        manifest = _transition(
            project,
            run_dir,
            manifest,
            "independent_review",
            candidate_sha256=_sha256_file(candidates_path),
        )

    if manifest.state in {
        "independent_review",
        "meta_review",
        "awaiting_human_decision",
        "completed",
    }:
        if not candidates_path.is_file() or _sha256_file(candidates_path) != manifest.candidate_sha256:
            return _blocked(
                manifest,
                next_action="restore_frozen_candidates",
                target=candidates_path,
                reason="The candidate artifact changed after independent review began.",
            )
        try:
            candidates = _load_candidates(
                candidates_path, manifest=manifest, source_ids=source_ids
            )
        except (OSError, UnicodeError, ValueError) as exc:
            return _blocked(
                manifest,
                next_action="restore_frozen_candidates",
                target=candidates_path,
                reason=str(exc),
            )
        candidate_ids = {idea.idea_id for idea in candidates.ideas}

    if manifest.state == "independent_review":
        review_paths = [reviews_dir / f"{role}.json" for role in (
            "novelty",
            "methods",
            "medical-safety",
        )]
        if not all(path.is_file() for path in review_paths):
            return _action(
                manifest,
                next_action="create_independent_reviews",
                target=reviews_dir,
                reason="Create all three role-separated review files.",
            )
        try:
            load_review_bundle(reviews_dir, expected_idea_ids=candidate_ids)
        except ValueError as exc:
            return _blocked(
                manifest,
                next_action="repair_independent_reviews",
                target=reviews_dir,
                reason=str(exc),
            )
        manifest = _transition(
            project,
            run_dir,
            manifest,
            "meta_review",
            reviews_sha256=_reviews_digest(reviews_dir),
        )

    if manifest.state in {"meta_review", "awaiting_human_decision", "completed"}:
        try:
            current_reviews_hash = _reviews_digest(reviews_dir)
        except OSError as exc:
            return _blocked(
                manifest,
                next_action="restore_frozen_reviews",
                target=reviews_dir,
                reason=str(exc),
            )
        if current_reviews_hash != manifest.reviews_sha256:
            return _blocked(
                manifest,
                next_action="restore_frozen_reviews",
                target=reviews_dir,
                reason="Independent review files changed after meta-review began.",
            )

    if manifest.state == "meta_review":
        if not meta_path.is_file():
            return _action(
                manifest,
                next_action="create_meta_review",
                target=meta_path,
                reason="Reconcile consensus and conflicts without selecting an Idea.",
            )
        try:
            meta = load_meta_review(
                meta_path,
                expected_idea_ids=candidate_ids,
                expected_run_id=manifest.run_id,
            )
            statuses = {
                idea.idea_id: (
                    "shortlisted" if idea.idea_id in meta.shortlist_ids else "rejected"
                )
                for idea in candidates.ideas
            }
            _synchronize_archive(
                archive_path,
                candidates,
                source_ids=source_ids,
                statuses=statuses,
            )
        except (OSError, UnicodeError, ValueError) as exc:
            return _blocked(
                manifest,
                next_action="repair_meta_review",
                target=meta_path,
                reason=str(exc),
            )
        manifest = _transition(
            project,
            run_dir,
            manifest,
            "awaiting_human_decision",
            meta_review_sha256=_sha256_file(meta_path),
        )

    if manifest.state in {"awaiting_human_decision", "completed"}:
        if not meta_path.is_file() or _sha256_file(meta_path) != manifest.meta_review_sha256:
            return _blocked(
                manifest,
                next_action="restore_frozen_meta_review",
                target=meta_path,
                reason="The meta-review changed after the human decision gate opened.",
            )
        try:
            archive = load_idea_archive(archive_path, allowed_source_ids=source_ids)
        except ValueError as exc:
            return _blocked(
                manifest,
                next_action="repair_idea_archive",
                target=archive_path,
                reason=str(exc),
            )
        frozen_by_id = {idea.idea_id: idea for idea in candidates.ideas}
        run_ideas = [
            idea for idea in archive.ideas if idea.generated_by_run == manifest.run_id
        ]
        if (
            {idea.idea_id for idea in run_ideas} != set(frozen_by_id)
            or any(
                idea_content_hash(idea) != idea_content_hash(frozen_by_id[idea.idea_id])
                for idea in run_ideas
                if idea.idea_id in frozen_by_id
            )
        ):
            return _blocked(
                manifest,
                next_action="restore_reviewed_idea",
                target=archive_path,
                reason="The Idea archive no longer matches the frozen reviewed candidates.",
            )
        selected = [
            idea
            for idea in archive.ideas
            if idea.generated_by_run == manifest.run_id and idea.status == "selected"
        ]
        if manifest.state == "awaiting_human_decision" and selected:
            manifest = _transition(project, run_dir, manifest, "completed")

    if manifest.state == "completed":
        return _action(
            manifest,
            next_action="none",
            target=None,
            reason="A researcher-approved Idea completed this guidance cycle.",
        )

    return _action(
        manifest,
        next_action="approve_or_reject_idea",
        target=archive_path,
        reason="Only the researcher may select a shortlisted Idea.",
    )
