from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Sequence

from research_os.dashboard import ProjectDashboard, build_project_dashboard
from research_os.doctor import render_doctor, run_doctor
from research_os.cycle import advance_cycle, approve_active_cycle_idea
from research_os.evidence import load_ledger, render_validation_report, validate_ledger
from research_os.guidance import guide_project, render_guide
from research_os.io import atomic_write_bytes, atomic_write_text
from research_os.knowledge import (
    METHODS,
    PRIORITIES,
    STAGES,
    TOPICS,
    inspect_knowledge_base,
    load_knowledge_base,
)
from research_os.knowledge_gaps import GAP_KINDS, GapFilters, find_knowledge_gaps
from research_os.knowledge_recommend import recommend_for_project
from research_os.knowledge_search import SearchFilters, search_knowledge
from research_os.meeting_brief import (
    build_meeting_brief,
    meeting_brief_payload,
    render_meeting_brief,
)
from research_os.manuscript_plan import (
    build_manuscript_plan,
    manuscript_plan_payload,
    render_manuscript_plan,
)
from research_os.manuscript_audit import (
    build_manuscript_audit,
    manuscript_audit_payload,
    render_manuscript_audit,
)
from research_os.pdf import extract_pdf
from research_os.project import (
    create_project,
    link_project_sources,
    load_project_manifest,
    resolve_project_path,
    resolve_workspace_directory,
)
from research_os.provider import OpenAICompatibleProvider
from research_os.provider_config import load_provider
from research_os.sources import (
    SourceRegistry,
    load_authorized_external_texts,
    load_source_manifest,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-os",
        description="证据优先的端到端科研导航工作区",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser(
        "doctor", help="只读检查工作区、来源、技能和中文终端"
    )
    doctor_parser.add_argument("--workspace", type=Path, default=Path.cwd())

    guide_parser = subparsers.add_parser(
        "guide", help="显示课题状态并只推荐一个下一步"
    )
    guide_parser.add_argument("--project", help="课题 slug；只有一个课题时可省略")
    guide_parser.add_argument("--workspace", type=Path, default=Path.cwd())

    dashboard_parser = subparsers.add_parser(
        "dashboard", help="只读汇总课题状态、证据、风险和今日行动"
    )
    dashboard_parser.add_argument("--project", required=True, help="课题 slug")
    dashboard_parser.add_argument(
        "--as-of", default="", help="状态截止日期 YYYY-MM-DD"
    )
    dashboard_parser.add_argument(
        "--format", choices=("text", "json"), default="text"
    )
    dashboard_parser.add_argument("--workspace", type=Path, default=Path.cwd())

    meeting_parser = subparsers.add_parser(
        "meeting-brief",
        help="生成证据绑定的组会研究决策简报",
    )
    meeting_parser.add_argument("--project", required=True, help="课题 slug")
    meeting_parser.add_argument(
        "--as-of", default="", help="简报截止日期 YYYY-MM-DD"
    )
    meeting_parser.add_argument(
        "--format", choices=("markdown", "json"), default="markdown"
    )
    meeting_parser.add_argument("--workspace", type=Path, default=Path.cwd())

    manuscript_parser = subparsers.add_parser(
        "manuscript-plan",
        help="生成证据绑定的论文写作就绪计划",
    )
    manuscript_parser.add_argument("--project", required=True, help="课题 slug")
    manuscript_parser.add_argument(
        "--as-of", default="", help="计划截止日期 YYYY-MM-DD"
    )
    manuscript_parser.add_argument(
        "--format", choices=("markdown", "json"), default="markdown"
    )
    manuscript_parser.add_argument("--workspace", type=Path, default=Path.cwd())

    manuscript_audit_parser = subparsers.add_parser(
        "manuscript-audit",
        help="只读审计带注释的论文草稿，不重写草稿或执行实验",
    )
    manuscript_audit_parser.add_argument("--project", required=True, help="课题 slug")
    manuscript_audit_parser.add_argument("--draft", type=Path, required=True, help="writing/ 下的直接 .md 草稿")
    manuscript_audit_parser.add_argument(
        "--as-of", default="", help="审计截止日期 YYYY-MM-DD"
    )
    manuscript_audit_parser.add_argument(
        "--format", choices=("markdown", "json"), default="markdown"
    )
    manuscript_audit_parser.add_argument("--workspace", type=Path, default=Path.cwd())

    cycle_parser = subparsers.add_parser(
        "cycle", help="创建或恢复有界、可审计的科研循环"
    )
    cycle_parser.add_argument("--project", required=True, help="课题 slug")
    cycle_parser.add_argument("--new-run", action="store_true", help="显式开始新 run")
    cycle_parser.add_argument("--max-ideas", type=int, help="候选 Idea 上限（1-10）")
    cycle_parser.add_argument("--max-calls", type=int, help="模型调用上限（1-20）")
    cycle_parser.add_argument("--provider-role", help="config/providers.yaml 中的角色")
    cycle_parser.add_argument(
        "--allow-external-api",
        action="store_true",
        help="明确授权本次调用外部 API；仍需每个来源已授权",
    )
    cycle_parser.add_argument("--workspace", type=Path, default=Path.cwd())

    approve_parser = subparsers.add_parser(
        "approve-idea", help="由研究者批准一个已入围 Idea"
    )
    approve_parser.add_argument("--project", required=True, help="课题 slug")
    approve_parser.add_argument("--idea", required=True, help="Idea ID")
    approve_parser.add_argument("--reason", required=True, help="人工批准理由")
    approve_parser.add_argument("--workspace", type=Path, default=Path.cwd())

    project_parser = subparsers.add_parser("new-project", help="创建规范科研课题")
    project_parser.add_argument("--title", required=True, help="中文或英文课题标题")
    project_parser.add_argument("--slug", required=True, help="小写英文课题标识")
    project_parser.add_argument("--workspace", type=Path, default=Path.cwd())

    source_parser = subparsers.add_parser("add-source", help="登记并去重科研资料")
    source_parser.add_argument("source", help="本地文件、DOI、arXiv 或 URL")
    source_parser.add_argument("--project", help="把来源关联到指定课题 slug")
    source_parser.add_argument("--notes", default="", help="只在首次登记时保存的人工笔记")
    source_parser.add_argument(
        "--allow-external-api",
        action="store_true",
        help="明确允许把此公开来源发送给外部模型",
    )
    source_parser.add_argument("--workspace", type=Path, default=Path.cwd())

    sources_parser = subparsers.add_parser(
        "add-sources", help="从 UTF-8 清单原子批量登记科研资料"
    )
    sources_parser.add_argument("manifest", type=Path, help="每行一个来源的 UTF-8 文本")
    sources_parser.add_argument("--project", help="把全部来源关联到指定课题 slug")
    sources_parser.add_argument("--notes", default="", help="只对首次登记来源保存的人工笔记")
    sources_parser.add_argument(
        "--allow-external-api",
        action="store_true",
        help="明确允许把清单内公开来源发送给外部模型",
    )
    sources_parser.add_argument("--workspace", type=Path, default=Path.cwd())

    pdf_parser = subparsers.add_parser(
        "extract-pdf", help="提取 PDF 文本并保留页码边界"
    )
    pdf_parser.add_argument("pdf", type=Path)
    pdf_parser.add_argument("--output", type=Path, required=True)
    pdf_parser.add_argument(
        "--force", action="store_true", help="允许覆盖已有的生成文本"
    )

    model_parser = subparsers.add_parser(
        "model-call", help="调用经显式授权的 OpenAI-compatible 模型"
    )
    model_parser.add_argument("--base-url", required=True)
    model_parser.add_argument("--model", required=True)
    model_parser.add_argument("--api-key-env", required=True)
    model_parser.add_argument("--system", type=Path, required=True)
    model_parser.add_argument("--user", type=Path, required=True)
    model_parser.add_argument("--output", type=Path, required=True)
    model_parser.add_argument("--workspace", type=Path, default=Path.cwd())
    model_parser.add_argument(
        "--source-id",
        action="append",
        required=True,
        help="参与本次请求且已显式授权外发的来源 ID；多个来源重复传入",
    )
    model_parser.add_argument("--temperature", type=float, default=0.1)
    model_parser.add_argument("--timeout", type=float, default=60.0)
    model_parser.add_argument(
        "--allow-external-api",
        action="store_true",
        help="确认输入只含允许外发的公开或脱敏资料",
    )

    evidence_parser = subparsers.add_parser(
        "validate-ledger", help="校验证据账本的来源、定位和状态"
    )
    evidence_parser.add_argument("ledger", type=Path)
    evidence_parser.add_argument("--report", type=Path)
    evidence_parser.add_argument("--workspace", type=Path, default=Path.cwd())

    kb_parser = subparsers.add_parser(
        "kb", help="检索、推荐和检查本地科研方法知识库"
    )
    kb_subparsers = kb_parser.add_subparsers(dest="kb_command", required=True)

    kb_doctor = kb_subparsers.add_parser(
        "doctor", help="严格检查知识目录、卡片、来源和引用"
    )
    kb_doctor.add_argument("--workspace", type=Path, default=Path.cwd())

    kb_search = kb_subparsers.add_parser(
        "search", help="执行确定性本地方法学检索"
    )
    kb_search.add_argument("query", help="关键词或短语")
    kb_search.add_argument("--topic", choices=sorted(TOPICS), default="")
    kb_search.add_argument("--method", choices=sorted(METHODS), default="")
    kb_search.add_argument("--stage", choices=sorted(STAGES), default="")
    kb_search.add_argument("--priority", choices=sorted(PRIORITIES), default="")
    kb_search.add_argument(
        "--verified-scope",
        choices=("metadata", "abstract", "fulltext"),
        default="",
    )
    kb_search.add_argument("--limit", type=int, default=10)
    kb_search.add_argument("--format", choices=("text", "json"), default="text")
    kb_search.add_argument("--include-history", action="store_true")
    kb_search.add_argument("--workspace", type=Path, default=Path.cwd())

    kb_gaps = kb_subparsers.add_parser(
        "gaps", help="只读列出知识库核验、卡片和复核缺口"
    )
    kb_gaps.add_argument("--topic", choices=sorted(TOPICS), default="")
    kb_gaps.add_argument("--method", choices=sorted(METHODS), default="")
    kb_gaps.add_argument("--kind", choices=GAP_KINDS, default="")
    kb_gaps.add_argument("--as-of", default="", help="复核截止日期 YYYY-MM-DD")
    kb_gaps.add_argument("--limit", type=int, default=100)
    kb_gaps.add_argument("--format", choices=("text", "json"), default="text")
    kb_gaps.add_argument("--workspace", type=Path, default=Path.cwd())

    kb_recommend = kb_subparsers.add_parser(
        "recommend", help="按课题画像和当前阶段推荐方法学参考"
    )
    kb_recommend.add_argument("--project", required=True, help="课题 slug")
    kb_recommend.add_argument(
        "--format", choices=("text", "json"), default="text"
    )
    kb_recommend.add_argument("--workspace", type=Path, default=Path.cwd())
    return parser


@dataclass(frozen=True)
class _ProjectTransactionState:
    slug: str
    path: Path
    directory_identity: tuple[int, int]
    manifest_path: Path
    manifest_snapshot: bytes | None


def _path_identity(path: Path) -> tuple[int, int]:
    metadata = path.stat()
    return metadata.st_dev, metadata.st_ino


def _preflight_project(
    workspace: Path, slug: str | None
) -> _ProjectTransactionState | None:
    if slug is None:
        return None
    path = resolve_project_path(workspace, slug, require_exists=True)
    load_project_manifest(path, allow_legacy=True)
    manifest_path = path / "project.yaml"
    return _ProjectTransactionState(
        slug=slug,
        path=path,
        directory_identity=_path_identity(path),
        manifest_path=manifest_path,
        manifest_snapshot=_snapshot_file(manifest_path),
    )


def _project_slugs(workspace: Path) -> list[str]:
    root = resolve_workspace_directory(workspace, "projects")
    if not root.is_dir():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir())


def _empty_workspace_guide() -> str:
    return """# Research OS · 科研驾驶舱

## 下一步

原因：当前工作区还没有课题，先建立一个可追踪的研究目录。

```text
research-os new-project --title "你的课题标题" --slug your-topic
```

"""


def _snapshot_file(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def _restore_file(
    path: Path,
    snapshot: bytes | None,
    expected_parent_identity: tuple[int, int],
) -> None:
    if _path_identity(path.parent) != expected_parent_identity:
        raise OSError(f"回滚目录在提交前被替换: {path.parent}")
    if snapshot is None:
        path.unlink(missing_ok=True)
    else:
        atomic_write_bytes(
            path,
            snapshot,
            expected_parent_identity=expected_parent_identity,
        )


def _registry_path(workspace: Path) -> Path:
    return resolve_workspace_directory(workspace, "library") / "sources.jsonl"


def _link_sources_transactionally(
    workspace: Path,
    project_state: _ProjectTransactionState | None,
    source_ids: list[str],
    registry_path: Path,
    registry_snapshot: bytes | None,
    registry_directory_identity: tuple[int, int],
) -> None:
    if project_state is None:
        return
    try:
        current_project = resolve_project_path(
            workspace, project_state.slug, require_exists=True
        )
        if (
            current_project != project_state.path
            or _path_identity(current_project)
            != project_state.directory_identity
        ):
            raise OSError(f"课题目录在来源登记期间被替换: {current_project}")
        link_project_sources(
            workspace,
            project_state.slug,
            source_ids,
            project_state.directory_identity,
        )
    except BaseException:
        rollback_errors: list[Exception] = []
        try:
            current_registry = _registry_path(workspace)
            if (
                current_registry != registry_path
                or _path_identity(current_registry.parent)
                != registry_directory_identity
            ):
                raise OSError(
                    f"library 目录在回滚前被替换: {current_registry.parent}"
                )
            _restore_file(
                registry_path,
                registry_snapshot,
                registry_directory_identity,
            )
        except (OSError, ValueError) as rollback_error:
            rollback_errors.append(rollback_error)
        try:
            current_project = resolve_project_path(
                workspace, project_state.slug, require_exists=True
            )
            if (
                current_project != project_state.path
                or _path_identity(current_project)
                != project_state.directory_identity
            ):
                raise OSError(
                    f"课题目录在回滚前被替换: {current_project}"
                )
            _restore_file(
                project_state.manifest_path,
                project_state.manifest_snapshot,
                project_state.directory_identity,
            )
        except (OSError, ValueError) as rollback_error:
            rollback_errors.append(rollback_error)
        if rollback_errors:
            raise RuntimeError(
                "来源关联失败，且事务回滚失败；立即运行 research-os doctor 检查工作区: "
                + "; ".join(str(error) for error in rollback_errors)
            )
        raise


def _entry_verification_scope(entry) -> str:
    if entry.verification.fulltext == "verified":
        return "fulltext"
    if entry.verification.abstract == "verified":
        return "abstract"
    if entry.verification.metadata == "verified":
        return "metadata"
    return "unverified"


def _search_payload(results) -> list[dict[str, object]]:
    return [
        {
            "source_id": result.entry.source_id,
            "title": result.entry.title,
            "score": result.score,
            "matched_fields": list(result.matched_fields),
            "priority": result.entry.priority,
            "verification_scope": _entry_verification_scope(result.entry),
            "status": result.entry.status,
            "access_url": result.entry.access_url,
        }
        for result in results
    ]


def _render_kb_search(results) -> str:
    if not results:
        return (
            "没有匹配的知识条目。\n"
            "下一步：调整关键词或过滤条件，并记录需要补充核验的新来源。\n"
        )
    lines = ["# 科研方法知识库检索", ""]
    for index, result in enumerate(results, 1):
        entry = result.entry
        lines.extend(
            [
                f"## {index}. {entry.title}",
                "",
                f"- source_id: `{entry.source_id}`",
                f"- 得分: {result.score}",
                f"- 命中: {', '.join(result.matched_fields) or '过滤条件'}",
                f"- 优先级: {entry.priority}",
                f"- 核验范围: {_entry_verification_scope(entry)}",
                f"- 原文: {entry.access_url}",
                "- 边界: 全局知识条目不能直接作为课题引用证据。",
                (
                    f"- 关联提示: `$paper-intake 核验并把 {entry.source_id} "
                    "显式关联到目标课题`"
                ),
                "",
            ]
        )
    return "\n".join(lines)


def _gap_payload(gaps) -> list[dict[str, object]]:
    return [
        {
            "kind": gap.kind,
            "source_id": gap.source_id,
            "title": gap.title,
            "priority": gap.priority,
            "reason": gap.reason,
            "next_action": gap.next_action,
            "access_url": gap.access_url,
        }
        for gap in gaps
    ]


def _render_kb_gaps(gaps, *, as_of: date) -> str:
    if not gaps:
        return (
            "# 知识库维护队列\n\n"
            f"- 截止日期: {as_of.isoformat()}\n"
            "- 共 0 项\n"
            "- 模式: 只读，不联网、不修改 catalog 或核验状态。\n\n"
            "当前筛选范围没有待处理项。\n"
        )
    lines = [
        "# 知识库维护队列",
        "",
        f"- 截止日期: {as_of.isoformat()}",
        f"- 共 {len(gaps)} 项",
        "- 模式: 只读，不联网、不修改 catalog 或核验状态。",
        "",
    ]
    for index, gap in enumerate(gaps, 1):
        lines.extend(
            [
                f"## {index}. {gap.title}",
                "",
                f"- 类型: `{gap.kind}`",
                f"- source_id: `{gap.source_id}`",
                f"- 队列优先级: {gap.priority}",
                f"- 原因: {gap.reason}",
                f"- 下一步: {gap.next_action}",
                f"- 原文: {gap.access_url}",
                "",
            ]
        )
    return "\n".join(lines)


def _recommendation_payload(recommendations) -> list[dict[str, object]]:
    return [
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
        for item in recommendations
    ]


def _render_kb_recommend(recommendations) -> str:
    if not recommendations:
        return "当前没有可用的方法学推荐；请运行 research-os kb doctor。\n"
    lines = ["# 当前课题的方法学参考", ""]
    for index, item in enumerate(recommendations, 1):
        lines.extend(
            [
                f"## {index}. {item.title}",
                "",
                f"- 类型: {item.kind}",
                f"- source_id: `{item.source_id or '-'}`",
                f"- 推荐原因: {item.reason}",
                f"- 核验范围: {item.verification_scope}",
                f"- 可用于: {item.can_use_for}",
                f"- 不可用于: {item.cannot_use_for}",
                f"- 本地路径: `{item.path if item.path is not None else '-'}`",
                "",
            ]
        )
    return "\n".join(lines)


def _dashboard_payload(snapshot: ProjectDashboard) -> dict[str, object]:
    return {
        "schema_version": snapshot.schema_version,
        "as_of": snapshot.as_of,
        "project": {
            "title": snapshot.project.title,
            "slug": snapshot.project.slug,
            "stage": snapshot.project.stage,
            "state": snapshot.project.state,
            "blockers": list(snapshot.project.blockers),
        },
        "evidence": {
            "linked_sources": snapshot.evidence.linked_sources,
            "verified_sources": snapshot.evidence.verified_sources,
            "stale_or_unknown_source_ids": list(
                snapshot.evidence.stale_or_unknown_source_ids
            ),
            "claims": snapshot.evidence.claims,
            "support_links": snapshot.evidence.support_links,
            "opposition_links": snapshot.evidence.opposition_links,
            "conflicted_claims": snapshot.evidence.conflicted_claims,
            "claims_with_limitations": snapshot.evidence.claims_with_limitations,
            "validation_issues": [
                {
                    "code": issue.code,
                    "claim_id": issue.claim_id,
                    "message": issue.message,
                }
                for issue in snapshot.evidence.validation_issues
            ],
        },
        "idea": {
            "run_id": snapshot.idea.run_id,
            "cycle_state": snapshot.idea.cycle_state,
            "candidate_count": snapshot.idea.candidate_count,
            "selected_idea_ids": list(snapshot.idea.selected_idea_ids),
            "human_decision_required": snapshot.idea.human_decision_required,
            "calls_used": snapshot.idea.calls_used,
            "max_calls": snapshot.idea.max_calls,
            "candidate_generation_complete": (
                snapshot.idea.candidate_generation_complete
            ),
            "novelty_check_complete": snapshot.idea.novelty_check_complete,
            "independent_review_complete": (
                snapshot.idea.independent_review_complete
            ),
            "meta_review_complete": snapshot.idea.meta_review_complete,
        },
        "recommendations": _recommendation_payload(snapshot.recommendations),
        "risks": [
            {
                "code": risk.code,
                "severity": risk.severity,
                "state": risk.state,
                "message": risk.message,
                "trigger": risk.trigger,
            }
            for risk in snapshot.risks
        ],
        "actions": [
            {
                "code": action.code,
                "priority": action.priority,
                "category": action.category,
                "rationale": action.rationale,
                "expected_artifact": action.expected_artifact,
                "command": action.command,
            }
            for action in snapshot.actions
        ],
    }


def _render_dashboard(snapshot: ProjectDashboard) -> str:
    state_labels = {
        "ready": "可推进",
        "in_progress": "进行中",
        "blocked": "受阻",
        "awaiting_human": "等待人工决策",
    }
    lines = [
        f"# {snapshot.project.title} · 课题研究驾驶舱",
        "",
        f"- 截止日期: {snapshot.as_of}",
        "- 模式: 只读、本地、无外部 API。",
        "",
        "## 课题状态",
        "",
        f"- 当前阶段: {snapshot.project.stage}",
        f"- 状态: {state_labels[snapshot.project.state]}",
    ]
    if snapshot.project.blockers:
        lines.extend(
            f"- 阻塞: {blocker}" for blocker in snapshot.project.blockers
        )
    else:
        lines.append("- 阻塞: 无")
    lines.extend(
        [
            "",
            "## 证据健康度",
            "",
            (
                f"- 来源: {snapshot.evidence.verified_sources}/"
                f"{snapshot.evidence.linked_sources} 个已核验"
            ),
            f"- Claims: {snapshot.evidence.claims}",
            (
                f"- 支持/反对链接: {snapshot.evidence.support_links}/"
                f"{snapshot.evidence.opposition_links}"
            ),
            f"- 冲突 Claims: {snapshot.evidence.conflicted_claims}",
            f"- 含限制说明: {snapshot.evidence.claims_with_limitations}",
            f"- 校验问题: {len(snapshot.evidence.validation_issues)}",
            "",
            "## Idea 与决策",
            "",
            f"- Run: {snapshot.idea.run_id or '-'}",
            f"- 循环状态: {snapshot.idea.cycle_state}",
            f"- 候选数: {snapshot.idea.candidate_count}",
            (
                "- 门禁: "
                f"候选生成={'完成' if snapshot.idea.candidate_generation_complete else '待完成'}；"
                f"新颖性={'完成' if snapshot.idea.novelty_check_complete else '待完成'}；"
                f"独立评审={'完成' if snapshot.idea.independent_review_complete else '待完成'}；"
                f"Meta-review={'完成' if snapshot.idea.meta_review_complete else '待完成'}"
            ),
            (
                "- 人工决策: 需要"
                if snapshot.idea.human_decision_required
                else "- 人工决策: 当前不需要"
            ),
            (
                "- 已选 Idea: "
                + (", ".join(snapshot.idea.selected_idea_ids) or "-")
            ),
            "",
            "## 方法学参考",
            "",
            "全局知识条目只是方法学指导，不会自动成为当前课题引用证据。",
        ]
    )
    if snapshot.recommendations:
        for item in snapshot.recommendations:
            lines.append(
                f"- **{item.title}**（{item.kind}）：{item.reason} "
                f"[核验范围: {item.verification_scope}]"
            )
    else:
        lines.append("- 当前阶段暂无可用方法学条目。")
    lines.extend(["", "## 风险雷达", ""])
    if snapshot.risks:
        for risk in snapshot.risks:
            lines.extend(
                [
                    f"- **{risk.code}** [{risk.severity}/{risk.state}] {risk.message}",
                    f"  触发依据: `{risk.trigger}`",
                ]
            )
    else:
        lines.append("- 未发现由当前结构化事实触发的风险；未知状态不会被报告为已确认缺陷。")
    lines.extend(["", "## 今日三个行动", ""])
    if snapshot.actions:
        for index, action in enumerate(snapshot.actions, 1):
            lines.extend(
                [
                    f"### {index}. {action.code}",
                    "",
                    f"- 原因: {action.rationale}",
                    f"- 预期产物: `{action.expected_artifact}`",
                    "",
                    "```text",
                    action.command,
                    "```",
                    "",
                ]
            )
    else:
        lines.append("- 当前没有可安全生成的行动。")
    return "\n".join(lines).rstrip() + "\n"


def _knowledge_stage_for_guide(report) -> str:
    skill_to_stage = {
        "research-project-init": "problem-definition",
        "paper-intake": "literature-search",
        "paper-deep-read": "literature-search",
        "literature-synthesis": "evidence-synthesis",
        "research-cycle": "idea-review",
        "idea-review": "idea-review",
        "experiment-advisor": "experiment-design",
        "result-interpreter": "result-interpretation",
        "manuscript-assistant": "writing",
        "mock-reviewer": "review",
        "research-weekly-review": "review",
    }
    if report.next_action.skill in skill_to_stage:
        return skill_to_stage[report.next_action.skill]
    target = report.next_action.target.casefold()
    if "idea" in target or "cycles" in target:
        return "idea-review"
    if "experiment" in target or "artifacts" in target:
        return "experiment-design"
    if "result" in target:
        return "result-interpretation"
    if "writing" in target:
        return "writing"
    if "review" in target:
        return "review"
    return "problem-definition"


def _run(args: argparse.Namespace) -> int:
    if args.command == "doctor":
        report = run_doctor(
            args.workspace,
            stdout_encoding=getattr(sys.stdout, "encoding", None),
        )
        print(render_doctor(report), end="")
        return report.exit_code
    if args.command == "guide":
        slug = args.project
        if slug is None:
            slugs = _project_slugs(args.workspace)
            if not slugs:
                print(_empty_workspace_guide(), end="")
                return 0
            if len(slugs) > 1:
                raise ValueError(
                    "存在多个课题，请使用 --project 指定: " + ", ".join(slugs)
                )
            slug = slugs[0]
        print(render_guide(guide_project(args.workspace, slug)), end="")
        return 0
    if args.command == "dashboard":
        if args.as_of:
            try:
                as_of = date.fromisoformat(args.as_of)
            except ValueError as exc:
                raise ValueError("--as-of 必须是 YYYY-MM-DD 日期") from exc
        else:
            as_of = date.today()
        snapshot = build_project_dashboard(
            args.workspace,
            args.project,
            as_of=as_of,
        )
        if args.format == "json":
            print(
                json.dumps(
                    _dashboard_payload(snapshot),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(_render_dashboard(snapshot), end="")
        return 0
    if args.command == "meeting-brief":
        if args.as_of:
            try:
                as_of = date.fromisoformat(args.as_of)
            except ValueError as exc:
                raise ValueError("--as-of 必须是 YYYY-MM-DD 日期") from exc
        else:
            as_of = date.today()
        brief = build_meeting_brief(
            args.workspace,
            args.project,
            as_of=as_of,
        )
        if args.format == "json":
            print(
                json.dumps(
                    meeting_brief_payload(brief),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(render_meeting_brief(brief), end="")
        return 0
    if args.command == "manuscript-plan":
        if args.as_of:
            try:
                as_of = date.fromisoformat(args.as_of)
            except ValueError as exc:
                raise ValueError("--as-of 必须是 YYYY-MM-DD 日期") from exc
        else:
            as_of = date.today()
        plan = build_manuscript_plan(
            args.workspace,
            args.project,
            as_of=as_of,
        )
        if args.format == "json":
            print(
                json.dumps(
                    manuscript_plan_payload(plan),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(render_manuscript_plan(plan), end="")
        return 0
    if args.command == "manuscript-audit":
        if args.as_of:
            try:
                as_of = date.fromisoformat(args.as_of)
            except ValueError as exc:
                raise ValueError("--as-of 必须是 YYYY-MM-DD 日期") from exc
        else:
            as_of = date.today()
        try:
            audit = build_manuscript_audit(
                args.workspace,
                args.project,
                args.draft,
                as_of=as_of,
            )
        except PermissionError as exc:
            if str(exc) == "PHI_SUSPECTED":
                raise PermissionError("PHI_SUSPECTED") from None
            raise ValueError("MANUSCRIPT_AUDIT_INPUT_ERROR") from None
        except (UnicodeError, ValueError, FileNotFoundError):
            raise ValueError("MANUSCRIPT_AUDIT_INPUT_ERROR") from None
        except OSError:
            raise OSError("MANUSCRIPT_AUDIT_STATE_CHANGED") from None
        if args.format == "json":
            print(
                json.dumps(
                    manuscript_audit_payload(audit),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(render_manuscript_audit(audit), end="")
        return 1 if audit.issues else 0
    if args.command == "kb":
        if args.kb_command == "doctor":
            report = inspect_knowledge_base(args.workspace)
            if not report.issues:
                print(
                    f"[PASS] knowledge: {report.entry_count} 条目录，"
                    f"{report.card_count} 张知识卡"
                )
            else:
                for issue in report.issues:
                    print(f"[{issue.level}] knowledge: {issue.message}")
                if report.exit_code == 0:
                    print(
                        f"[PASS] knowledge: {report.entry_count} 条目录，"
                        f"{report.card_count} 张知识卡"
                    )
            return report.exit_code
        if args.kb_command == "search":
            kb = load_knowledge_base(args.workspace)
            results = search_knowledge(
                kb,
                args.query,
                filters=SearchFilters(
                    topic=args.topic,
                    method=args.method,
                    stage=args.stage,
                    priority=args.priority,
                    verified_scope=args.verified_scope,
                    include_history=args.include_history,
                ),
                limit=args.limit,
            )
            if args.format == "json":
                print(json.dumps(_search_payload(results), ensure_ascii=False, indent=2))
            else:
                print(_render_kb_search(results), end="")
            return 0
        if args.kb_command == "gaps":
            if args.as_of:
                try:
                    as_of = date.fromisoformat(args.as_of)
                except ValueError as exc:
                    raise ValueError("--as-of 必须是 YYYY-MM-DD 日期") from exc
            else:
                as_of = date.today()
            kb = load_knowledge_base(args.workspace)
            gaps = find_knowledge_gaps(
                kb,
                as_of=as_of,
                filters=GapFilters(
                    topic=args.topic,
                    method=args.method,
                    kind=args.kind,
                ),
                limit=args.limit,
            )
            if args.format == "json":
                print(json.dumps(_gap_payload(gaps), ensure_ascii=False, indent=2))
            else:
                print(_render_kb_gaps(gaps, as_of=as_of), end="")
            return 0
        if args.kb_command == "recommend":
            guide = guide_project(args.workspace, args.project)
            recommendations = recommend_for_project(
                args.workspace,
                args.project,
                stage=_knowledge_stage_for_guide(guide),
            )
            if args.format == "json":
                print(
                    json.dumps(
                        _recommendation_payload(recommendations),
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print(_render_kb_recommend(recommendations), end="")
            return 0
    if args.command == "cycle":
        if args.provider_role and not args.allow_external_api:
            raise PermissionError(
                "使用外部 provider 必须同时显式传入 --allow-external-api"
            )
        if args.allow_external_api and not args.provider_role:
            raise ValueError("--allow-external-api 只能与 --provider-role 一起使用")
        provider = None
        if args.provider_role:
            provider = load_provider(
                args.workspace.resolve() / "config" / "providers.yaml",
                args.provider_role,
            )
        action = advance_cycle(
            args.workspace,
            args.project,
            new_run=args.new_run,
            max_ideas=args.max_ideas,
            max_calls=args.max_calls,
            provider=provider,
            allow_external_api=args.allow_external_api,
        )
        target = str(action.target) if action.target is not None else "-"
        print(f"Run: {action.run_id}")
        print(f"状态: {action.state}")
        print(
            f"调用: {action.manifest.calls_used}/{action.manifest.max_calls}"
        )
        print(f"原因: {action.reason}")
        print(f"目标: {target}")
        print(f"下一步: {action.next_action}")
        return 0
    if args.command == "approve-idea":
        approve_active_cycle_idea(
            args.workspace,
            args.project,
            args.idea,
            reason=args.reason,
        )
        print(f"已由研究者批准 Idea: {args.idea}")
        print(f"下一步: research-os guide --project {args.project}")
        return 0
    if args.command == "new-project":
        path = create_project(args.workspace, args.title, args.slug)
        print(f"已创建课题: {path}")
        print(f"下一步: research-os guide --project {args.slug}")
        return 0
    if args.command == "add-source":
        workspace = args.workspace.resolve()
        project_state = _preflight_project(workspace, args.project)
        registry_path = _registry_path(workspace)
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_directory_identity = _path_identity(registry_path.parent)
        registry = SourceRegistry(
            registry_path,
            expected_parent_identity=registry_directory_identity,
        )
        registry_snapshot = _snapshot_file(registry.path)
        record = registry.add(
            args.source,
            notes=args.notes,
            external_api_allowed=args.allow_external_api,
        )
        _link_sources_transactionally(
            workspace,
            project_state,
            [record.source_id],
            registry.path,
            registry_snapshot,
            registry_directory_identity,
        )
        suffix = f"，已关联课题 {args.project}" if args.project else ""
        print(f"已登记来源: {record.source_id} ({record.kind}){suffix}")
        return 0
    if args.command == "add-sources":
        workspace = args.workspace.resolve()
        project_state = _preflight_project(workspace, args.project)
        values = load_source_manifest(args.manifest.resolve())
        registry_path = _registry_path(workspace)
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_directory_identity = _path_identity(registry_path.parent)
        registry = SourceRegistry(
            registry_path,
            expected_parent_identity=registry_directory_identity,
        )
        registry_snapshot = _snapshot_file(registry.path)
        result = registry.add_many(
            values,
            notes=args.notes,
            external_api_allowed=args.allow_external_api,
        )
        _link_sources_transactionally(
            workspace,
            project_state,
            list(dict.fromkeys(record.source_id for record in result.records)),
            registry.path,
            registry_snapshot,
            registry_directory_identity,
        )
        suffix = f"，关联课题 {args.project}" if args.project else ""
        print(
            f"批量登记完成：新增 {result.added}，重复 {result.duplicates}，"
            f"升级外发许可 {result.authorizations_upgraded}{suffix}"
        )
        return 0
    if args.command == "extract-pdf":
        if args.pdf.resolve() == args.output.resolve():
            raise ValueError("输出路径不能与输入 PDF 相同")
        if args.output.exists() and not args.force:
            raise FileExistsError(f"输出已存在，使用 --force 才能覆盖: {args.output}")
        result = extract_pdf(args.pdf)
        atomic_write_text(args.output.resolve(), result.markdown)
        print(f"已提取 {len(result.pages)} 页: {args.output.resolve()}")
        return 0
    if args.command == "model-call":
        output = args.output.resolve()
        provenance_path = output.with_name(f"{output.name}.provenance.json")
        input_paths = {args.system.resolve(), args.user.resolve()}
        if output.exists():
            raise FileExistsError(f"模型输出已存在，不自动覆盖: {output}")
        if provenance_path in input_paths:
            raise ValueError("provenance 输出不能覆盖 system 或 user 输入")
        if provenance_path.exists():
            raise FileExistsError(
                f"provenance 输出已存在，不自动覆盖: {provenance_path}"
            )
        system_text, user_text = load_authorized_external_texts(
            _registry_path(args.workspace.resolve()),
            [args.system, args.user],
            args.source_id,
        )
        provider = OpenAICompatibleProvider(
            args.base_url,
            args.model,
            args.api_key_env,
            temperature=args.temperature,
            timeout=args.timeout,
        )
        result = provider.complete(
            system_text,
            user_text,
            external_api_allowed=args.allow_external_api,
        )
        atomic_write_text(output, result.content)
        atomic_write_text(
            provenance_path,
            json.dumps(result.provenance, ensure_ascii=False, indent=2) + "\n",
        )
        print(f"模型输出: {output}")
        print(f"调用记录: {provenance_path}")
        return 0
    if args.command == "validate-ledger":
        registry = SourceRegistry(
            _registry_path(args.workspace.resolve())
        )
        known_source_ids = registry.verified_source_ids()
        issues = validate_ledger(
            load_ledger(args.ledger), known_source_ids=known_source_ids
        )
        report = render_validation_report(args.ledger, issues)
        if args.report:
            report_path = args.report.resolve()
            if report_path == args.ledger.resolve():
                raise ValueError("校验报告不能覆盖证据账本")
            if report_path.exists():
                raise FileExistsError(f"校验报告已存在，不自动覆盖: {report_path}")
            atomic_write_text(report_path, report)
            print(f"校验报告: {report_path}")
        else:
            print(report, end="")
        return 1 if issues else 0
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


def _configure_windows_utf8() -> None:
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def entrypoint() -> None:
    _configure_windows_utf8()
    raise SystemExit(main())
