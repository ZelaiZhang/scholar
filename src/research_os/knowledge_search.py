from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from research_os.knowledge import (
    METHODS,
    PRIORITIES,
    STAGES,
    TOPICS,
    CatalogEntry,
    KnowledgeBase,
)


@dataclass(frozen=True)
class SearchFilters:
    topic: str = ""
    method: str = ""
    stage: str = ""
    priority: str = ""
    verified_scope: str = ""
    include_history: bool = False


@dataclass(frozen=True)
class SearchResult:
    entry: CatalogEntry
    score: int
    matched_fields: tuple[str, ...]


def _is_cjk(character: str) -> bool:
    codepoint = ord(character)
    return any(
        lower <= codepoint <= upper
        for lower, upper in (
            (0x3400, 0x4DBF),
            (0x4E00, 0x9FFF),
            (0xF900, 0xFAFF),
            (0x3040, 0x30FF),
            (0xAC00, 0xD7AF),
        )
    )


def _segment_tokens(segment: str) -> set[str]:
    tokens: set[str] = set()
    start = 0
    while start < len(segment):
        cjk = _is_cjk(segment[start])
        end = start + 1
        while end < len(segment) and _is_cjk(segment[end]) == cjk:
            end += 1
        run = segment[start:end]
        if cjk:
            tokens.add(run)
            if len(run) > 1:
                tokens.update(run[index : index + 2] for index in range(len(run) - 1))
        else:
            tokens.add(run)
        start = end
    return tokens


def _tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    tokens: set[str] = set()
    for segment in re.findall(r"[^\W_]+", normalized, flags=re.UNICODE):
        tokens.update(_segment_tokens(segment))
    return tokens


def _field_score(
    query_tokens: set[str], value: str, weight: int
) -> tuple[int, bool]:
    matches = query_tokens & _tokens(value)
    return len(matches) * weight, bool(matches)


def _validate_filters(filters: SearchFilters) -> None:
    checks = (
        ("topic", filters.topic, TOPICS),
        ("method", filters.method, METHODS),
        ("stage", filters.stage, STAGES),
        ("priority", filters.priority, PRIORITIES),
        ("verified_scope", filters.verified_scope, {"metadata", "abstract", "fulltext"}),
    )
    for name, value, allowed in checks:
        if value and value not in allowed:
            raise ValueError(f"{name} 使用未受控值: {value}")
    if not isinstance(filters.include_history, bool):
        raise ValueError("include_history 必须是布尔值")


def _matches_filters(entry: CatalogEntry, filters: SearchFilters) -> bool:
    if not filters.include_history and entry.status != "active":
        return False
    if filters.topic and filters.topic not in entry.topics:
        return False
    if filters.method and filters.method not in entry.methods:
        return False
    if filters.stage and filters.stage not in entry.stages:
        return False
    if filters.priority and filters.priority != entry.priority:
        return False
    if filters.verified_scope:
        if getattr(entry.verification, filters.verified_scope) != "verified":
            return False
    return True


def _alias_terms(kb: KnowledgeBase, entry: CatalogEntry) -> tuple[str, ...]:
    keys = {
        entry.source_id.casefold(),
        entry.canonical.casefold(),
        entry.title.casefold(),
        *(value.casefold() for value in entry.topics),
        *(value.casefold() for value in entry.methods),
        *(value.casefold() for value in entry.stages),
    }
    terms: list[str] = []
    for key in sorted(keys):
        terms.extend(kb.aliases.get(key, ()))
    return tuple(terms)


def _score_entry(
    kb: KnowledgeBase, entry: CatalogEntry, query_tokens: set[str]
) -> SearchResult:
    score = 0
    matched_fields: list[str] = []

    fields = (
        ("title", entry.title, 8),
        ("alias", " ".join(_alias_terms(kb, entry)), 6),
        ("topic", " ".join(entry.topics), 5),
        ("method", " ".join(entry.methods), 4),
        ("stage", " ".join(entry.stages), 3),
    )
    for name, value, weight in fields:
        increment, matched = _field_score(query_tokens, value, weight)
        score += increment
        if matched:
            matched_fields.append(name)

    card = kb.cards.get(entry.source_id)
    if card is not None:
        heading_score, heading_match = _field_score(
            query_tokens, " ".join(card.headings), 2
        )
        score += heading_score
        if heading_match:
            matched_fields.append("card-heading")
        prose = re.sub(r"(?m)^#{1,6}\s+.*$", "", card.body)
        body_score, body_match = _field_score(query_tokens, prose, 1)
        score += body_score
        if body_match:
            matched_fields.append("card-body")

    return SearchResult(
        entry=entry,
        score=score,
        matched_fields=tuple(matched_fields),
    )


def search_knowledge(
    kb: KnowledgeBase,
    query: str,
    *,
    filters: SearchFilters = SearchFilters(),
    limit: int = 10,
) -> tuple[SearchResult, ...]:
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("limit 必须是 1-50 的整数")
    if not isinstance(query, str):
        raise ValueError("query 必须是字符串")
    _validate_filters(filters)
    query_tokens = _tokens(query)
    results: list[SearchResult] = []
    for entry in kb.entries:
        if not _matches_filters(entry, filters):
            continue
        result = _score_entry(kb, entry, query_tokens)
        if query_tokens and result.score == 0:
            continue
        results.append(result)
    priority_rank = {"core": 0, "background": 1, "watch": 2}
    verification_rank = {"verified": 0, "unverified": 1, "unavailable": 2}
    results.sort(
        key=lambda result: (
            -result.score,
            priority_rank[result.entry.priority],
            verification_rank[result.entry.verification.fulltext],
            -result.entry.year,
            result.entry.source_id,
        )
    )
    return tuple(results[:limit])
