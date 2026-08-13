from dataclasses import FrozenInstanceError

import pytest

from research_os.manuscript_markup import (
    ManuscriptAnnotation,
    MarkupIssue,
    ManuscriptBlock,
    parse_annotation,
    parse_manuscript,
)


def test_parses_strict_fact_annotation() -> None:
    annotation = parse_annotation(
        "<!-- research-os:kind=fact; claims=SRC-1:claim.2,ledger_3 -->",
        line=7,
    )

    assert annotation == ManuscriptAnnotation(
        kind="fact",
        claim_ids=("SRC-1:claim.2", "ledger_3"),
        idea_id="",
        artifact_names=(),
        line=7,
    )
    with pytest.raises(FrozenInstanceError):
        annotation.kind = "inference"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("comment", "kind", "idea_id", "artifact_names"),
    [
        (
            "<!-- research-os:kind=method; idea=idea-17 -->",
            "method",
            "idea-17",
            (),
        ),
        (
            "<!-- research-os:kind=result; artifacts=table_1.csv,figure-2.png -->",
            "result",
            "",
            ("table_1.csv", "figure-2.png"),
        ),
        (
            "<!-- research-os:kind=method;idea=idea-18 -->",
            "method",
            "idea-18",
            (),
        ),
    ],
)
def test_parses_kind_specific_annotation_fields(
    comment: str,
    kind: str,
    idea_id: str,
    artifact_names: tuple[str, ...],
) -> None:
    annotation = parse_annotation(comment, line=3)

    assert annotation.kind == kind
    assert annotation.claim_ids == ()
    assert annotation.idea_id == idea_id
    assert annotation.artifact_names == artifact_names
    assert annotation.line == 3


@pytest.mark.parametrize(
    "comment",
    [
        "<!-- research-os:kind=fact; claims=claim-1; claims=claim-2 -->",
        "<!-- research-os:kind=fact; claims=claim-1; idea=idea-1 -->",
        "<!-- research-os:kind=fact -->",
        "<!-- research-os:kind=method; claims=claim-1 -->",
        "<!-- research-os:kind=result; artifacts= -->",
        "<!-- research-os:kind=fact; claims=claim-1,claim-1 -->",
        "<!-- research-os:kind=fact; claims=-claim -->",
        "<!-- research-os:kind=fact; claims=claim 1 -->",
        "<!-- research-os:kind=fact; claims=claim-1 --> trailing",
        "prefix <!-- research-os:kind=fact; claims=claim-1 -->",
        "<!-- research-os:kind=unknown; claims=claim-1 -->",
    ],
)
def test_rejects_invalid_annotation_grammar(comment: str) -> None:
    assert parse_annotation(comment, line=2) is None


def test_parses_audited_blocks_without_retaining_manuscript_prose() -> None:
    parsed = parse_manuscript(
        "## Abstract\r\n"
        "<!-- research-os:kind=fact; claims=claim-1 -->\r\n"
        "First paragraph.\r\n"
        "\r\n"
        "- one\r\n"
        "- two\r\n"
        "\r\n"
        "> quoted\r\n"
        "> material\r\n"
        "\r\n"
        "| a | b |\r\n"
        "| - | - |\r\n"
        "| 1 | 2 |\r\n"
        "\r\n"
        "---\r\n"
        "\r\n"
        "## Background\r\n"
        "Ignored prose.\r\n"
        "\r\n"
        "## Introduction\r\n"
        "Introduction prose.\r\n"
    )

    assert parsed.blocks == (
        ManuscriptBlock(
            section="Abstract",
            block_index=1,
            line=3,
            annotation=ManuscriptAnnotation(
                kind="fact",
                claim_ids=("claim-1",),
                idea_id="",
                artifact_names=(),
                line=2,
            ),
        ),
        ManuscriptBlock("Abstract", 2, 5, None),
        ManuscriptBlock("Abstract", 3, 8, None),
        ManuscriptBlock("Abstract", 4, 11, None),
        ManuscriptBlock("Introduction", 1, 21, None),
    )
    assert parsed.section_occurrences == (("Abstract", 1), ("Introduction", 20))
    assert parsed.syntax_issues == ()
    assert not hasattr(parsed.blocks[0], "text")


def test_reports_invalid_second_annotation_without_leaking_comment_text() -> None:
    parsed = parse_manuscript(
        "## Results\n"
        "<!-- research-os:kind=result; artifacts=table-1.csv -->\n"
        "<!-- research-os:kind=fact; claims=claim-1 -->\n"
        "Reported result.\n"
    )

    assert parsed.blocks == (
        ManuscriptBlock(
            section="Results",
            block_index=1,
            line=4,
            annotation=ManuscriptAnnotation(
                kind="result",
                claim_ids=(),
                idea_id="",
                artifact_names=("table-1.csv",),
                line=2,
            ),
        ),
    )
    assert parsed.syntax_issues == (
        MarkupIssue("INVALID_ANNOTATION", "Results", 1, 3),
    )
    assert not hasattr(parsed.syntax_issues[0], "message")


def test_clears_pending_annotation_at_any_heading_and_records_orphan() -> None:
    parsed = parse_manuscript(
        "# Title\n"
        "## Abstract\n"
        "<!-- research-os:kind=hypothesis; claims=claim-1 -->\n"
        "### Aim\n"
        "Prose after a subheading.\n"
        "# New part\n"
        "More ignored prose.\n"
    )

    assert parsed.blocks == (
        ManuscriptBlock("Abstract", 1, 5, None),
        ManuscriptBlock("Abstract", 2, 7, None),
    )
    assert parsed.syntax_issues == (
        MarkupIssue("ORPHAN_ANNOTATION", "Abstract", 1, 3),
    )


def test_uses_only_exact_h2_names_and_records_duplicate_occurrences() -> None:
    parsed = parse_manuscript(
        "## Abstract \n"
        "Ignored because the heading is not exact.\n"
        "## Abstract\n"
        "One.\n"
        "## Abstract\n"
        "Two.\n"
        "### Results\n"
        "Still abstract.\n"
    )

    assert parsed.blocks == (
        ManuscriptBlock("Abstract", 1, 4, None),
        ManuscriptBlock("Abstract", 2, 6, None),
        ManuscriptBlock("Abstract", 3, 8, None),
    )
    assert parsed.section_occurrences == (("Abstract", 3), ("Abstract", 5))


def test_ignores_annotations_inside_fenced_code_and_orphans_at_end() -> None:
    parsed = parse_manuscript(
        "## Methods\n"
        "```markdown\n"
        "<!-- research-os:kind=method; idea=not-real -->\n"
        "code\n"
        "```\n"
        "<!-- research-os:kind=method; idea=idea-1 -->\n"
    )

    assert parsed.blocks == ()
    assert parsed.syntax_issues == (
        MarkupIssue("ORPHAN_ANNOTATION", "Methods", 1, 6),
    )
