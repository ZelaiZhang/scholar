from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from research_os.knowledge import (
    CatalogEntry,
    KnowledgeBase,
    KnowledgeCard,
    VerificationScope,
)
from research_os.knowledge_gaps import GapFilters, find_knowledge_gaps


def _entry(
    index: int,
    *,
    priority: str = "core",
    status: str = "active",
    metadata: str = "verified",
    abstract: str = "verified",
    fulltext: str = "verified",
    reviewed_at: str = "2026-08-12",
    topics: tuple[str, ...] = ("medical-ai",),
    methods: tuple[str, ...] = ("model-evaluation",),
) -> CatalogEntry:
    source_id = f"src-{index:016x}"
    return CatalogEntry(
        source_id=source_id,
        canonical=f"10.1000/gap-{index}",
        title=f"Knowledge source {index}",
        authors=("Methods Group",),
        year=2025,
        source_type="paper",
        venue="Methods Journal",
        topics=topics,
        methods=methods,
        stages=("literature-search",),
        priority=priority,
        verification=VerificationScope(
            metadata=metadata,
            abstract=abstract,
            fulltext=fulltext,
        ),
        reviewed_at=reviewed_at,
        status=status,
        superseded_by="",
        access_url=f"https://example.org/{index}",
        license="unknown",
        notes="",
    )


def _card(entry: CatalogEntry, scope: str = "fulltext") -> KnowledgeCard:
    locator = "abstract" if scope == "abstract" else "Results"
    return KnowledgeCard(
        schema_version=1,
        source_id=entry.source_id,
        title=entry.title,
        reading_scope=scope,
        locators=(locator,),
        reviewed_at=entry.reviewed_at,
        headings=("已报告事实",),
        body="",
        path=Path(f"{entry.source_id}.md"),
    )


def _knowledge_base(
    entries: tuple[CatalogEntry, ...], cards: dict[str, KnowledgeCard]
) -> KnowledgeBase:
    return KnowledgeBase(
        root=Path("knowledge"), entries=entries, cards=cards, aliases={}
    )


def test_gap_queue_classifies_six_actionable_maintenance_kinds() -> None:
    watch = _entry(1, priority="watch")
    metadata = _entry(
        2,
        metadata="unverified",
        abstract="unverified",
        fulltext="unavailable",
    )
    missing = _entry(3, fulltext="unavailable")
    abstract = _entry(4, abstract="unverified", fulltext="unavailable")
    upgrade = _entry(5, fulltext="unverified")
    stale = _entry(6, reviewed_at="2024-01-01")
    kb = _knowledge_base(
        (stale, upgrade, abstract, missing, metadata, watch),
        {
            watch.source_id: _card(watch),
            upgrade.source_id: _card(upgrade, "abstract"),
            stale.source_id: _card(stale),
        },
    )

    gaps = find_knowledge_gaps(kb, as_of=date(2026, 8, 12))

    assert [gap.kind for gap in gaps] == [
        "watch-review",
        "metadata-review",
        "missing-card",
        "abstract-review",
        "fulltext-upgrade",
        "stale-review",
    ]
    assert len({(gap.kind, gap.source_id) for gap in gaps}) == len(gaps)
    assert all(gap.source_id.startswith("src-") for gap in gaps)
    assert all(gap.reason and gap.next_action and gap.access_url for gap in gaps)


def test_gap_queue_filters_topic_method_and_kind_without_mutating_kb() -> None:
    medical = _entry(
        1,
        fulltext="unverified",
        topics=("medical-ai",),
        methods=("model-evaluation",),
    )
    rag = _entry(
        2,
        fulltext="unverified",
        topics=("rag-and-evidence",),
        methods=("rag",),
    )
    cards = {
        medical.source_id: _card(medical, "abstract"),
        rag.source_id: _card(rag, "abstract"),
    }
    kb = _knowledge_base((rag, medical), cards)
    before = (kb.entries, dict(kb.cards), dict(kb.aliases))

    gaps = find_knowledge_gaps(
        kb,
        as_of=date(2026, 8, 12),
        filters=GapFilters(
            topic="medical-ai",
            method="model-evaluation",
            kind="fulltext-upgrade",
        ),
    )

    assert [(gap.kind, gap.source_id) for gap in gaps] == [
        ("fulltext-upgrade", medical.source_id)
    ]
    assert (kb.entries, dict(kb.cards), dict(kb.aliases)) == before


def test_gap_queue_ties_use_catalog_priority_oldest_date_then_source_id() -> None:
    background = _entry(
        1, priority="background", fulltext="unverified", reviewed_at="2024-01-01"
    )
    core_new = _entry(2, fulltext="unverified", reviewed_at="2025-01-01")
    core_old_high_id = _entry(4, fulltext="unverified", reviewed_at="2024-01-01")
    core_old_low_id = _entry(3, fulltext="unverified", reviewed_at="2024-01-01")
    entries = (background, core_new, core_old_high_id, core_old_low_id)
    kb = _knowledge_base(
        entries,
        {entry.source_id: _card(entry, "abstract") for entry in entries},
    )

    gaps = find_knowledge_gaps(
        kb,
        as_of=date(2026, 8, 12),
        filters=GapFilters(kind="fulltext-upgrade"),
    )

    assert [gap.source_id for gap in gaps] == [
        core_old_low_id.source_id,
        core_old_high_id.source_id,
        core_new.source_id,
        background.source_id,
    ]


def test_gap_queue_validates_filters_limit_and_date() -> None:
    entry = _entry(1, fulltext="unverified")
    kb = _knowledge_base((entry,), {entry.source_id: _card(entry, "abstract")})

    with pytest.raises(ValueError, match="topic"):
        find_knowledge_gaps(
            kb,
            as_of=date(2026, 8, 12),
            filters=GapFilters(topic="not-controlled"),
        )
    with pytest.raises(ValueError, match="kind"):
        find_knowledge_gaps(
            kb,
            as_of=date(2026, 8, 12),
            filters=GapFilters(kind="invented"),
        )
    with pytest.raises(ValueError, match="limit"):
        find_knowledge_gaps(kb, as_of=date(2026, 8, 12), limit=0)
    with pytest.raises(ValueError, match="as_of"):
        find_knowledge_gaps(kb, as_of="2026-08-12")  # type: ignore[arg-type]


def test_gap_queue_ignores_non_active_history_entries() -> None:
    retracted = _entry(1, status="retracted", fulltext="unverified")
    superseded = _entry(2, status="superseded", fulltext="unverified")
    inaccessible = _entry(3, status="inaccessible", fulltext="unverified")
    entries = (retracted, superseded, inaccessible)
    kb = _knowledge_base(
        entries,
        {entry.source_id: _card(entry, "abstract") for entry in entries},
    )

    assert find_knowledge_gaps(kb, as_of=date(2026, 8, 12)) == ()
