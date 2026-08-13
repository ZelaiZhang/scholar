"""Strict, prose-free parsing helpers for Research OS manuscript markup."""

from __future__ import annotations

from dataclasses import dataclass
import re


SAFE_VALUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
ANNOTATION_ENVELOPE = re.compile(r"\A<!-- research-os:(?P<body>[^\r\n]+) -->\Z")
ANNOTATION_FIELDS = {
    "fact": frozenset({"kind", "claims"}),
    "inference": frozenset({"kind", "claims"}),
    "hypothesis": frozenset({"kind", "claims"}),
    "limitation": frozenset({"kind", "claims"}),
    "method": frozenset({"kind", "idea"}),
    "result": frozenset({"kind", "artifacts"}),
}
AUDITED_SECTIONS = frozenset(
    {
        "Abstract",
        "Introduction",
        "Related Work",
        "Methods",
        "Experiments",
        "Results",
        "Limitations and Ethics",
        "Conclusion",
    }
)
HEADING = re.compile(r"^(?P<level>#{1,6})[ \t]+(?P<title>.*)$")
FENCE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})")
HORIZONTAL_RULE = re.compile(
    r"^ {0,3}(?P<marker>[*_-])(?:[ \t]*(?P=marker)){2,}[ \t]*$"
)
HTML_COMMENT_START = re.compile(r"^[ \t]*<!--")


@dataclass(frozen=True)
class ManuscriptAnnotation:
    kind: str
    claim_ids: tuple[str, ...]
    idea_id: str
    artifact_names: tuple[str, ...]
    line: int


@dataclass(frozen=True)
class MarkupIssue:
    code: str
    section: str
    block_index: int
    line: int


@dataclass(frozen=True)
class ManuscriptBlock:
    section: str
    block_index: int
    line: int
    annotation: ManuscriptAnnotation | None


@dataclass(frozen=True)
class ParsedManuscript:
    blocks: tuple[ManuscriptBlock, ...]
    section_occurrences: tuple[tuple[str, int], ...]
    syntax_issues: tuple[MarkupIssue, ...]


def parse_annotation(comment: str, *, line: int) -> ManuscriptAnnotation | None:
    """Parse one exact annotation comment, returning ``None`` if it is invalid."""
    match = ANNOTATION_ENVELOPE.fullmatch(comment)
    if match is None:
        return None

    values: dict[str, str] = {}
    for field_index, field in enumerate(match.group("body").split(";")):
        if field_index and field.startswith(" "):
            field = field[1:]
        if field.count("=") != 1:
            return None
        key, value = field.split("=", 1)
        if not key or not value or key in values:
            return None
        values[key] = value

    kind = values.get("kind")
    if kind not in ANNOTATION_FIELDS or frozenset(values) != ANNOTATION_FIELDS[kind]:
        return None

    if kind in {"fact", "inference", "hypothesis", "limitation"}:
        claim_ids = _parse_values(values["claims"])
        if claim_ids is None:
            return None
        return ManuscriptAnnotation(kind, claim_ids, "", (), line)
    if kind == "method":
        idea_id = values["idea"]
        if SAFE_VALUE.fullmatch(idea_id) is None:
            return None
        return ManuscriptAnnotation(kind, (), idea_id, (), line)

    artifact_names = _parse_values(values["artifacts"])
    if artifact_names is None:
        return None
    return ManuscriptAnnotation(kind, (), "", artifact_names, line)


def _parse_values(value: str) -> tuple[str, ...] | None:
    values = tuple(value.split(","))
    if not values or len(values) != len(set(values)):
        return None
    if any(SAFE_VALUE.fullmatch(item) is None for item in values):
        return None
    return values


def parse_manuscript(markdown: str) -> ParsedManuscript:
    """Parse audited Markdown structure while retaining no manuscript prose."""
    blocks: list[ManuscriptBlock] = []
    occurrences: list[tuple[str, int]] = []
    issues: list[MarkupIssue] = []
    section: str | None = None
    pending: ManuscriptAnnotation | None = None
    pending_section = ""
    pending_index = 0
    in_block = False
    fence_marker: tuple[str, int] | None = None
    in_html_comment = False

    def next_block_index() -> int:
        if section is None:
            return 0
        return sum(block.section == section for block in blocks) + 1

    def orphan_pending() -> None:
        nonlocal pending
        if pending is not None:
            issues.append(
                MarkupIssue(
                    "ORPHAN_ANNOTATION",
                    pending_section,
                    pending_index,
                    pending.line,
                )
            )
            pending = None

    def close_block() -> None:
        nonlocal in_block
        in_block = False

    for line_number, raw_line in enumerate(markdown.splitlines(), start=1):
        ordinary_comment_prefix_stripped = False
        if in_html_comment:
            comment_end = raw_line.find("-->")
            if comment_end == -1:
                continue
            in_html_comment = False
            ordinary_comment_prefix_stripped = True
            raw_line = raw_line[comment_end + 3 :]
            if not raw_line.strip():
                continue

        fence_match = FENCE.match(raw_line)
        if fence_marker is not None:
            if fence_match is not None:
                marker = fence_match.group("marker")
                if (
                    marker[0] == fence_marker[0]
                    and len(marker) >= fence_marker[1]
                    and raw_line[fence_match.end() :].strip() == ""
                ):
                    fence_marker = None
            continue
        if fence_match is not None:
            close_block()
            marker = fence_match.group("marker")
            fence_marker = (marker[0], len(marker))
            continue

        heading_match = HEADING.fullmatch(raw_line)
        if heading_match is not None:
            close_block()
            orphan_pending()
            level = len(heading_match.group("level"))
            title = heading_match.group("title")
            if level == 2 and title in AUDITED_SECTIONS:
                section = title
                occurrences.append((title, line_number))
            elif level == 2:
                section = None
            continue

        if not raw_line.strip() or HORIZONTAL_RULE.fullmatch(raw_line) is not None:
            close_block()
            continue

        preceded_by_ordinary_comment = ordinary_comment_prefix_stripped
        while HTML_COMMENT_START.match(raw_line) is not None:
            is_research_annotation = raw_line.lstrip(" \t").startswith(
                "<!-- research-os:"
            )
            if is_research_annotation and not preceded_by_ordinary_comment:
                break
            comment_end = raw_line.find("-->")
            if comment_end == -1:
                in_html_comment = True
                raw_line = ""
                break
            preceded_by_ordinary_comment = True
            raw_line = raw_line[comment_end + 3 :]

        if not raw_line.strip():
            continue

        if raw_line.lstrip(" \t").startswith("<!-- research-os:"):
            is_multiline_comment = "-->" not in raw_line
            if section is None:
                if is_multiline_comment:
                    in_html_comment = True
                continue
            if in_block:
                issues.append(
                    MarkupIssue(
                        "INVALID_ANNOTATION",
                        section,
                        blocks[-1].block_index,
                        line_number,
                    )
                )
                if is_multiline_comment:
                    in_html_comment = True
                continue
            annotation = parse_annotation(raw_line, line=line_number)
            if annotation is None or pending is not None:
                issues.append(
                    MarkupIssue(
                        "INVALID_ANNOTATION", section, next_block_index(), line_number
                    )
                )
                if is_multiline_comment:
                    in_html_comment = True
                continue
            pending = annotation
            pending_section = section
            pending_index = next_block_index()
            continue

        if section is None:
            continue
        if not in_block:
            block_index = next_block_index()
            blocks.append(
                ManuscriptBlock(section, block_index, line_number, pending)
            )
            pending = None
            in_block = True

    orphan_pending()
    return ParsedManuscript(tuple(blocks), tuple(occurrences), tuple(issues))
