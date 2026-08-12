from __future__ import annotations

from pathlib import Path

from research_os.knowledge import (
    CatalogEntry,
    KnowledgeBase,
    KnowledgeCard,
    VerificationScope,
)
from research_os.knowledge_search import SearchFilters, search_knowledge


def _entry(
    source_id: str,
    *,
    title: str,
    topics: tuple[str, ...] = ("evaluation",),
    methods: tuple[str, ...] = ("model-evaluation",),
    stages: tuple[str, ...] = ("experiment-design",),
    priority: str = "background",
    fulltext: str = "unverified",
    year: int = 2025,
    status: str = "active",
) -> CatalogEntry:
    return CatalogEntry(
        source_id=source_id,
        canonical=f"10.1000/{source_id}",
        title=title,
        authors=("A. Researcher",),
        year=year,
        source_type="paper",
        venue="Test Venue",
        topics=topics,
        methods=methods,
        stages=stages,
        priority=priority,
        verification=VerificationScope(
            metadata="verified", abstract="verified", fulltext=fulltext
        ),
        reviewed_at="2026-08-12",
        status=status,
        superseded_by="",
        access_url="https://example.org/paper",
        license="unknown",
        notes="",
    )


def _card(source_id: str, body: str, headings: tuple[str, ...] = ()) -> KnowledgeCard:
    return KnowledgeCard(
        schema_version=1,
        source_id=source_id,
        title="Card",
        reading_scope="abstract",
        locators=("abstract",),
        reviewed_at="2026-08-12",
        headings=headings,
        body=body,
        path=Path(f"{source_id}.md"),
    )


def test_search_uses_title_alias_heading_and_body_weights() -> None:
    title = _entry("src-0000000000000001", title="Calibration in practice")
    alias = _entry("src-0000000000000002", title="Reliability study")
    heading = _entry("src-0000000000000003", title="Evaluation study")
    body = _entry("src-0000000000000004", title="Model study")
    kb = KnowledgeBase(
        root=Path("knowledge"),
        entries=(body, heading, alias, title),
        cards={
            heading.source_id: _card(
                heading.source_id,
                "## Calibration\n\nNo target term in prose.",
                headings=("Calibration",),
            ),
            body.source_id: _card(
                body.source_id,
                "The paper reports calibration limitations.",
            ),
        },
        aliases={alias.source_id: ("calibration",)},
    )

    results = search_knowledge(kb, "calibration", limit=10)

    assert [result.entry.source_id for result in results] == [
        title.source_id,
        alias.source_id,
        heading.source_id,
        body.source_id,
    ]
    assert [result.score for result in results] == [8, 6, 2, 1]


def test_search_topic_method_and_stage_filters_are_exact() -> None:
    match = _entry(
        "src-0000000000000001",
        title="Medical RAG",
        topics=("medical-ai",),
        methods=("rag",),
        stages=("evidence-synthesis",),
        priority="core",
        fulltext="verified",
    )
    other = _entry("src-0000000000000002", title="Other")
    kb = KnowledgeBase(
        root=Path("knowledge"), entries=(other, match), cards={}, aliases={}
    )

    results = search_knowledge(
        kb,
        "",
        filters=SearchFilters(
            topic="medical-ai",
            method="rag",
            stage="evidence-synthesis",
            priority="core",
            verified_scope="fulltext",
        ),
        limit=10,
    )

    assert [result.entry.source_id for result in results] == [match.source_id]


def test_search_excludes_retracted_and_superseded_unless_history_requested() -> None:
    retracted = _entry(
        "src-0000000000000001", title="Diagnosis", status="retracted"
    )
    superseded = _entry(
        "src-0000000000000002", title="Diagnosis", status="superseded"
    )
    kb = KnowledgeBase(
        root=Path("knowledge"),
        entries=(retracted, superseded),
        cards={},
        aliases={},
    )

    assert search_knowledge(kb, "diagnosis", limit=10) == ()
    history = search_knowledge(
        kb,
        "diagnosis",
        filters=SearchFilters(include_history=True),
        limit=10,
    )
    assert len(history) == 2


def test_search_ties_use_priority_scope_year_then_source_id() -> None:
    background = _entry(
        "src-0000000000000001", title="Shared", priority="background", year=2026
    )
    core_abstract = _entry(
        "src-0000000000000002", title="Shared", priority="core", year=2026
    )
    core_fulltext_old = _entry(
        "src-0000000000000003",
        title="Shared",
        priority="core",
        fulltext="verified",
        year=2024,
    )
    core_fulltext_new = _entry(
        "src-0000000000000004",
        title="Shared",
        priority="core",
        fulltext="verified",
        year=2025,
    )
    kb = KnowledgeBase(
        root=Path("knowledge"),
        entries=(background, core_abstract, core_fulltext_old, core_fulltext_new),
        cards={},
        aliases={},
    )

    results = search_knowledge(kb, "shared", limit=10)

    assert [result.entry.source_id for result in results] == [
        core_fulltext_new.source_id,
        core_fulltext_old.source_id,
        core_abstract.source_id,
        background.source_id,
    ]


def test_search_validates_limit_and_controlled_filters() -> None:
    entry = _entry("src-0000000000000001", title="Study")
    kb = KnowledgeBase(root=Path("knowledge"), entries=(entry,), cards={}, aliases={})

    import pytest

    with pytest.raises(ValueError, match="limit"):
        search_knowledge(kb, "study", limit=0)
    with pytest.raises(ValueError, match="topic"):
        search_knowledge(
            kb,
            "study",
            filters=SearchFilters(topic="not-controlled"),
            limit=10,
        )
