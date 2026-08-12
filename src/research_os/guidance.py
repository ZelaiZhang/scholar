from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from research_os.evidence import load_ledger, validate_ledger
from research_os.project import load_project_manifest, template_content
from research_os.sources import SourceRegistry


@dataclass(frozen=True)
class StageView:
    name: str
    status: str
    detail: str


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


def _normalized(text: str) -> str:
    return text.replace("\r\n", "\n").strip()


def _matches_template(
    project_path: Path,
    filename: str,
    template_name: str,
    title: str,
) -> bool:
    path = project_path / filename
    if not path.is_file():
        return False
    expected = template_content(template_name, None).replace(
        "{{PROJECT_TITLE}}", title
    )
    return _normalized(path.read_text(encoding="utf-8")) == _normalized(expected)


def _linked_paper_card_count(workspace: Path, source_ids: tuple[str, ...]) -> int:
    papers_root = workspace / "library" / "papers"
    if not source_ids or not papers_root.is_dir():
        return 0
    count = 0
    for path in papers_root.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        if any(source_id in text for source_id in source_ids):
            count += 1
    return count


def _result_inputs(project_path: Path) -> tuple[Path, ...]:
    artifacts = project_path / "artifacts"
    if not artifacts.is_dir():
        return ()
    inputs: list[Path] = []
    for path in artifacts.rglob("*"):
        if not path.is_file() or path.name == ".gitkeep":
            continue
        lowered = path.name.lower()
        if lowered.endswith(".provenance.json") or lowered.startswith(
            ("evidence-check", "evidence-validation")
        ):
            continue
        inputs.append(path)
    return tuple(sorted(inputs))


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


def guide_project(workspace: Path, slug: str) -> GuideReport:
    workspace = workspace.resolve()
    project_path = workspace / "projects" / slug
    if not project_path.is_dir():
        raise FileNotFoundError(f"课题不存在: {project_path}")
    manifest = load_project_manifest(project_path, allow_legacy=True)
    registry = SourceRegistry(workspace / "library" / "sources.jsonl")
    known_source_ids = registry.verified_source_ids()
    unknown_linked = [
        source_id
        for source_id in manifest.source_ids
        if source_id not in known_source_ids
    ]

    ledger_error = ""
    ledger: dict[str, object] = {"claims": []}
    ledger_issues = []
    try:
        ledger = load_ledger(project_path / "02-evidence-ledger.yaml")
        ledger_issues = validate_ledger(
            ledger, known_source_ids=known_source_ids
        )
    except (OSError, ValueError) as exc:
        ledger_error = str(exc)

    brief_ready = not _matches_template(
        project_path, "00-research-brief.md", "research-brief.md", manifest.title
    )
    paper_card_count = _linked_paper_card_count(
        workspace, manifest.source_ids
    )
    raw_claims = ledger.get("claims", [])
    claim_count = len(raw_claims) if isinstance(raw_claims, list) else 0
    literature_ready = not _matches_template(
        project_path,
        "03-literature-review.md",
        "literature-review.md",
        manifest.title,
    )
    idea_ready = not _matches_template(
        project_path, "04-idea-candidates.md", "idea-candidates.md", manifest.title
    )
    design_ready = not _matches_template(
        project_path,
        "05-experiment-design.md",
        "experiment-design.md",
        manifest.title,
    )
    result_ready = not _matches_template(
        project_path, "06-result-analysis.md", "result-analysis.md", manifest.title
    )
    result_inputs = _result_inputs(project_path)
    manuscripts = _markdown_outputs(project_path / "writing")
    reviews = _markdown_outputs(project_path / "reviews")

    evidence_blocked = bool(ledger_error or ledger_issues or unknown_linked)
    if ledger_error:
        evidence_detail = f"账本无法读取：{ledger_error}"
    elif unknown_linked:
        evidence_detail = f"课题关联了无效或已漂移来源：{', '.join(unknown_linked)}"
    elif ledger_issues:
        evidence_detail = f"证据账本有 {len(ledger_issues)} 项校验问题"
    elif claim_count and literature_ready:
        evidence_detail = f"{claim_count} 条 claim，文献综合已编辑"
    elif claim_count or literature_ready:
        evidence_detail = "证据账本与文献综合尚未同时完成"
    else:
        evidence_detail = "尚未形成证据 claim 和文献综合"

    if evidence_blocked:
        synthesis_status = "受阻"
    elif claim_count and literature_ready:
        synthesis_status = "已产出"
    elif claim_count or literature_ready:
        synthesis_status = "进行中"
    else:
        synthesis_status = "未开始"

    if unknown_linked:
        intake_status = "受阻"
        intake_detail = f"{len(unknown_linked)} 个关联来源无效或内容已改变"
    elif manifest.source_ids:
        intake_status = "已产出"
        intake_detail = f"已显式关联 {len(manifest.source_ids)} 个来源"
    else:
        intake_status = "未开始"
        intake_detail = "尚未为本课题关联来源"

    if not result_inputs:
        result_status = "未开始"
        result_detail = "等待独立实验仓库的聚合结果"
    elif result_ready:
        result_status = "已产出"
        result_detail = f"已导入 {len(result_inputs)} 个结果文件并完成解读"
    else:
        result_status = "进行中"
        result_detail = f"已导入 {len(result_inputs)} 个结果文件，尚未解读"

    stages = (
        StageView(
            "课题定义",
            "已产出" if brief_ready else "未开始",
            "研究简报已编辑" if brief_ready else "仍是空白模板",
        ),
        StageView("资料导入", intake_status, intake_detail),
        StageView(
            "论文精读",
            "已产出" if paper_card_count else "未开始",
            f"找到 {paper_card_count} 张关联论文卡片",
        ),
        StageView("文献综合", synthesis_status, evidence_detail),
        StageView(
            "Idea 审查",
            "已产出" if idea_ready else "未开始",
            "候选与反向审查已编辑" if idea_ready else "仍是空白模板",
        ),
        StageView(
            "实验设计",
            "已产出" if design_ready else "未开始",
            "设计文档已编辑" if design_ready else "仍是空白模板",
        ),
        StageView("结果解读", result_status, result_detail),
        StageView(
            "论文写作",
            "已产出" if manuscripts else "未开始",
            f"writing 中有 {len(manuscripts)} 个 Markdown 稿件",
        ),
        StageView(
            "模拟审稿",
            "已产出" if reviews else "未开始",
            f"reviews 中有 {len(reviews)} 个 Markdown 审稿产物",
        ),
    )

    if evidence_blocked:
        next_action = _blocked_action(slug, evidence_detail)
    elif not brief_ready:
        next_action = NextAction(
            reason="研究简报仍是空白模板，先把模糊方向变成可证伪问题。",
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
    elif not idea_ready:
        next_action = NextAction(
            reason="证据基础已经形成，下一步应审查候选创新而不是直接定题。",
            target="04-idea-candidates.md",
            command=f"$idea-review 基于 {slug} 的核验证据生成并反向审查候选 Idea",
            skill="idea-review",
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
    return GuideReport(manifest.title, manifest.slug, stages, next_action)


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
