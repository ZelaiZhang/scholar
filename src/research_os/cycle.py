from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

import yaml

from research_os.ideas import (
    IdeaArchive,
    IdeaRecord,
    idea_content_hash,
    approve_idea,
    load_idea_archive,
    save_idea_archive,
)
from research_os.io import (
    atomic_create_text,
    atomic_write_bytes,
    atomic_write_text,
    read_stable_direct_text,
)
from research_os.journal import append_event, validate_journal
from research_os.project import (
    _is_link_or_reparse_point,
    load_project_manifest,
    resolve_project_path,
)
from research_os.review import load_meta_review, load_review_bundle
from research_os.review import load_independent_review
from research_os.cycle_context import ExternalContextSnapshot, build_external_context


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


def cycle_snapshot_token(
    manifest: CycleManifest,
    archive: IdeaArchive,
) -> str:
    """Fingerprint the complete cycle and Idea state used by a read model."""
    payload = {
        "manifest": asdict(manifest),
        "idea_archive": asdict(archive),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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


def _assert_directory_identity(
    path: Path, expected: tuple[int, int], *, context: str
) -> None:
    if _directory_identity(path) != expected:
        raise OSError(f"{context} directory was replaced or changed: {path}")


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


def _sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _write_json(
    path: Path,
    payload: dict[str, object],
    *,
    expected_parent_identity: tuple[int, int] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    identity = expected_parent_identity or _directory_identity(path.parent)
    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        expected_parent_identity=identity,
    )


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


def save_cycle_manifest(
    path: Path,
    manifest: CycleManifest,
    *,
    expected_parent_identity: tuple[int, int] | None = None,
) -> None:
    _validate_manifest(manifest, expected_run_id=path.parent.name)
    identity = expected_parent_identity or _directory_identity(path.parent)
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
    state_rank = {
        "candidate_generation": 0,
        "novelty_check": 1,
        "independent_review": 2,
        "meta_review": 3,
        "awaiting_human_decision": 4,
        "completed": 5,
    }[manifest.state]
    for minimum_rank, field in (
        (1, "candidate_sha256"),
        (3, "reviews_sha256"),
        (4, "meta_review_sha256"),
    ):
        if state_rank >= minimum_rank and not getattr(manifest, field):
            raise ValueError(
                f"cycle manifest state {manifest.state} requires {field}"
            )
    for field in ("project_slug", "created_at", "updated_at"):
        _required_string(getattr(manifest, field), field=field)


def load_cycle_manifest(
    path: Path,
    *,
    expected_parent_identity: tuple[int, int] | None = None,
) -> CycleManifest:
    try:
        raw = yaml.safe_load(
            read_stable_direct_text(
                path,
                expected_parent=path.parent,
                expected_parent_identity=expected_parent_identity,
                max_bytes=MAX_ARTIFACT_BYTES,
            )
        )
    except OSError as exc:
        raise ValueError(f"cycle manifest cannot be read: {path}") from exc
    except (UnicodeError, yaml.YAMLError) as exc:
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
    archive = load_idea_archive(project / "ideas" / "archive.yaml")
    reserved_ids = tuple(idea.idea_id for idea in archive.ideas)
    used_numbers = {
        int(idea_id.split("-", 1)[1]) for idea_id in reserved_ids
    }
    next_number = next(
        number for number in range(1, 10000) if number not in used_numbers
    )
    content = (
        template.replace("{{PROJECT_SLUG}}", manifest.project_slug)
        .replace("{{RUN_ID}}", manifest.run_id)
        .replace("{{MAX_IDEAS}}", str(manifest.max_ideas))
        .replace("{{MAX_CALLS}}", str(manifest.max_calls))
        .replace(
            "{{RESERVED_IDEA_IDS}}",
            ", ".join(reserved_ids) if reserved_ids else "(none)",
        )
        .replace("{{SUGGESTED_IDEA_ID}}", f"idea-{next_number:04d}")
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


def _provider_public_metadata(provider: object) -> dict[str, object]:
    metadata: dict[str, object] = {}
    for field in ("base_url", "model", "temperature", "timeout"):
        value = getattr(provider, field, None)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            metadata[field] = value
    return metadata


@contextmanager
def _provider_budget_lock(
    run_dir: Path, expected_run_identity: tuple[int, int]
):
    """Serialize the durable reservation of a provider-call budget slot."""
    _assert_directory_identity(
        run_dir, expected_run_identity, context="cycle run before budget reservation"
    )
    lock_path = run_dir / ".provider-budget.lock"
    handle = lock_path.open("a+b")
    handle.seek(0, 2)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    locked = False
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        locked = True
        yield
    except OSError as exc:
        if not locked:
            raise RuntimeError(
                "another cycle process is reserving the provider budget; "
                "retry after it finishes"
            ) from exc
        raise
    finally:
        try:
            if locked:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            _assert_directory_identity(
                run_dir,
                expected_run_identity,
                context="cycle run during budget reservation",
            )


def _begin_provider_call(
    project: Path,
    run_dir: Path,
    manifest: CycleManifest,
    *,
    provider: object,
    context: ExternalContextSnapshot,
    stage: str,
    system_prompt: str,
    user_prompt: str,
    expected_run_identity: tuple[int, int],
) -> tuple[CycleManifest, int]:
    with _provider_budget_lock(run_dir, expected_run_identity):
        current = load_cycle_manifest(run_dir / "manifest.yaml")
        if current != manifest:
            raise RuntimeError(
                "cycle manifest changed concurrently; reload before provider dispatch"
            )
        if current.calls_used >= current.max_calls:
            raise RuntimeError("provider call budget is exhausted")
        call_number = current.calls_used + 1
        updated = replace(
            current,
            calls_used=call_number,
            updated_at=_utc_now(),
            last_error="",
        )
        save_cycle_manifest(
            run_dir / "manifest.yaml",
            updated,
            expected_parent_identity=expected_run_identity,
        )
        provenance_dir = _direct_directory(run_dir, "provenance", create=True)
        started = provenance_dir / f"call-{call_number:03d}-started.json"
        _write_json(
            started,
            {
                "schema_version": 1,
                "run_id": current.run_id,
                "call_number": call_number,
                "stage": stage,
                "status": "started",
                "started_at": _utc_now(),
                "provider": _provider_public_metadata(provider),
                "context_sha256": context.sha256,
                "context_source_id": context.context_source_id,
                "input_source_ids": list(context.input_source_ids),
                "system_prompt_sha256": _sha256_text(system_prompt),
                "user_prompt_sha256": _sha256_text(user_prompt),
            },
            expected_parent_identity=_directory_identity(provenance_dir),
        )
        _record(
            project,
            event_type="provider_call_started",
            run_id=current.run_id,
            artifact=started,
            summary=f"Reserved provider call {call_number} for {stage} before dispatch.",
        )
    return updated, call_number


def _finish_provider_call(
    project: Path,
    run_dir: Path,
    manifest: CycleManifest,
    *,
    call_number: int,
    stage: str,
    status: str,
    response_content: str | None,
    provider_provenance: dict[str, object] | None,
    error_type: str = "",
    expected_run_identity: tuple[int, int],
) -> Path:
    _assert_directory_identity(
        run_dir, expected_run_identity, context="cycle run after provider dispatch"
    )
    provenance_dir = _direct_directory(run_dir, "provenance", create=True)
    finished = provenance_dir / f"call-{call_number:03d}-finished.json"
    response_hash = _sha256_text(response_content) if response_content is not None else ""
    _write_json(
        finished,
        {
            "schema_version": 1,
            "run_id": manifest.run_id,
            "call_number": call_number,
            "stage": stage,
            "status": status,
            "finished_at": _utc_now(),
            "response_sha256": response_hash,
            "response_bytes": (
                len(response_content.encode("utf-8"))
                if response_content is not None
                else 0
            ),
            "provider_provenance": _sanitize_provider_provenance(
                provider_provenance or {}
            ),
            "error_type": error_type,
        },
    )
    _record(
        project,
        event_type="provider_call_finished",
        run_id=manifest.run_id,
        artifact=finished,
        summary=f"Provider call {call_number} finished with status {status}.",
    )
    return finished


def _sanitize_provider_provenance(raw: dict[str, object]) -> dict[str, object]:
    allowed = {
        "provider_base_url",
        "model",
        "reported_model",
        "created_at",
        "temperature",
        "system_prompt_sha256",
        "user_prompt_sha256",
        "usage",
    }
    clean: dict[str, object] = {}
    for key in allowed:
        value = raw.get(key)
        if key == "usage" and isinstance(value, dict):
            clean[key] = {
                str(name): count
                for name, count in value.items()
                if isinstance(name, str)
                and isinstance(count, (int, float))
                and not isinstance(count, bool)
            }
        elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
            clean[key] = value
    return clean


def _dispatch_provider(
    project: Path,
    run_dir: Path,
    manifest: CycleManifest,
    *,
    provider: object,
    context: ExternalContextSnapshot,
    stage: str,
    system_prompt: str,
    user_prompt: str,
    expected_run_identity: tuple[int, int],
) -> tuple[CycleManifest, int, object | None, str | None]:
    updated, call_number = _begin_provider_call(
        project,
        run_dir,
        manifest,
        provider=provider,
        context=context,
        stage=stage,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        expected_run_identity=expected_run_identity,
    )
    try:
        complete = getattr(provider, "complete")
        result = complete(
            system_prompt,
            user_prompt,
            external_api_allowed=True,
        )
        content = result.content
        provenance = result.provenance
        if not isinstance(content, str):
            raise ValueError("provider result content must be text")
        if len(content.encode("utf-8")) > MAX_ARTIFACT_BYTES:
            raise ValueError("provider response exceeds the 1 MiB limit")
        if not isinstance(provenance, dict):
            raise ValueError("provider provenance must be an object")
    except Exception as exc:
        # If the run was replaced while the network call was in flight, fail closed.
        # In particular, do not write even an error provenance record into the new path.
        _assert_directory_identity(
            run_dir,
            expected_run_identity,
            context="cycle run during provider dispatch",
        )
        _finish_provider_call(
            project,
            run_dir,
            updated,
            call_number=call_number,
            stage=stage,
            status="provider_error",
            response_content=None,
            provider_provenance=None,
            error_type=type(exc).__name__,
            expected_run_identity=expected_run_identity,
        )
        return updated, call_number, None, f"provider call failed: {type(exc).__name__}"
    _assert_directory_identity(
        run_dir,
        expected_run_identity,
        context="cycle run during provider dispatch",
    )
    return updated, call_number, result, None


def _mark_provider_output(
    project: Path,
    run_dir: Path,
    manifest: CycleManifest,
    *,
    call_number: int,
    stage: str,
    result: object,
    status: str,
    error_type: str = "",
    expected_run_identity: tuple[int, int],
) -> None:
    _finish_provider_call(
        project,
        run_dir,
        manifest,
        call_number=call_number,
        stage=stage,
        status=status,
        response_content=getattr(result, "content"),
        provider_provenance=getattr(result, "provenance"),
        error_type=error_type,
        expected_run_identity=expected_run_identity,
    )


def _temporary_response(run_dir: Path, content: str, *, suffix: str) -> Path:
    path = run_dir / f".provider-response-{secrets.token_hex(8)}{suffix}"
    atomic_write_text(
        path,
        content,
        expected_parent_identity=_directory_identity(run_dir),
    )
    return path


def _commit_provider_candidates(
    run_dir: Path,
    target: Path,
    content: str,
    *,
    manifest: CycleManifest,
    source_ids: set[str],
    call_number: int,
    provider_provenance: dict[str, object],
    reserved_idea_ids: set[str],
    expected_run_identity: tuple[int, int],
) -> None:
    temporary = _temporary_response(run_dir, content, suffix=".json")
    try:
        candidates = _load_candidates(
            temporary, manifest=manifest, source_ids=source_ids
        )
        collisions = sorted(
            {idea.idea_id for idea in candidates.ideas} & reserved_idea_ids
        )
        if collisions:
            raise ValueError(
                "Idea ID already belongs to another run: "
                + ", ".join(collisions)
            )
        clean_provenance = _sanitize_provider_provenance(provider_provenance)
        generated = IdeaArchive(
            1,
            candidates.project_slug,
            tuple(
                replace(
                    idea,
                    provenance={
                        "provider_call": call_number,
                        "response_sha256": _sha256_text(content),
                        **clean_provenance,
                    },
                )
                for idea in candidates.ideas
            ),
        )
        save_idea_archive(
            target,
            generated,
            overwrite=False,
            expected_parent_identity=expected_run_identity,
        )
        _load_candidates(target, manifest=manifest, source_ids=source_ids)
    finally:
        temporary.unlink(missing_ok=True)


def _commit_provider_review(
    run_dir: Path,
    target: Path,
    content: str,
    *,
    role: str,
    candidate_ids: set[str],
    expected_reviews_identity: tuple[int, int],
) -> None:
    temporary = _temporary_response(run_dir, content, suffix=".json")
    try:
        load_independent_review(
            temporary,
            expected_role=role,
            expected_idea_ids=candidate_ids,
            expected_run_id=run_dir.name,
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_create_text(
            target,
            content.rstrip() + "\n",
            expected_parent_identity=expected_reviews_identity,
        )
    finally:
        temporary.unlink(missing_ok=True)


def _commit_provider_meta_review(
    run_dir: Path,
    target: Path,
    content: str,
    *,
    candidate_ids: set[str],
    run_id: str,
    expected_run_identity: tuple[int, int],
) -> None:
    temporary = _temporary_response(run_dir, content, suffix=".json")
    try:
        load_meta_review(
            temporary,
            expected_idea_ids=candidate_ids,
            expected_run_id=run_id,
        )
        atomic_create_text(
            target,
            content.rstrip() + "\n",
            expected_parent_identity=expected_run_identity,
        )
    finally:
        temporary.unlink(missing_ok=True)


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


def _active_run(
    project: Path,
    *,
    expected_project_identity: tuple[int, int] | None = None,
) -> tuple[Path, CycleManifest]:
    project_identity = expected_project_identity or _directory_identity(project)
    _assert_directory_identity(project, project_identity, context="project")
    cycles = _direct_directory(project, "cycles", create=False)
    cycles_identity = _directory_identity(cycles)
    pointer = cycles / "active-run.txt"
    try:
        run_id = read_stable_direct_text(
            pointer,
            expected_parent=cycles,
            expected_parent_identity=cycles_identity,
            max_bytes=256,
        ).strip()
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("cycle active-run pointer is missing or unreadable") from exc
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("cycle active-run pointer is invalid")
    _assert_directory_identity(project, project_identity, context="project")
    _assert_directory_identity(cycles, cycles_identity, context="cycles")
    run_dir = _direct_directory(cycles, run_id, create=False)
    run_identity = _directory_identity(run_dir)
    manifest = load_cycle_manifest(
        run_dir / "manifest.yaml",
        expected_parent_identity=run_identity,
    )
    if manifest.project_slug != project.name:
        raise ValueError("active cycle belongs to a different project")
    _assert_directory_identity(cycles, cycles_identity, context="cycles")
    _assert_directory_identity(project, project_identity, context="project")
    return run_dir, manifest


def load_active_cycle(
    workspace: Path,
    slug: str,
    *,
    expected_project_identity: tuple[int, int] | None = None,
) -> tuple[Path, CycleManifest]:
    project = resolve_project_path(workspace, slug, require_exists=True)
    return _active_run(
        project,
        expected_project_identity=expected_project_identity,
    )


def approve_active_cycle_idea(
    workspace: Path,
    slug: str,
    idea_id: str,
    *,
    reason: str,
) -> IdeaRecord:
    project = resolve_project_path(workspace, slug, require_exists=True)
    project_manifest = load_project_manifest(project)
    if not (project / "cycles").is_dir():
        raise ValueError("no active reviewed run exists for Idea approval")
    run_dir, manifest = _active_run(project)
    if manifest.state != "awaiting_human_decision":
        raise ValueError(
            "active run is not awaiting a human Idea decision"
        )
    candidates_path = run_dir / "candidates.yaml"
    reviews_dir = run_dir / "reviews"
    meta_path = run_dir / "meta-review.json"
    if (
        not candidates_path.is_file()
        or _sha256_file(candidates_path) != manifest.candidate_sha256
    ):
        raise ValueError("active run candidate snapshot is missing or changed")
    if _reviews_digest(reviews_dir) != manifest.reviews_sha256:
        raise ValueError("active run independent reviews are missing or changed")
    if not meta_path.is_file() or _sha256_file(meta_path) != manifest.meta_review_sha256:
        raise ValueError("active run meta-review is missing or changed")
    source_ids = set(project_manifest.source_ids)
    candidates = _load_candidates(
        candidates_path, manifest=manifest, source_ids=source_ids
    )
    candidate_ids = {idea.idea_id for idea in candidates.ideas}
    load_review_bundle(
        reviews_dir,
        expected_idea_ids=candidate_ids,
        expected_run_id=manifest.run_id,
    )
    meta = load_meta_review(
        meta_path,
        expected_idea_ids=candidate_ids,
        expected_run_id=manifest.run_id,
    )
    if idea_id not in meta.shortlist_ids:
        raise ValueError(f"Idea is not shortlisted by the active meta-review: {idea_id}")
    archive_path = project / "ideas" / "archive.yaml"
    archive = load_idea_archive(archive_path, allowed_source_ids=source_ids)
    frozen_by_id = {idea.idea_id: idea for idea in candidates.ideas}
    selected_record = next(
        (
            idea
            for idea in archive.ideas
            if idea.idea_id == idea_id and idea.generated_by_run == manifest.run_id
        ),
        None,
    )
    if selected_record is None:
        raise ValueError(f"active run Idea is missing from the archive: {idea_id}")
    if idea_content_hash(selected_record) != idea_content_hash(frozen_by_id[idea_id]):
        raise ValueError("active run Idea no longer matches its frozen reviewed candidate")
    approved = approve_idea(archive, idea_id, reason=reason)
    snapshot = archive_path.read_bytes()
    archive_identity = _directory_identity(archive_path.parent)
    manifest_path = run_dir / "manifest.yaml"
    manifest_snapshot = manifest_path.read_bytes()
    run_identity = _directory_identity(run_dir)
    save_idea_archive(archive_path, approved)
    approved_record = next(idea for idea in approved.ideas if idea.idea_id == idea_id)
    try:
        completed = replace(
            manifest,
            state="completed",
            updated_at=_utc_now(),
            last_error="",
        )
        save_cycle_manifest(
            manifest_path,
            completed,
            expected_parent_identity=run_identity,
        )
        _record(
            project,
            event_type="idea_approved",
            run_id=manifest.run_id,
            artifact=archive_path,
            summary=(
                f"Researcher approved {idea_id} and completed the supervised run: "
                f"{reason.strip()}"
            ),
        )
    except BaseException:
        atomic_write_bytes(
            archive_path,
            snapshot,
            expected_parent_identity=archive_identity,
        )
        atomic_write_bytes(
            manifest_path,
            manifest_snapshot,
            expected_parent_identity=run_identity,
        )
        raise
    return approved_record


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
    snapshot = manifest_path.read_bytes()
    manifest_identity = _directory_identity(run_dir)
    save_cycle_manifest(
        manifest_path,
        updated,
        expected_parent_identity=manifest_identity,
    )
    try:
        _record(
            project,
            event_type="state_transition",
            run_id=manifest.run_id,
            artifact=manifest_path,
            summary=f"Advanced research cycle from {manifest.state} to {new_state}.",
        )
    except BaseException:
        atomic_write_bytes(
            manifest_path,
            snapshot,
            expected_parent_identity=manifest_identity,
        )
        raise
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


def validate_cycle_artifacts(
    run_dir: Path,
    manifest: CycleManifest,
    *,
    source_ids: set[str],
    archive_path: Path,
) -> tuple[str, ...]:
    """Validate state-bound cycle artifacts without changing the run."""
    issues: list[str] = []
    candidate_ids: set[str] = set()
    candidates_path = run_dir / "candidates.yaml"
    if manifest.candidate_sha256:
        try:
            if _sha256_file(candidates_path) != manifest.candidate_sha256:
                raise ValueError("candidate hash does not match manifest")
            candidates = _load_candidates(
                candidates_path, manifest=manifest, source_ids=source_ids
            )
            if manifest.state in {
                "independent_review",
                "meta_review",
                "awaiting_human_decision",
                "completed",
            } and any(not _novelty_complete(idea) for idea in candidates.ideas):
                raise ValueError(
                    "novelty gate requires checked candidates with queries, "
                    "nearest sources, and documented differences"
                )
            candidate_ids = {idea.idea_id for idea in candidates.ideas}
        except (OSError, UnicodeError, ValueError) as exc:
            issues.append(f"candidates: {exc}")
    if manifest.reviews_sha256:
        try:
            reviews_dir = run_dir / "reviews"
            if _reviews_digest(reviews_dir) != manifest.reviews_sha256:
                raise ValueError("review bundle hash does not match manifest")
            if candidate_ids:
                load_review_bundle(
                    reviews_dir,
                    expected_idea_ids=candidate_ids,
                    expected_run_id=manifest.run_id,
                )
        except (OSError, UnicodeError, ValueError) as exc:
            issues.append(f"reviews: {exc}")
    if manifest.meta_review_sha256:
        try:
            meta_path = run_dir / "meta-review.json"
            if _sha256_file(meta_path) != manifest.meta_review_sha256:
                raise ValueError("meta-review hash does not match manifest")
            if candidate_ids:
                load_meta_review(
                    meta_path,
                    expected_idea_ids=candidate_ids,
                    expected_run_id=manifest.run_id,
                )
        except (OSError, UnicodeError, ValueError) as exc:
            issues.append(f"meta-review: {exc}")
    if manifest.state == "completed":
        try:
            archive = load_idea_archive(
                archive_path, allowed_source_ids=source_ids
            )
            selected = [
                idea
                for idea in archive.ideas
                if idea.generated_by_run == manifest.run_id and idea.status == "selected"
            ]
            if len(selected) != 1:
                raise ValueError(
                    "completed run must have exactly one researcher-selected Idea"
                )
        except (OSError, UnicodeError, ValueError) as exc:
            issues.append(f"approval: {exc}")
    return tuple(issues)


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
    allow_external_api: bool = False,
) -> CycleAction:
    requested_max_ideas = _validate_bound(
        max_ideas, name="max_ideas", default=DEFAULT_MAX_IDEAS, upper=10
    )
    requested_max_calls = _validate_bound(
        max_calls, name="max_calls", default=DEFAULT_MAX_CALLS, upper=20
    )
    project = resolve_project_path(workspace, slug, require_exists=True)
    project_manifest = load_project_manifest(project)
    journal_path = project / "research-journal.jsonl"
    if journal_path.exists():
        journal_issues = validate_journal(journal_path, project_root=project)
        if journal_issues:
            raise ValueError(
                "research journal is corrupt; cycle resume is blocked: "
                + "; ".join(journal_issues)
            )
    elif (project / "cycles").exists():
        raise ValueError("research journal is missing; cycle resume is blocked")
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
    run_identity = _directory_identity(run_dir)

    candidates_path = run_dir / "candidates.yaml"
    reviews_dir = run_dir / "reviews"
    meta_path = run_dir / "meta-review.json"

    if manifest.state == "candidate_generation":
        if not candidates_path.is_file():
            if provider is None:
                return _action(
                    manifest,
                    next_action="create_candidates",
                    target=candidates_path,
                    reason="Create a strict local candidate artifact; no model call was made.",
                )
            if manifest.max_calls - manifest.calls_used < 1:
                return _action(
                    manifest,
                    state="budget_exhausted",
                    next_action="increase_budget_or_continue_locally",
                    target=run_dir / "work-packet.md",
                    reason="Candidate generation requires one remaining provider call.",
                )
            context = build_external_context(
                workspace,
                slug,
                run_dir=run_dir,
                allow_external_api=allow_external_api,
            )
            system_prompt = (
                "Generate a strict JSON candidate archive for this research cycle. "
                "Use schema_version 1, project_slug, and no more than max_ideas Ideas. "
                "Every Idea must remain draft, cite only listed source IDs, contain a "
                "falsifiable failure criterion, and leave novelty pending. Never select "
                "an Idea and never propose executing an experiment. Return JSON only."
            )
            user_prompt = (
                context.content
                + f"\nRun ID: {manifest.run_id}\nMaximum Ideas: {manifest.max_ideas}\n"
            )
            manifest, call_number, result, error = _dispatch_provider(
                project,
                run_dir,
                manifest,
                provider=provider,
                context=context,
                stage="candidate_generation",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                expected_run_identity=run_identity,
            )
            if error is not None or result is None:
                return _blocked(
                    manifest,
                    next_action="retry_or_continue_candidates_locally",
                    target=candidates_path,
                    reason=error or "provider call failed",
                )
            try:
                _commit_provider_candidates(
                    run_dir,
                    candidates_path,
                    result.content,
                    manifest=manifest,
                    source_ids=source_ids,
                    call_number=call_number,
                    provider_provenance=result.provenance,
                    reserved_idea_ids={
                        idea.idea_id
                        for idea in load_idea_archive(
                            archive_path, allowed_source_ids=source_ids
                        ).ideas
                    },
                    expected_run_identity=run_identity,
                )
            except (OSError, UnicodeError, ValueError) as exc:
                _mark_provider_output(
                    project,
                    run_dir,
                    manifest,
                    call_number=call_number,
                    stage="candidate_generation",
                    result=result,
                    status="invalid_output",
                    error_type=type(exc).__name__,
                    expected_run_identity=run_identity,
                )
                return _blocked(
                    manifest,
                    next_action="retry_or_continue_candidates_locally",
                    target=candidates_path,
                    reason=f"provider candidate output was invalid: {exc}",
                )
            _mark_provider_output(
                project,
                run_dir,
                manifest,
                call_number=call_number,
                stage="candidate_generation",
                result=result,
                status="committed",
                expected_run_identity=run_identity,
            )
        archive_snapshot = archive_path.read_bytes()
        archive_identity = _directory_identity(archive_path.parent)
        try:
            candidates = _load_candidates(
                candidates_path, manifest=manifest, source_ids=source_ids
            )
            _assert_directory_identity(
                run_dir, run_identity, context="cycle run"
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
        try:
            manifest = _transition(
                project,
                run_dir,
                manifest,
                "novelty_check",
                candidate_sha256=_sha256_file(candidates_path),
            )
        except BaseException:
            atomic_write_bytes(
                archive_path,
                archive_snapshot,
                expected_parent_identity=archive_identity,
            )
            raise

    if manifest.state == "novelty_check":
        try:
            candidates = _load_candidates(
                candidates_path, manifest=manifest, source_ids=source_ids
            )
            _assert_directory_identity(
                run_dir, run_identity, context="cycle run"
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
        archive_snapshot = archive_path.read_bytes()
        archive_identity = _directory_identity(archive_path.parent)
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
        try:
            manifest = _transition(
                project,
                run_dir,
                manifest,
                "independent_review",
                candidate_sha256=_sha256_file(candidates_path),
            )
        except BaseException:
            atomic_write_bytes(
                archive_path,
                archive_snapshot,
                expected_parent_identity=archive_identity,
            )
            raise

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
            _assert_directory_identity(
                run_dir, run_identity, context="cycle run"
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
        missing_roles = [
            role
            for role, path in zip(
                ("novelty", "methods", "medical-safety"), review_paths
            )
            if not path.is_file()
        ]
        for role, path in zip(
            ("novelty", "methods", "medical-safety"), review_paths
        ):
            if not path.is_file():
                continue
            try:
                load_independent_review(
                    path,
                    expected_role=role,
                    expected_idea_ids=candidate_ids,
                    expected_run_id=manifest.run_id,
                )
            except ValueError as exc:
                return _blocked(
                    manifest,
                    next_action="repair_independent_reviews",
                    target=path,
                    reason=str(exc),
                )
        if missing_roles and provider is None:
            return _action(
                manifest,
                next_action="create_independent_reviews",
                target=reviews_dir,
                reason="Create all three role-separated review files.",
            )
        if missing_roles:
            remaining = manifest.max_calls - manifest.calls_used
            if remaining < len(missing_roles):
                return _action(
                    manifest,
                    state="budget_exhausted",
                    next_action="increase_budget_or_continue_locally",
                    target=reviews_dir,
                    reason=(
                        f"The independent review stage needs {len(missing_roles)} "
                        f"calls but only {remaining} remain; no partial dispatch occurred."
                    ),
                )
            context = build_external_context(
                workspace,
                slug,
                run_dir=run_dir,
                allow_external_api=allow_external_api,
            )
            candidate_text = candidates_path.read_text(encoding="utf-8")
            reviews_dir.mkdir(exist_ok=True)
            for role in missing_roles:
                reviews_identity = _directory_identity(reviews_dir)
                system_prompt = (
                    f"Act only as the independent {role} reviewer. Return the strict "
                    "schema-version-1 JSON review for every candidate. Do not read or "
                    "imitate another reviewer, do not select an Idea, and do not execute "
                    "experiments. Recommendations are advance, revise, or reject."
                )
                user_prompt = context.content + "\n# Frozen candidates\n" + candidate_text
                manifest, call_number, result, error = _dispatch_provider(
                    project,
                    run_dir,
                    manifest,
                    provider=provider,
                    context=context,
                    stage=f"independent_review:{role}",
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    expected_run_identity=run_identity,
                )
                target = reviews_dir / f"{role}.json"
                if error is not None or result is None:
                    return _blocked(
                        manifest,
                        next_action="retry_missing_independent_review",
                        target=target,
                        reason=error or "provider call failed",
                    )
                try:
                    _commit_provider_review(
                        run_dir,
                        target,
                        result.content,
                        role=role,
                        candidate_ids=candidate_ids,
                        expected_reviews_identity=reviews_identity,
                    )
                except (OSError, UnicodeError, ValueError) as exc:
                    _mark_provider_output(
                        project,
                        run_dir,
                        manifest,
                        call_number=call_number,
                        stage=f"independent_review:{role}",
                        result=result,
                        status="invalid_output",
                        error_type=type(exc).__name__,
                        expected_run_identity=run_identity,
                    )
                    return _blocked(
                        manifest,
                        next_action="retry_missing_independent_review",
                        target=target,
                        reason=f"provider review output was invalid: {exc}",
                    )
                _mark_provider_output(
                    project,
                    run_dir,
                    manifest,
                    call_number=call_number,
                    stage=f"independent_review:{role}",
                    result=result,
                    status="committed",
                    expected_run_identity=run_identity,
                )
        try:
            load_review_bundle(
                reviews_dir,
                expected_idea_ids=candidate_ids,
                expected_run_id=manifest.run_id,
            )
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
            if provider is None:
                return _action(
                    manifest,
                    next_action="create_meta_review",
                    target=meta_path,
                    reason="Reconcile consensus and conflicts without selecting an Idea.",
                )
            if manifest.max_calls - manifest.calls_used < 1:
                return _action(
                    manifest,
                    state="budget_exhausted",
                    next_action="increase_budget_or_continue_locally",
                    target=meta_path,
                    reason="Meta-review requires one remaining provider call.",
                )
            context = build_external_context(
                workspace,
                slug,
                run_dir=run_dir,
                allow_external_api=allow_external_api,
            )
            review_text = "\n".join(
                (reviews_dir / f"{role}.json").read_text(encoding="utf-8")
                for role in ("novelty", "methods", "medical-safety")
            )
            system_prompt = (
                "Create a strict schema-version-1 JSON meta-review from the three "
                "independent reports. Preserve disagreements and blocking issues. You "
                "may shortlist but must never select an Idea or execute experiments."
            )
            user_prompt = context.content + "\n# Independent reviews\n" + review_text
            manifest, call_number, result, error = _dispatch_provider(
                project,
                run_dir,
                manifest,
                provider=provider,
                context=context,
                stage="meta_review",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                expected_run_identity=run_identity,
            )
            if error is not None or result is None:
                return _blocked(
                    manifest,
                    next_action="retry_or_continue_meta_review_locally",
                    target=meta_path,
                    reason=error or "provider call failed",
                )
            try:
                _commit_provider_meta_review(
                    run_dir,
                    meta_path,
                    result.content,
                    candidate_ids=candidate_ids,
                    run_id=manifest.run_id,
                    expected_run_identity=run_identity,
                )
            except (OSError, UnicodeError, ValueError) as exc:
                _mark_provider_output(
                    project,
                    run_dir,
                    manifest,
                    call_number=call_number,
                    stage="meta_review",
                    result=result,
                    status="invalid_output",
                    error_type=type(exc).__name__,
                    expected_run_identity=run_identity,
                )
                return _blocked(
                    manifest,
                    next_action="retry_or_continue_meta_review_locally",
                    target=meta_path,
                    reason=f"provider meta-review output was invalid: {exc}",
                )
            _mark_provider_output(
                project,
                run_dir,
                manifest,
                call_number=call_number,
                stage="meta_review",
                result=result,
                status="committed",
                expected_run_identity=run_identity,
            )
        archive_snapshot = archive_path.read_bytes()
        archive_identity = _directory_identity(archive_path.parent)
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
        try:
            manifest = _transition(
                project,
                run_dir,
                manifest,
                "awaiting_human_decision",
                meta_review_sha256=_sha256_file(meta_path),
            )
        except BaseException:
            atomic_write_bytes(
                archive_path,
                archive_snapshot,
                expected_parent_identity=archive_identity,
            )
            raise

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
