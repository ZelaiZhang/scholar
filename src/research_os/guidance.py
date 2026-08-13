from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from research_os.evidence import load_ledger, validate_ledger
from research_os.project import (
    load_project_manifest,
    resolve_project_path,
    resolve_workspace_directory,
    template_content,
)
from research_os.sources import SourceRegistry
from research_os.cycle import CycleManifest, load_active_cycle
from research_os.ideas import load_idea_archive
from research_os.io import (
    assert_directory_identity,
    direct_file_identity,
    directory_identity,
    read_stable_direct_text,
)
from research_os.knowledge_recommend import (
    KnowledgeRecommendation,
    recommend_for_project,
)
from research_os.project import _is_link_or_reparse_point


@dataclass(frozen=True)
class StageView:
    code: str
    name: str
    progress: str
    status: str
    detail: str
    artifact_path: str = ""
    artifact_sha256: str = ""
    dependency_sha256: str = ""
    artifact_identity: tuple[int, int] | None = None


@dataclass(frozen=True)
class NextAction:
    reason: str
    target: str
    command: str
    skill: str | None


@dataclass(frozen=True)
class GuideReport:
    title: str
    slug: str
    stages: tuple[StageView, ...]
    next_action: NextAction
    method_references: tuple[KnowledgeRecommendation, ...] = ()
    knowledge_issue: str = ""


def _normalized(text: str) -> str:
    return text.replace("\r\n", "\n").strip()


def _document_progress(
    project_path: Path,
    filename: str,
    template_name: str,
    title: str,
    completion_marker: str,
    expected_project_identity: tuple[int, int],
) -> tuple[str, str, tuple[int, int] | None]:
    path = project_path / filename
    if not path.is_file():
        return "blocked", "missing", None
    actual = read_stable_direct_text(
        path,
        expected_parent=project_path,
        expected_parent_identity=expected_project_identity,
    )
    expected = template_content(template_name, None).replace(
        "{{PROJECT_TITLE}}", title
    )
    digest = hashlib.sha256(actual.encode("utf-8")).hexdigest()
    identity = direct_file_identity(
        path,
        expected_parent=project_path,
        expected_parent_identity=expected_project_identity,
    )
    if _normalized(actual) == _normalized(expected):
        return "unstarted", digest, identity
    marker = f"<!-- research-os:stage={completion_marker} -->"
    return ("complete" if marker in actual else "in_progress"), digest, identity


def validate_stage_documents(
    project_path: Path,
    expected_project_identity: tuple[int, int],
    stages: tuple[StageView, ...],
) -> None:
    """Reject a mixed snapshot if any stage document changed after guidance."""
    for stage in stages:
        if not stage.artifact_path:
            continue
        path = project_path / stage.artifact_path
        if stage.artifact_sha256 == "missing":
            if path.exists():
                raise OSError(f"stage document changed after capture: {path}")
            continue
        try:
            identity = direct_file_identity(
                path,
                expected_parent=project_path,
                expected_parent_identity=expected_project_identity,
            )
            actual = read_stable_direct_text(
                path,
                expected_parent=project_path,
                expected_parent_identity=expected_project_identity,
            )
        except (OSError, ValueError) as exc:
            raise OSError(f"stage document changed after capture: {path}") from exc
        digest = hashlib.sha256(actual.encode("utf-8")).hexdigest()
        if digest != stage.artifact_sha256 or identity != stage.artifact_identity:
            raise OSError(f"stage document changed after capture: {path}")
        if stage.code == "result_interpretation" and stage.dependency_sha256:
            try:
                _inputs, dependency_sha256 = _result_inputs(
                    project_path,
                    expected_project_identity,
                )
            except (OSError, UnicodeError, ValueError) as exc:
                raise OSError("result inputs changed after stage capture") from exc
            if dependency_sha256 != stage.dependency_sha256:
                raise OSError("result inputs changed after stage capture")


def _progress_status(progress: str) -> str:
    return {
        "blocked": "受阻",
        "unstarted": "未开始",
        "in_progress": "进行中",
        "complete": "已产出",
    }[progress]


def _linked_paper_card_count(
    library_root: Path, source_ids: tuple[str, ...]
) -> int:
    papers_root = library_root / "papers"
    if not source_ids or not papers_root.is_dir():
        return 0
    count = 0
    for path in papers_root.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        if any(source_id in text for source_id in source_ids):
            count += 1
    return count


_RESULT_EXTENSIONS = {".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml"}
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _result_inputs(
    project_path: Path,
    expected_project_identity: tuple[int, int],
) -> tuple[tuple[Path, ...], str]:
    artifacts = project_path / "artifacts"
    if not artifacts.is_dir():
        return (), "missing"
    assert_directory_identity(
        project_path,
        expected_project_identity,
        context="project",
    )
    artifacts_identity = directory_identity(artifacts)
    manifest_path = artifacts / "results-manifest.yaml"
    if not manifest_path.exists():
        return (), "missing"
    raw_text = read_stable_direct_text(
        manifest_path,
        expected_parent=artifacts,
        expected_parent_identity=artifacts_identity,
        max_bytes=1024 * 1024,
    )
    try:
        raw = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ValueError("results manifest is not valid YAML") from exc
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "results"}:
        raise ValueError("results manifest must contain only schema_version and results")
    if raw["schema_version"] != 1 or not isinstance(raw["results"], list):
        raise ValueError("results manifest schema_version must be 1 and results a list")
    inputs: list[Path] = []
    seen: set[str] = set()
    required = {"path", "sha256", "source_repository", "generated_at"}
    for index, item in enumerate(raw["results"], 1):
        if not isinstance(item, dict) or set(item) != required:
            raise ValueError(f"results manifest entry {index} has invalid fields")
        relative = item["path"]
        digest = item["sha256"]
        repository = item["source_repository"]
        generated_at = item["generated_at"]
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).name != relative
            or relative in seen
        ):
            raise ValueError(f"results manifest entry {index} has an unsafe path")
        if Path(relative).suffix.lower() not in _RESULT_EXTENSIONS:
            raise ValueError(f"results manifest entry {index} has an unsupported format")
        if not isinstance(digest, str) or not _SHA256_PATTERN.fullmatch(digest):
            raise ValueError(f"results manifest entry {index} has an invalid sha256")
        if not isinstance(repository, str) or not repository.strip():
            raise ValueError(
                f"results manifest entry {index} needs source_repository provenance"
            )
        if not isinstance(generated_at, str) or not generated_at.strip():
            raise ValueError(f"results manifest entry {index} needs generated_at")
        try:
            datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(
                f"results manifest entry {index} has invalid generated_at"
            ) from exc
        path = artifacts / relative
        actual_text = read_stable_direct_text(
            path,
            expected_parent=artifacts,
            expected_parent_identity=artifacts_identity,
        )
        actual_digest = hashlib.sha256(actual_text.encode("utf-8")).hexdigest()
        if actual_digest != digest:
            raise ValueError(f"result artifact hash mismatch: {relative}")
        seen.add(relative)
        inputs.append(path)
    assert_directory_identity(artifacts, artifacts_identity, context="artifacts")
    assert_directory_identity(
        project_path,
        expected_project_identity,
        context="project",
    )
    identity_parts = [
        str(artifacts_identity),
        str(
            direct_file_identity(
                manifest_path,
                expected_parent=artifacts,
                expected_parent_identity=artifacts_identity,
            )
        ),
    ]
    identity_parts.extend(
        str(
            direct_file_identity(
                path,
                expected_parent=artifacts,
                expected_parent_identity=artifacts_identity,
            )
        )
        for path in inputs
    )
    dependency_token = "\n".join(
        (raw_text, *(str(path.name) for path in inputs), *identity_parts)
    )
    return tuple(inputs), hashlib.sha256(dependency_token.encode("utf-8")).hexdigest()


def _markdown_outputs(folder: Path) -> tuple[Path, ...]:
    if not folder.is_dir():
        return ()
    return tuple(sorted(path for path in folder.glob("*.md") if path.is_file()))


def _blocked_action(slug: str, reason: str) -> NextAction:
    ledger = f"projects/{slug}/02-evidence-ledger.yaml"
    return NextAction(
        reason=reason,
        target="02-evidence-ledger.yaml",
        command=f'research-os validate-ledger "{ledger}" --workspace .',
        skill=None,
    )


def _knowledge_stage(next_action: NextAction) -> str:
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
    if next_action.skill in skill_to_stage:
        return skill_to_stage[next_action.skill]
    target = next_action.target.casefold()
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


def guide_project(
    workspace: Path,
    slug: str,
    *,
    expected_project_identity: tuple[int, int] | None = None,
) -> GuideReport:
    workspace = workspace.resolve()
    project_path = resolve_project_path(workspace, slug, require_exists=True)
    project_identity = expected_project_identity or directory_identity(project_path)
    assert_directory_identity(project_path, project_identity, context="project")
    manifest = load_project_manifest(
        project_path,
        allow_legacy=True,
        expected_directory_identity=project_identity,
    )
    library_root = resolve_workspace_directory(workspace, "library")
    registry = SourceRegistry(library_root / "sources.jsonl")
    globally_verified_source_ids = registry.verified_source_ids()
    known_source_ids = set(manifest.source_ids) & globally_verified_source_ids
    unknown_linked = [
        source_id
        for source_id in manifest.source_ids
        if source_id not in globally_verified_source_ids
    ]

    ledger_error = ""
    ledger: dict[str, object] = {"claims": []}
    ledger_issues = []
    try:
        ledger = load_ledger(
            project_path / "02-evidence-ledger.yaml",
            expected_parent=project_path,
            expected_parent_identity=project_identity,
        )
        ledger_issues = validate_ledger(
            ledger, known_source_ids=known_source_ids
        )
    except (OSError, ValueError) as exc:
        ledger_error = str(exc)

    brief_progress, brief_sha256, brief_identity = _document_progress(
        project_path,
        "00-research-brief.md",
        "research-brief.md",
        manifest.title,
        "brief-complete",
        project_identity,
    )
    brief_ready = brief_progress == "complete"
    paper_card_count = _linked_paper_card_count(
        library_root, manifest.source_ids
    )
    raw_claims = ledger.get("claims", [])
    claim_count = len(raw_claims) if isinstance(raw_claims, list) else 0
    literature_progress, literature_sha256, literature_identity = _document_progress(
        project_path,
        "03-literature-review.md",
        "literature-review.md",
        manifest.title,
        "synthesis-complete",
        project_identity,
    )
    literature_ready = literature_progress == "complete"
    idea_progress, idea_sha256, idea_identity = _document_progress(
        project_path,
        "04-idea-candidates.md",
        "idea-candidates.md",
        manifest.title,
        "idea-complete",
        project_identity,
    )
    legacy_idea_ready = idea_progress == "complete"
    cycle_manifest: CycleManifest | None = None
    cycle_error = ""
    selected_idea_ids: tuple[str, ...] = ()
    if (project_path / "cycles").exists():
        try:
            _run_dir, cycle_manifest = load_active_cycle(
                workspace,
                slug,
                expected_project_identity=project_identity,
            )
            ideas_path = project_path / "ideas"
            ideas_identity = directory_identity(ideas_path)
            assert_directory_identity(
                project_path,
                project_identity,
                context="project",
            )
            archive = load_idea_archive(
                ideas_path / "archive.yaml",
                allowed_source_ids=set(manifest.source_ids),
                expected_parent=ideas_path,
                expected_parent_identity=ideas_identity,
            )
            selected_idea_ids = tuple(
                idea.idea_id
                for idea in archive.ideas
                if idea.status == "selected"
                and idea.generated_by_run == cycle_manifest.run_id
            )
            if cycle_manifest.state == "completed" and not selected_idea_ids:
                cycle_error = "completed run 缺少匹配的人工批准 Idea"
        except (OSError, UnicodeError, ValueError) as exc:
            cycle_error = str(exc)
    idea_ready = (
        bool(selected_idea_ids)
        if cycle_manifest is not None
        else legacy_idea_ready
    )
    design_progress, design_sha256, design_identity = _document_progress(
        project_path,
        "05-experiment-design.md",
        "experiment-design.md",
        manifest.title,
        "design-complete",
        project_identity,
    )
    design_ready = design_progress == "complete"
    result_progress, result_sha256, result_identity = _document_progress(
        project_path,
        "06-result-analysis.md",
        "result-analysis.md",
        manifest.title,
        "result-complete",
        project_identity,
    )
    result_ready = result_progress == "complete"
    result_inputs, result_inputs_sha256 = _result_inputs(
        project_path,
        project_identity,
    )
    manuscripts = _markdown_outputs(project_path / "writing")
    reviews = _markdown_outputs(project_path / "reviews")

    ledger_blocked = bool(ledger_error or ledger_issues)
    evidence_blocked = bool(ledger_blocked or unknown_linked)
    if ledger_error:
        evidence_detail = f"账本无法读取：{ledger_error}"
    elif unknown_linked:
        evidence_detail = f"课题关联了无效或已漂移来源：{', '.join(unknown_linked)}"
    elif ledger_issues:
        evidence_detail = f"证据账本有 {len(ledger_issues)} 项校验问题"
    elif claim_count and literature_ready:
        evidence_detail = f"{claim_count} 条 claim，文献综合已编辑"
    elif claim_count or literature_progress == "in_progress":
        evidence_detail = "证据账本与文献综合尚未同时完成"
    else:
        evidence_detail = "尚未形成证据 claim 和文献综合"

    if evidence_blocked:
        synthesis_status = "受阻"
    elif claim_count and literature_ready:
        synthesis_status = "已产出"
    elif claim_count or literature_progress == "in_progress":
        synthesis_status = "进行中"
    else:
        synthesis_status = "未开始"

    if unknown_linked:
        intake_progress = "blocked"
        intake_status = "受阻"
        intake_detail = f"{len(unknown_linked)} 个关联来源无效或内容已改变"
    elif manifest.source_ids:
        intake_progress = "complete"
        intake_status = "已产出"
        intake_detail = f"已显式关联 {len(manifest.source_ids)} 个来源"
    else:
        intake_progress = "unstarted"
        intake_status = "未开始"
        intake_detail = "尚未为本课题关联来源"

    if not result_inputs:
        result_stage_progress = "unstarted"
        result_status = "未开始"
        result_detail = "等待独立实验仓库的聚合结果"
    elif result_ready:
        result_stage_progress = "complete"
        result_status = "已产出"
        result_detail = f"已导入 {len(result_inputs)} 个结果文件并完成解读"
    else:
        result_stage_progress = "in_progress"
        result_status = "进行中"
        result_detail = f"已导入 {len(result_inputs)} 个结果文件，尚未解读"

    if cycle_error:
        idea_stage_progress = "blocked"
        idea_stage_status = "受阻"
        idea_stage_detail = f"科研循环不可读：{cycle_error}"
    elif cycle_manifest is not None:
        idea_stage_progress = (
            "complete"
            if cycle_manifest.state == "completed" and idea_ready
            else "in_progress"
        )
        idea_stage_status = (
            "已产出" if cycle_manifest.state == "completed" and idea_ready else "进行中"
        )
        idea_stage_detail = (
            f"{cycle_manifest.run_id} · {cycle_manifest.state} · "
            f"调用 {cycle_manifest.calls_used}/{cycle_manifest.max_calls}"
        )
    else:
        idea_stage_progress = idea_progress
        idea_stage_status = _progress_status(idea_progress)
        idea_stage_detail = {
            "blocked": "Idea 文件缺失",
            "unstarted": "仍是空白模板",
            "in_progress": "已编辑，等待启动结构化科研循环",
            "complete": "旧版候选 Idea 已通过反向审查门禁",
        }[idea_progress]

    stages = (
        StageView(
            "problem_definition",
            "课题定义",
            brief_progress,
            _progress_status(brief_progress),
            {
                "blocked": "研究简报缺失",
                "unstarted": "仍是空白模板",
                "in_progress": "已编辑，尚未通过质量门禁",
                "complete": "研究简报已通过质量门禁",
            }[brief_progress],
            "00-research-brief.md",
            brief_sha256,
            "",
            brief_identity,
        ),
        StageView(
            "source_intake",
            "资料导入",
            intake_progress,
            intake_status,
            intake_detail,
        ),
        StageView(
            "paper_deep_read",
            "论文精读",
            "complete" if paper_card_count else "unstarted",
            "已产出" if paper_card_count else "未开始",
            f"找到 {paper_card_count} 张关联论文卡片",
        ),
        StageView(
            "evidence_synthesis",
            "文献综合",
            (
                "blocked"
                if evidence_blocked
                else "complete"
                if claim_count and literature_ready
                else "in_progress"
                if claim_count or literature_progress == "in_progress"
                else "unstarted"
            ),
            synthesis_status,
            evidence_detail,
            "03-literature-review.md",
            literature_sha256,
            "",
            literature_identity,
        ),
        StageView(
            "idea_review",
            "Idea 审查",
            idea_stage_progress,
            idea_stage_status,
            idea_stage_detail,
            "04-idea-candidates.md",
            idea_sha256,
            "",
            idea_identity,
        ),
        StageView(
            "experiment_design",
            "实验设计",
            design_progress,
            _progress_status(design_progress),
            {
                "blocked": "实验设计文件缺失",
                "unstarted": "仍是空白模板",
                "in_progress": "已编辑，尚未通过设计门禁",
                "complete": "实验设计已通过质量门禁",
            }[design_progress],
            "05-experiment-design.md",
            design_sha256,
            "",
            design_identity,
        ),
        StageView(
            "result_interpretation",
            "结果解读",
            result_stage_progress,
            result_status,
            result_detail,
            "06-result-analysis.md",
            result_sha256,
            result_inputs_sha256,
            result_identity,
        ),
        StageView(
            "manuscript_writing",
            "论文写作",
            "complete" if manuscripts else "unstarted",
            "已产出" if manuscripts else "未开始",
            f"writing 中有 {len(manuscripts)} 个 Markdown 稿件",
        ),
        StageView(
            "mock_review",
            "模拟审稿",
            "complete" if reviews else "unstarted",
            "已产出" if reviews else "未开始",
            f"reviews 中有 {len(reviews)} 个 Markdown 审稿产物",
        ),
    )

    if unknown_linked:
        invalid_ids = ", ".join(unknown_linked)
        next_action = NextAction(
            reason="课题关联了未登记、已移动或内容已改变的来源；校验证据账本不能修复来源关联。",
            target="project.yaml / library/sources.jsonl",
            command=(
                f"$paper-intake 修复 {slug} 的无效来源关联 {invalid_ids}："
                "重新登记当前公开文件；若属于误关联，经人工确认后从 project.yaml 移除"
            ),
            skill="paper-intake",
        )
    elif ledger_blocked:
        next_action = _blocked_action(slug, evidence_detail)
    elif not brief_ready:
        progress_hint = (
            "研究简报仍是空白模板"
            if brief_progress == "unstarted"
            else "研究简报已编辑但尚未通过质量门禁"
        )
        next_action = NextAction(
            reason=f"{progress_hint}，先把方向变成可证伪问题并完成人工确认。",
            target="00-research-brief.md",
            command=(
                f"$research-project-init 完善 projects/{slug}/"
                "00-research-brief.md，只使用公开资料"
            ),
            skill="research-project-init",
        )
    elif not manifest.source_ids:
        next_action = NextAction(
            reason="课题已有问题定义，但还没有显式关联任何来源。",
            target="project.yaml",
            command=f"$paper-intake 登记公开资料并关联 --project {slug}",
            skill="paper-intake",
        )
    elif not paper_card_count:
        next_action = NextAction(
            reason="来源已经登记，但尚无带定位的关联论文卡片。",
            target="library/papers/",
            command=(
                f"$paper-deep-read 精读 {slug} 的最高优先级全文，"
                "生成带 source_id 和页码定位的论文卡片"
            ),
            skill="paper-deep-read",
        )
    elif not claim_count or not literature_ready:
        next_action = NextAction(
            reason="已有论文卡片，但证据账本与跨论文综合尚未同时完成。",
            target="02-evidence-ledger.yaml / 03-literature-review.md",
            command=(
                f"$literature-synthesis 综合 {slug} 的关联论文卡片，"
                "同时记录支持、反对、冲突和研究空白"
            ),
            skill="literature-synthesis",
        )
    elif cycle_error:
        next_action = NextAction(
            reason="科研循环或 Idea 档案损坏，不能安全推进或自动修复。",
            target="cycles/ / ideas/archive.yaml",
            command=f"research-os doctor --workspace .  # 修复课题 {slug} 后重试",
            skill=None,
        )
    elif cycle_manifest is not None and cycle_manifest.state != "completed":
        if cycle_manifest.state == "awaiting_human_decision":
            next_action = NextAction(
                reason="三路独立评审与 meta-review 已完成，必须由研究者决定。",
                target="ideas/archive.yaml",
                command=(
                    f"research-os approve-idea --project {slug} "
                    '--idea IDEA_ID --reason "你的人工判断"'
                ),
                skill=None,
            )
        else:
            next_action = NextAction(
                reason="已有未完成的可恢复科研循环，应只执行其当前阶段。",
                target=f"cycles/{cycle_manifest.run_id}/work-packet.md",
                command=(
                    f"$research-cycle 推进 {slug} 的 {cycle_manifest.run_id}，"
                    "只处理工作包指定阶段"
                ),
                skill="research-cycle",
            )
    elif not idea_ready:
        next_action = NextAction(
            reason="证据基础已经形成，下一步启动有预算、可恢复的结构化 Idea 循环。",
            target="cycles/",
            command=f"research-os cycle --project {slug}",
            skill=None,
        )
    elif not design_ready:
        next_action = NextAction(
            reason="候选 Idea 已记录，需要把它转成可证伪、可复现的实验设计。",
            target="05-experiment-design.md",
            command=f"$experiment-advisor 为 {slug} 设计基线、消融、指标和失败判据，不执行实验",
            skill="experiment-advisor",
        )
    elif not result_inputs:
        next_action = NextAction(
            reason="实验设计已经形成；Research OS 不执行实验，当前应等待外部聚合结果。",
            target="artifacts/",
            command=(
                "请在独立实验仓库执行并复核实验，再把公开或脱敏的聚合结果"
                f"放入 projects/{slug}/artifacts/"
            ),
            skill=None,
        )
    elif not result_ready:
        next_action = NextAction(
            reason="已发现外部实验结果，但尚未检查它能支持和不能支持的结论。",
            target="06-result-analysis.md",
            command=f"$result-interpreter 保守解读 {slug} 的聚合结果并记录负结果与越界结论",
            skill="result-interpreter",
        )
    elif not manuscripts:
        next_action = NextAction(
            reason="结果解读已完成，可以从核验证据开始搭建稿件。",
            target="writing/",
            command=f"$manuscript-assistant 基于 {slug} 的核验证据生成论文大纲并标记引用缺口",
            skill="manuscript-assistant",
        )
    elif not reviews:
        next_action = NextAction(
            reason="已有稿件但尚无独立审稿记录。",
            target="reviews/",
            command=f"$mock-reviewer 从方法、统计、复现和医疗安全角度严格审查 {slug}",
            skill="mock-reviewer",
        )
    else:
        next_action = NextAction(
            reason="主要阶段均已有产物，回到证据变化和优先级复盘。",
            target="projects/" + slug,
            command=f"$research-weekly-review 复盘 {slug} 并只给三个下周行动",
            skill="research-weekly-review",
        )
    method_references: tuple[KnowledgeRecommendation, ...] = ()
    knowledge_issue = ""
    knowledge_root = library_root / "knowledge"
    if knowledge_root.exists() or _is_link_or_reparse_point(knowledge_root):
        try:
            method_references = recommend_for_project(
                workspace,
                slug,
                stage=_knowledge_stage(next_action),
                expected_project_identity=project_identity,
            )
        except (OSError, UnicodeError, ValueError) as exc:
            knowledge_issue = (
                f"方法学知识库受阻：{exc}。运行 research-os kb doctor --workspace ."
            )
    report = GuideReport(
        manifest.title,
        manifest.slug,
        stages,
        next_action,
        method_references,
        knowledge_issue,
    )
    assert_directory_identity(project_path, project_identity, context="project")
    return report


def render_guide(report: GuideReport) -> str:
    lines = [
        f"# {report.title} · 科研驾驶舱",
        "",
        "| 阶段 | 状态 | 说明 |",
        "|---|---|---|",
    ]
    lines.extend(
        f"| {stage.name} | {stage.status} | {stage.detail} |"
        for stage in report.stages
    )
    lines.extend(
        [
            "",
            "## 方法学参考",
            "",
            (
                report.knowledge_issue
                if report.knowledge_issue
                else "全局知识条目只是方法学线索，不会自动成为当前课题引用证据。"
            ),
            "",
        ]
        if report.method_references or report.knowledge_issue
        else []
    )
    for reference in report.method_references:
        identity = f"（`{reference.source_id}`）" if reference.source_id else ""
        lines.extend(
            [
                f"- **{reference.title}**{identity}：{reference.reason}",
                f"  核验范围：{reference.verification_scope}；边界：{reference.cannot_use_for}",
            ]
        )
    lines.extend(
        [
            "",
            "## 下一步",
            "",
            f"原因：{report.next_action.reason}",
            "",
            f"目标：`{report.next_action.target}`",
            "",
            "```text",
            report.next_action.command,
            "```",
            "",
        ]
    )
    return "\n".join(lines)
