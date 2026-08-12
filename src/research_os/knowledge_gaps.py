from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from research_os.knowledge import METHODS, TOPICS, CatalogEntry, KnowledgeBase


GAP_KINDS = (
    "watch-review",
    "metadata-review",
    "missing-card",
    "abstract-review",
    "fulltext-upgrade",
    "stale-review",
)
_GAP_PRIORITY = {kind: index for index, kind in enumerate(GAP_KINDS, start=1)}
_CATALOG_PRIORITY = {"core": 0, "background": 1, "watch": 2}


@dataclass(frozen=True)
class GapFilters:
    topic: str = ""
    method: str = ""
    kind: str = ""


@dataclass(frozen=True)
class KnowledgeGap:
    kind: str
    source_id: str
    title: str
    priority: int
    reason: str
    next_action: str
    access_url: str


def _validate_inputs(filters: GapFilters, as_of: date, limit: int) -> None:
    if filters.topic and filters.topic not in TOPICS:
        raise ValueError(f"topic 使用未受控值: {filters.topic}")
    if filters.method and filters.method not in METHODS:
        raise ValueError(f"method 使用未受控值: {filters.method}")
    if filters.kind and filters.kind not in GAP_KINDS:
        raise ValueError(f"kind 使用未受控值: {filters.kind}")
    if not isinstance(as_of, date):
        raise ValueError("as_of 必须是日期")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit 必须是 1-100 的整数")


def _matches_filters(entry: CatalogEntry, filters: GapFilters) -> bool:
    if filters.topic and filters.topic not in entry.topics:
        return False
    if filters.method and filters.method not in entry.methods:
        return False
    return True


def _gap(
    entry: CatalogEntry, kind: str, reason: str, next_action: str
) -> KnowledgeGap:
    return KnowledgeGap(
        kind=kind,
        source_id=entry.source_id,
        title=entry.title,
        priority=_GAP_PRIORITY[kind],
        reason=reason,
        next_action=next_action,
        access_url=entry.access_url,
    )


def _entry_gaps(
    kb: KnowledgeBase, entry: CatalogEntry, as_of: date
) -> tuple[KnowledgeGap, ...]:
    gaps: list[KnowledgeGap] = []
    if entry.priority == "watch":
        gaps.append(
            _gap(
                entry,
                "watch-review",
                "该来源仍处于 watch，不能进入默认方法推荐。",
                "核对原文、版本和风险；确认后再人工调整 catalog priority。",
            )
        )

    card = kb.cards.get(entry.source_id)
    if entry.verification.metadata != "verified":
        gaps.append(
            _gap(
                entry,
                "metadata-review",
                "来源元数据尚未核验。",
                "$paper-intake 核对标题、作者、年份、canonical 和原文链接。",
            )
        )
    elif entry.verification.abstract != "verified":
        gaps.append(
            _gap(
                entry,
                "abstract-review",
                "摘要尚未核验，当前只能作为元数据线索。",
                "$paper-deep-read 核验摘要，只记录 abstract 明确报告的事实。",
            )
        )
    elif card is None:
        gaps.append(
            _gap(
                entry,
                "missing-card",
                "来源已核验摘要或全文，但尚无结构化知识卡。",
                f"$paper-deep-read 为 {entry.source_id} 生成逐事实带 locator 的知识卡。",
            )
        )
    elif entry.verification.fulltext == "unverified":
        gaps.append(
            _gap(
                entry,
                "fulltext-upgrade",
                "当前知识卡未达到全文核验范围。",
                "合法获取全文后使用 $paper-deep-read 升级 locator 和 fulltext 核验状态。",
            )
        )

    reviewed = date.fromisoformat(entry.reviewed_at)
    if (as_of - reviewed).days > 365:
        gaps.append(
            _gap(
                entry,
                "stale-review",
                f"来源自 {entry.reviewed_at} 起已超过 365 天未复核。",
                "重新访问原文，核对状态或替代版本，并人工更新 reviewed_at。",
            )
        )
    return tuple(gaps)


def find_knowledge_gaps(
    kb: KnowledgeBase,
    *,
    as_of: date,
    filters: GapFilters | None = None,
    limit: int = 100,
) -> tuple[KnowledgeGap, ...]:
    selected_filters = filters or GapFilters()
    _validate_inputs(selected_filters, as_of, limit)
    entries = {
        entry.source_id: entry
        for entry in kb.entries
        if entry.status == "active" and _matches_filters(entry, selected_filters)
    }
    gaps = [
        gap
        for entry in entries.values()
        for gap in _entry_gaps(kb, entry, as_of)
        if not selected_filters.kind or gap.kind == selected_filters.kind
    ]
    gaps.sort(
        key=lambda gap: (
            gap.priority,
            _CATALOG_PRIORITY[entries[gap.source_id].priority],
            entries[gap.source_id].reviewed_at,
            gap.source_id,
        )
    )
    return tuple(gaps[:limit])
