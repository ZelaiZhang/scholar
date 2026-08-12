from __future__ import annotations

import re
from pathlib import Path

from research_os.io import atomic_write_text


class ProjectExistsError(FileExistsError):
    """Raised when project creation would overwrite an existing project."""


class InvalidSlugError(ValueError):
    """Raised when a project slug is not safe and portable."""


PROJECT_FILES = {
    "research-brief.md": "00-research-brief.md",
    "search-log.md": "01-search-log.md",
    "evidence-ledger.yaml": "02-evidence-ledger.yaml",
    "literature-review.md": "03-literature-review.md",
    "idea-candidates.md": "04-idea-candidates.md",
    "experiment-design.md": "05-experiment-design.md",
    "result-analysis.md": "06-result-analysis.md",
}
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_slug(slug: str) -> None:
    if not SLUG_PATTERN.fullmatch(slug):
        raise InvalidSlugError("slug 只能包含小写字母、数字和单个连字符")


def default_template_root() -> Path:
    return Path(__file__).resolve().parents[2] / "templates"


def create_project(
    workspace: Path,
    title: str,
    slug: str,
    template_root: Path | None = None,
) -> Path:
    validate_slug(slug)
    if not title.strip():
        raise ValueError("课题标题不能为空")

    destination = workspace.resolve() / "projects" / slug
    if destination.exists():
        raise ProjectExistsError(f"课题已存在: {destination}")

    templates = template_root or default_template_root()
    destination.mkdir(parents=True)
    try:
        for source_name, target_name in PROJECT_FILES.items():
            source = templates / source_name
            content = source.read_text(encoding="utf-8")
            atomic_write_text(
                destination / target_name,
                content.replace("{{PROJECT_TITLE}}", title.strip()),
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

