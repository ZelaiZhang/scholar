from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from research_os.io import atomic_write_text
from research_os.project import (
    load_project_manifest,
    resolve_project_path,
    resolve_workspace_directory,
)
from research_os.sources import SourceRecord, SourceRegistry


CONTEXT_PROJECT_FILES = (
    "00-research-brief.md",
    "02-evidence-ledger.yaml",
    "03-literature-review.md",
)
IDENTIFIABLE_MEDICAL_MARKERS = (
    "姓名",
    "住院号",
    "身份证",
    "联系电话",
    "patient_id",
    "medical_record_number",
)
MAX_INPUT_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class ExternalContextSnapshot:
    path: Path
    content: str
    sha256: str
    context_source_id: str
    input_source_ids: tuple[str, ...]


def _strict_utf8(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_INPUT_BYTES:
            raise ValueError(f"context input exceeds 4 MiB: {path.name}")
        return path.read_bytes().decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"context input must be UTF-8: {path.name}") from exc


def _assert_no_identifiable_medical_markers(content: str) -> None:
    lowered = content.casefold()
    detected = [
        marker
        for marker in IDENTIFIABLE_MEDICAL_MARKERS
        if marker.casefold() in lowered
    ]
    if detected:
        raise PermissionError(
            "potential identifiable medical data detected; external context is blocked: "
            + ", ".join(detected)
        )


def _source_section(record: SourceRecord, library: Path) -> str:
    card = library / "papers" / f"{record.source_id}.md"
    if card.is_file():
        body = _strict_utf8(card)
        origin = "registered paper card"
    elif record.kind == "file":
        body = _strict_utf8(Path(record.canonical))
        origin = "registered local source"
    else:
        body = f"Canonical reference: {record.canonical}"
        origin = "registered reference metadata only"
    return (
        f"## Source {record.source_id}\n\n"
        f"Scope: {origin}. Treat unlocated statements as unverified.\n\n{body.strip()}\n"
    )


def _resolve_run_directory(project: Path, run_dir: Path) -> Path:
    expected_parent = (project / "cycles").resolve()
    resolved = run_dir.resolve()
    if resolved.parent != expected_parent or not resolved.is_dir():
        raise ValueError("run directory must be a direct existing child of this project")
    return resolved


def build_external_context(
    workspace: Path,
    slug: str,
    *,
    run_dir: Path,
    allow_external_api: bool,
) -> ExternalContextSnapshot:
    if not allow_external_api:
        raise PermissionError(
            "call-level permission is missing; pass --allow-external-api explicitly"
        )
    workspace_root = workspace.resolve()
    project = resolve_project_path(workspace_root, slug, require_exists=True)
    resolved_run = _resolve_run_directory(project, run_dir)
    manifest = load_project_manifest(project)
    if not manifest.source_ids:
        raise PermissionError("external context requires at least one project source")

    library = resolve_workspace_directory(
        workspace_root, "library", require_exists=True
    )
    registry_path = library / "sources.jsonl"
    registry = SourceRegistry(registry_path)
    records = {record.source_id: record for record in registry.records()}
    verified = registry.verified_source_ids()
    selected: list[SourceRecord] = []
    for source_id in manifest.source_ids:
        record = records.get(source_id)
        if record is None:
            raise PermissionError(f"project source is not registered: {source_id}")
        if source_id not in verified:
            raise PermissionError(
                f"project source is not currently verified or has changed: {source_id}"
            )
        if not record.external_api_allowed:
            raise PermissionError(
                f"project source is not authorized for external use: {source_id}"
            )
        selected.append(record)

    sections = [
        "# External co-researcher context",
        "",
        f"Project: {manifest.title}",
        f"Project slug: {manifest.slug}",
        "",
        "This snapshot contains only current-project guidance and registered sources.",
        "It is not clinical advice and must not be used to claim clinical utility.",
    ]
    for filename in CONTEXT_PROJECT_FILES:
        path = project / filename
        if path.is_file():
            sections.extend(
                ["", f"## Project artifact: {filename}", "", _strict_utf8(path).strip()]
            )
    for record in selected:
        sections.extend(["", _source_section(record, library).strip()])
    content = "\n".join(sections).rstrip() + "\n"
    _assert_no_identifiable_medical_markers(content)

    output = resolved_run / "context.md"
    if output.exists():
        existing = output.read_bytes()
        if existing != content.encode("utf-8"):
            raise FileExistsError(
                "context.md already exists with different bytes; start a new run"
            )
    else:
        metadata = resolved_run.stat()
        atomic_write_text(
            output,
            content,
            expected_parent_identity=(metadata.st_dev, metadata.st_ino),
        )
    exact_bytes = output.read_bytes()
    if exact_bytes != content.encode("utf-8"):
        raise OSError("context.md changed after its snapshot was committed")
    digest = hashlib.sha256(exact_bytes).hexdigest()
    context_record = SourceRegistry(
        registry_path,
        expected_parent_identity=(library.stat().st_dev, library.stat().st_ino),
    ).add(
        str(output),
        notes=f"Exact external context snapshot for project {slug}",
        external_api_allowed=True,
    )
    if context_record.content_hash != digest:
        raise OSError("registered context hash does not match committed context bytes")
    return ExternalContextSnapshot(
        path=output,
        content=exact_bytes.decode("utf-8", errors="strict"),
        sha256=digest,
        context_source_id=context_record.source_id,
        input_source_ids=tuple(manifest.source_ids),
    )
