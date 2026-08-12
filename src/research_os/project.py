from __future__ import annotations

import re
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

import yaml

from research_os.io import (
    assert_directory_identity,
    atomic_write_text,
    read_stable_direct_text,
)
from research_os.sources import SOURCE_ID_PATTERN


class ProjectExistsError(FileExistsError):
    """Raised when project creation would overwrite an existing project."""


class InvalidSlugError(ValueError):
    """Raised when a project slug is not safe and portable."""


PROJECT_FILES = {
    "start-here.md": "START-HERE.md",
    "research-brief.md": "00-research-brief.md",
    "search-log.md": "01-search-log.md",
    "evidence-ledger.yaml": "02-evidence-ledger.yaml",
    "literature-review.md": "03-literature-review.md",
    "idea-candidates.md": "04-idea-candidates.md",
    "experiment-design.md": "05-experiment-design.md",
    "result-analysis.md": "06-result-analysis.md",
}
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class ProjectManifest:
    schema_version: int
    title: str
    slug: str
    created_at: str
    source_ids: tuple[str, ...]
    persisted: bool = True


def validate_slug(slug: str) -> None:
    if not SLUG_PATTERN.fullmatch(slug):
        raise InvalidSlugError("slug 只能包含小写字母、数字和单个连字符")


def resolve_project_path(
    workspace: Path, slug: str, *, require_exists: bool = False
) -> Path:
    """Resolve a direct project child without following links outside workspace."""
    validate_slug(slug)
    projects_root = resolve_workspace_directory(workspace, "projects")
    candidate = projects_root / slug
    if _is_link_or_reparse_point(candidate):
        raise ValueError(f"课题路径越出工作区（目录不能是符号链接或目录联接）: {candidate}")
    project_path = candidate.resolve()
    if project_path.parent != projects_root:
        raise ValueError(f"课题路径越出工作区: {project_path}")
    if require_exists and not project_path.is_dir():
        raise FileNotFoundError(f"课题不存在: {project_path}")
    return project_path


def resolve_workspace_directory(
    workspace: Path, name: str, *, require_exists: bool = False
) -> Path:
    """Resolve one internal directory without following it outside workspace."""
    if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
        raise ValueError(f"无效工作区目录名: {name}")
    workspace_root = workspace.resolve()
    candidate = workspace_root / name
    if _is_link_or_reparse_point(candidate):
        raise ValueError(f"{name} 不能是符号链接或目录联接: {candidate}")
    directory = candidate.resolve()
    if directory.parent != workspace_root:
        raise ValueError(f"{name} 路径越出工作区: {directory}")
    if require_exists and not directory.is_dir():
        raise FileNotFoundError(f"工作区目录不存在: {directory}")
    return directory


def _is_link_or_reparse_point(path: Path) -> bool:
    """Detect symlinks and Windows junctions without following the target."""
    try:
        metadata = path.lstat()
    except OSError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(metadata, "st_file_attributes", 0)
    return path.is_symlink() or bool(reparse_flag and file_attributes & reparse_flag)


def template_content(name: str, template_root: Path | None) -> str:
    if template_root is not None:
        return (template_root / name).read_text(encoding="utf-8")
    return resources.files("research_os.templates").joinpath(name).read_text(
        encoding="utf-8"
    )


def _manifest_path(project_path: Path) -> Path:
    return project_path / "project.yaml"


def write_project_manifest(
    project_path: Path,
    manifest: ProjectManifest,
    *,
    expected_directory_identity: tuple[int, int] | None = None,
) -> None:
    payload = {
        "schema_version": manifest.schema_version,
        "title": manifest.title,
        "slug": manifest.slug,
        "created_at": manifest.created_at,
        "source_ids": list(manifest.source_ids),
    }
    atomic_write_text(
        _manifest_path(project_path),
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        expected_parent_identity=expected_directory_identity,
    )


def load_project_manifest(
    project_path: Path,
    *,
    allow_legacy: bool = False,
    expected_directory_identity: tuple[int, int] | None = None,
) -> ProjectManifest:
    project_path = project_path.resolve()
    if expected_directory_identity is not None:
        assert_directory_identity(
            project_path,
            expected_directory_identity,
            context="project",
        )
    path = _manifest_path(project_path)
    if not path.exists():
        if not allow_legacy:
            raise FileNotFoundError(path)
        brief = project_path / "00-research-brief.md"
        if not brief.is_file():
            raise FileNotFoundError(brief)
        brief_text = read_stable_direct_text(
            brief,
            expected_parent=project_path,
            expected_parent_identity=expected_directory_identity,
        )
        first_heading = next(
            (
                line[2:].strip()
                for line in brief_text.splitlines()
                if line.startswith("# ") and line[2:].strip()
            ),
            project_path.name,
        )
        return ProjectManifest(
            1, first_heading, project_path.name, "", (), persisted=False
        )

    try:
        raw = yaml.safe_load(
            read_stable_direct_text(
                path,
                expected_parent=project_path,
                expected_parent_identity=expected_directory_identity,
            )
        )
    except yaml.YAMLError as exc:
        raise ValueError(f"课题元数据 YAML 无法解析: {path}: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError(f"课题元数据格式无效: {path}")
    title = str(raw.get("title", "")).strip()
    slug = str(raw.get("slug", "")).strip()
    source_ids = raw.get("source_ids", [])
    if (
        not title
        or not SLUG_PATTERN.fullmatch(slug)
        or not isinstance(source_ids, list)
    ):
        raise ValueError(f"课题元数据字段无效: {path}")
    clean_ids = tuple(str(item).strip() for item in source_ids)
    if any(not SOURCE_ID_PATTERN.fullmatch(item) for item in clean_ids):
        raise ValueError(f"课题 source_ids 无效: {path}")
    if len(clean_ids) != len(set(clean_ids)):
        raise ValueError(f"课题 source_ids 包含重复项: {path}")
    return ProjectManifest(
        schema_version=1,
        title=title,
        slug=slug,
        created_at=str(raw.get("created_at", "")),
        source_ids=clean_ids,
    )


def link_project_sources(
    workspace: Path,
    slug: str,
    source_ids: list[str],
    expected_directory_identity: tuple[int, int] | None = None,
) -> None:
    if any(
        not isinstance(item, str) or not SOURCE_ID_PATTERN.fullmatch(item)
        for item in source_ids
    ):
        raise ValueError("source_id 必须是安全的小写字母数字和单连字符")
    project_path = resolve_project_path(workspace, slug, require_exists=True)
    if expected_directory_identity is not None:
        metadata = project_path.stat()
        if (metadata.st_dev, metadata.st_ino) != expected_directory_identity:
            raise OSError(f"课题目录在关联提交前被替换: {project_path}")
    manifest = load_project_manifest(project_path, allow_legacy=True)
    ordered = list(manifest.source_ids)
    for source_id in source_ids:
        if source_id not in ordered:
            ordered.append(source_id)
    write_project_manifest(
        project_path,
        ProjectManifest(
            schema_version=manifest.schema_version,
            title=manifest.title,
            slug=manifest.slug,
            created_at=manifest.created_at
            or datetime.now(timezone.utc).isoformat(),
            source_ids=tuple(ordered),
        ),
        expected_directory_identity=expected_directory_identity,
    )


def create_project(
    workspace: Path,
    title: str,
    slug: str,
    template_root: Path | None = None,
) -> Path:
    validate_slug(slug)
    if not title.strip():
        raise ValueError("课题标题不能为空")

    destination = resolve_project_path(workspace, slug)
    if destination.exists():
        raise ProjectExistsError(f"课题已存在: {destination}")

    destination.mkdir(parents=True)
    try:
        for source_name, target_name in PROJECT_FILES.items():
            content = template_content(source_name, template_root)
            atomic_write_text(
                destination / target_name,
                content.replace("{{PROJECT_TITLE}}", title.strip()).replace(
                    "{{PROJECT_SLUG}}", slug
                ),
            )
        write_project_manifest(
            destination,
            ProjectManifest(
                schema_version=1,
                title=title.strip(),
                slug=slug,
                created_at=datetime.now(timezone.utc).isoformat(),
                source_ids=(),
            ),
        )
        for name in ("writing", "reviews", "artifacts"):
            folder = destination / name
            folder.mkdir()
            (folder / ".gitkeep").touch()
    except BaseException:
        for child in sorted(destination.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            else:
                child.rmdir()
        destination.rmdir()
        raise
    return destination
