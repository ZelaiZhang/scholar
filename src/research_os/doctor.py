from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from research_os.project import (
    load_project_manifest,
    resolve_project_path,
    resolve_workspace_directory,
)
from research_os.sources import SourceRegistry


EXPECTED_SKILLS = (
    "research-project-init",
    "paper-intake",
    "paper-deep-read",
    "literature-synthesis",
    "idea-review",
    "experiment-advisor",
    "result-interpreter",
    "manuscript-assistant",
    "mock-reviewer",
    "research-weekly-review",
)
CORE_PROJECT_FILES = (
    "00-research-brief.md",
    "01-search-log.md",
    "02-evidence-ledger.yaml",
    "03-literature-review.md",
    "04-idea-candidates.md",
    "05-experiment-design.md",
    "06-result-analysis.md",
)


@dataclass(frozen=True)
class DiagnosticItem:
    level: str
    name: str
    message: str
    fix: str = ""


@dataclass(frozen=True)
class DoctorReport:
    items: tuple[DiagnosticItem, ...]

    @property
    def exit_code(self) -> int:
        return 1 if any(item.level == "fail" for item in self.items) else 0


def _check_projects(
    workspace: Path, verified_source_ids: set[str] | None = None
) -> DiagnosticItem:
    try:
        projects_root = resolve_workspace_directory(
            workspace, "projects", require_exists=True
        )
    except (OSError, ValueError) as exc:
        return DiagnosticItem(
            "fail",
            "projects",
            f"projects 目录不可用: {exc}",
            "恢复工作区内的真实 projects 目录，不要使用指向外部的目录链接",
        )
    project_paths = sorted(path for path in projects_root.iterdir() if path.is_dir())
    problems: list[str] = []
    for project_path in project_paths:
        try:
            resolved_project = resolve_project_path(
                workspace, project_path.name, require_exists=True
            )
        except (OSError, ValueError) as exc:
            problems.append(f"{project_path.name} 路径不可用: {exc}")
            continue
        missing = [
            name for name in CORE_PROJECT_FILES if not (project_path / name).is_file()
        ]
        if missing:
            problems.append(f"{project_path.name} 缺少 {', '.join(missing)}")
            continue
        try:
            manifest = load_project_manifest(resolved_project, allow_legacy=True)
            if verified_source_ids is not None:
                missing_ids = [
                    source_id
                    for source_id in manifest.source_ids
                    if source_id not in verified_source_ids
                ]
                if missing_ids:
                    problems.append(
                        f"{project_path.name} 关联了无效来源: {', '.join(missing_ids)}"
                    )
        except (OSError, ValueError) as exc:
            problems.append(f"{project_path.name} 无法读取: {exc}")
    if problems:
        return DiagnosticItem(
            "fail",
            "projects",
            "；".join(problems),
            "补齐课题核心文件或修复 project.yaml 后再运行 guide",
        )
    if not project_paths:
        return DiagnosticItem(
            "warn",
            "projects",
            "尚未创建课题",
            "运行 research-os new-project 创建第一个课题",
        )
    return DiagnosticItem("pass", "projects", f"{len(project_paths)} 个课题可读")


def run_doctor(
    workspace: Path,
    *,
    stdout_encoding: str | None = None,
    python_version: tuple[int, int, int] | None = None,
) -> DoctorReport:
    workspace = workspace.resolve()
    version = python_version or tuple(sys.version_info[:3])
    items: list[DiagnosticItem] = []

    if version >= (3, 11, 0):
        items.append(
            DiagnosticItem("pass", "python", f"Python {'.'.join(map(str, version))}")
        )
    else:
        items.append(
            DiagnosticItem(
                "fail",
                "python",
                f"Python {'.'.join(map(str, version))} 低于 3.11",
                "安装 Python 3.11 或更高版本并重建 .venv",
            )
        )

    invalid: list[str] = []
    try:
        config_root = resolve_workspace_directory(
            workspace, "config", require_exists=True
        )
        config_file = config_root / "research.yaml"
        if not config_file.is_file() or config_file.resolve().parent != config_root:
            invalid.append("config/research.yaml（应为工作区内的文件）")
    except (OSError, ValueError):
        invalid.append("config/research.yaml（应为工作区内的文件）")
    for name in ("projects", "library", "inbox"):
        try:
            resolve_workspace_directory(workspace, name, require_exists=True)
        except (OSError, ValueError):
            invalid.append(f"{name}（应为工作区内的目录）")
    if invalid:
        items.append(
            DiagnosticItem(
                "fail",
                "workspace",
                f"不是完整的 Research OS 工作区: {', '.join(invalid)}",
                "切换到包含 config、projects、library 和 inbox 的仓库根目录",
            )
        )
    else:
        items.append(DiagnosticItem("pass", "workspace", str(workspace)))

    missing_skills = [
        skill
        for skill in EXPECTED_SKILLS
        if not (workspace / ".agents" / "skills" / skill / "SKILL.md").is_file()
    ]
    if missing_skills:
        items.append(
            DiagnosticItem(
                "fail",
                "skills",
                f"缺少科研技能: {', '.join(missing_skills)}",
                "恢复仓库的 .agents/skills 目录并重启 Codex",
            )
        )
    else:
        items.append(DiagnosticItem("pass", "skills", "10 个科研技能可读"))

    verified_ids: set[str] | None = None
    try:
        library_root = resolve_workspace_directory(
            workspace, "library", require_exists=True
        )
    except (OSError, ValueError):
        items.append(
            DiagnosticItem(
                "fail",
                "sources",
                "library 不是工作区内的真实目录，未读取来源登记表",
                "恢复工作区内的 library 目录，不要使用指向外部的目录链接",
            )
        )
    else:
        registry = SourceRegistry(library_root / "sources.jsonl")
        try:
            records = registry.records()
            verified_ids = registry.verified_source_ids()
            stale = [
                record.source_id
                for record in records
                if record.kind == "file" and record.source_id not in verified_ids
            ]
            if stale:
                items.append(
                    DiagnosticItem(
                        "fail",
                        "sources",
                        f"{len(stale)} 个本地来源已移动、缺失或内容改变: {', '.join(stale)}",
                        "重新登记当前文件版本，并更新引用旧 source_id 的证据",
                    )
                )
            else:
                items.append(
                    DiagnosticItem("pass", "sources", f"{len(records)} 个来源记录可读")
                )
        except (OSError, ValueError) as exc:
            items.append(
                DiagnosticItem(
                    "fail",
                    "sources",
                    str(exc),
                    "修复 library/sources.jsonl；不要用空内容覆盖人工记录",
                )
            )

    items.append(_check_projects(workspace, verified_ids))

    normalized_encoding = (stdout_encoding or "").lower().replace("-", "")
    if normalized_encoding == "utf8":
        items.append(DiagnosticItem("pass", "console", "UTF-8 中文输出可用"))
    else:
        items.append(
            DiagnosticItem(
                "warn",
                "console",
                f"当前输出编码为 {stdout_encoding or '未知'}，中文可能乱码",
                '$env:PYTHONUTF8="1"；或直接使用 research-os 入口',
            )
        )
    return DoctorReport(tuple(items))


def render_doctor(report: DoctorReport) -> str:
    lines: list[str] = []
    for item in report.items:
        lines.append(f"[{item.level.upper()}] {item.name}: {item.message}")
        if item.fix:
            lines.append(f"  修复：{item.fix}")
    return "\n".join(lines) + "\n"
