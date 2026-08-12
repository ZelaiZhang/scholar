from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from research_os.knowledge import (
    PROFILE_TRACKS,
    REPORTING_CONTEXTS,
    STAGES,
    CatalogEntry,
    KnowledgeBase,
    KnowledgeProfile,
    load_knowledge_base,
    load_profile,
)
from research_os.project import (
    _is_link_or_reparse_point,
    resolve_project_path,
)


@dataclass(frozen=True)
class KnowledgeRecommendation:
    kind: str
    title: str
    source_id: str
    reason: str
    verification_scope: str
    can_use_for: str
    cannot_use_for: str
    path: Path | None


def _verification_scope(entry: CatalogEntry) -> str:
    if entry.verification.fulltext == "verified":
        return "fulltext"
    if entry.verification.abstract == "verified":
        return "abstract"
    if entry.verification.metadata == "verified":
        return "metadata"
    return "unverified"


def _entry_recommendation(
    entry: CatalogEntry,
    *,
    kind: str,
    reason: str,
) -> KnowledgeRecommendation:
    return KnowledgeRecommendation(
        kind=kind,
        title=entry.title,
        source_id=entry.source_id,
        reason=reason,
        verification_scope=_verification_scope(entry),
        can_use_for="方法选择、评价边界和下一轮原文核验的线索。",
        cannot_use_for=(
            "不能自动成为当前课题的引用证据；必须先用 paper-intake 显式关联，"
            "并按阅读范围核验原文。"
        ),
        path=None,
    )


def _method_score(
    entry: CatalogEntry,
    profile: KnowledgeProfile | None,
    stage: str,
) -> int:
    score = 3 if stage in entry.stages else 0
    if entry.priority == "core":
        score += 4
    elif entry.priority == "background":
        score += 2
    if profile is None:
        if "evaluation" in entry.topics:
            score += 2
        return score
    score += 5 * len(set(profile.domains) & set(entry.topics))
    score += 4 * len(set(profile.tracks) & (set(entry.topics) | set(entry.methods)))
    if "medical-ai" in profile.domains and "medical-ai" in entry.topics:
        score += 3
    return score


def _select_method_source(
    kb: KnowledgeBase,
    profile: KnowledgeProfile | None,
    stage: str,
) -> CatalogEntry | None:
    candidates = [
        entry
        for entry in kb.entries
        if entry.status == "active"
        and entry.priority != "watch"
        and entry.verification.metadata == "verified"
        and "reporting-guideline" not in entry.methods
        and stage in entry.stages
    ]
    candidates.sort(
        key=lambda entry: (
            -_method_score(entry, profile, stage),
            0 if entry.priority == "core" else 1,
            0 if entry.verification.fulltext == "verified" else 1,
            -entry.year,
            entry.source_id,
        )
    )
    return candidates[0] if candidates else None


def _safe_playbook(kb: KnowledgeBase, filename: str) -> Path | None:
    root = kb.root / "playbooks"
    if not root.is_dir() or _is_link_or_reparse_point(root):
        return None
    path = root / filename
    if _is_link_or_reparse_point(path) or not path.is_file():
        return None
    if path.resolve().parent != root.resolve():
        raise ValueError(f"方法手册路径越出知识库: {path}")
    return path


def _select_playbook(
    kb: KnowledgeBase, profile: KnowledgeProfile | None
) -> KnowledgeRecommendation | None:
    if profile is not None and "medical-ai" in profile.domains:
        filename = "medical-ai-study.md"
        title = "医疗 AI 研究方法手册"
        reason = "课题画像包含 medical-ai，优先检查临床目标、偏倚、外部验证和安全边界。"
    elif profile is not None and set(profile.tracks) & {
        "finetuning",
        "quantization",
        "preference-optimization",
    }:
        filename = "llm-adaptation-study.md"
        title = "大模型适配研究方法手册"
        reason = "课题画像包含模型适配方向，优先核对参数效率、基线和资源约束。"
    else:
        filename = "evaluation-and-ablation.md"
        title = "评价与消融方法手册"
        reason = "当前画像不足或属于通用方法研究，先使用可复核的评价与消融清单。"
    path = _safe_playbook(kb, filename)
    if path is None:
        return None
    return KnowledgeRecommendation(
        kind="playbook",
        title=title,
        source_id="",
        reason=reason,
        verification_scope="operational-playbook",
        can_use_for="把方法规范转换成实验设计和审查问题。",
        cannot_use_for="手册是操作映射，不是论文证据，也不能证明临床有效性。",
        path=path,
    )


def _load_applicability(kb: KnowledgeBase) -> dict[str, tuple[str, ...]]:
    path = kb.root / "reporting-guidelines" / "applicability.yaml"
    if not path.exists():
        return {}
    if _is_link_or_reparse_point(path) or not path.is_file():
        raise ValueError(f"报告规范适用性矩阵不能是链接或目录: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"报告规范适用性矩阵无法解析: {path}") from exc
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "contexts"}:
        raise ValueError("报告规范适用性矩阵字段必须为 schema_version 和 contexts")
    if raw["schema_version"] != 1 or not isinstance(raw["contexts"], list):
        raise ValueError("报告规范适用性矩阵 schema_version/contexts 无效")
    known = {entry.source_id for entry in kb.entries}
    result: dict[str, tuple[str, ...]] = {}
    for index, value in enumerate(raw["contexts"]):
        if not isinstance(value, dict) or set(value) != {
            "context",
            "guideline_source_ids",
            "notes",
        }:
            raise ValueError(f"报告规范适用性矩阵 contexts[{index}] 字段无效")
        context = value["context"]
        source_ids = value["guideline_source_ids"]
        notes = value["notes"]
        if context not in REPORTING_CONTEXTS:
            raise ValueError(f"报告规范 context 未受控: {context}")
        if context in result:
            raise ValueError(f"报告规范 context 重复: {context}")
        if not isinstance(source_ids, list) or not source_ids or not all(
            isinstance(source_id, str) and source_id in known for source_id in source_ids
        ):
            raise ValueError(f"报告规范 source_id 无效: {context}")
        if len(set(source_ids)) != len(source_ids):
            raise ValueError(f"报告规范 source_id 重复: {context}")
        if not isinstance(notes, str) or not notes.strip():
            raise ValueError(f"报告规范 notes 不能为空: {context}")
        result[context] = tuple(source_ids)
    return result


def _select_reporting_guideline(
    kb: KnowledgeBase, profile: KnowledgeProfile | None
) -> KnowledgeRecommendation | None:
    if profile is None:
        return None
    applicability = _load_applicability(kb)
    entries = {entry.source_id: entry for entry in kb.entries}
    for context in profile.reporting_context:
        for source_id in applicability.get(context, ()):
            entry = entries[source_id]
            if (
                entry.status == "active"
                and entry.priority != "watch"
                and entry.verification.metadata == "verified"
            ):
                return _entry_recommendation(
                    entry,
                    kind="reporting-guideline",
                    reason=f"课题画像声明 {context}，应核对该规范的适用范围和当前版本。",
                )
    return None


def recommend_for_project(
    workspace: Path,
    slug: str,
    *,
    stage: str,
) -> tuple[KnowledgeRecommendation, ...]:
    if stage not in STAGES:
        raise ValueError(f"知识推荐 stage 未受控: {stage}")
    project = resolve_project_path(workspace, slug, require_exists=True)
    kb = load_knowledge_base(workspace)
    profile_path = project / "knowledge-profile.yaml"
    profile = load_profile(profile_path) if profile_path.exists() else None
    recommendations: list[KnowledgeRecommendation] = []
    method = _select_method_source(kb, profile, stage)
    if method is not None:
        recommendations.append(
            _entry_recommendation(
                method,
                kind="method-source",
                reason=f"该核心方法来源与当前 {stage} 阶段和课题画像匹配。",
            )
        )
    playbook = _select_playbook(kb, profile)
    if playbook is not None:
        recommendations.append(playbook)
    reporting = _select_reporting_guideline(kb, profile)
    if reporting is not None:
        recommendations.append(reporting)
    if profile is None:
        recommendations = recommendations[:2]
        recommendations.append(
            KnowledgeRecommendation(
                kind="profile-hint",
                title="补充课题知识画像",
                source_id="",
                reason=(
                    "当前课题没有 knowledge-profile.yaml；补充受控画像后，"
                    "kb recommend 才能给出医疗场景和报告规范建议。"
                ),
                verification_scope="not-evidence",
                can_use_for="提高后续方法学推荐的相关性。",
                cannot_use_for="不会从研究简报自由文本猜测医疗场景，也不会自动修改课题。",
                path=None,
            )
        )
    return tuple(recommendations[:3])
