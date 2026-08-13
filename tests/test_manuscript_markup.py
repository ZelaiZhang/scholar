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


@pytest.mark.parametrize("kind", ["inference", "hypothesis", "limitation"])
def test_parses_each_claim_based_annotation_kind(kind: str) -> None:
    annotation = parse_annotation(
        f"<!-- research-os:kind={kind}; claims=claim-1 -->", line=11
    )

    assert annotation == ManuscriptAnnotation(
        kind=kind,
        claim_ids=("claim-1",),
        idea_id="",
        artifact_names=(),
        line=11,
    )


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


def test_only_matching_fence_with_sufficient_length_and_whitespace_closes() -> None:
    parsed = parse_manuscript(
        "## Methods\n"
        "````markdown\n"
        "<!-- research-os:kind=method; idea=inside-four-backticks -->\n"
        "```\n"
        "<!-- research-os:kind=method; idea=still-inside -->\n"
        "````not-a-close\n"
        "<!-- research-os:kind=method; idea=also-inside -->\n"
        "````  \n"
        "<!-- research-os:kind=method; idea=idea-1 -->\n"
        "Methods prose.\n"
        "~~~~\n"
        "<!-- research-os:kind=method; idea=inside-tilde -->\n"
        "~~~\n"
        "~~~~not-a-close\n"
        "~~~~\t\n"
        "Methods after tilde.\n"
    )

    assert parsed.blocks == (
        ManuscriptBlock(
            "Methods",
            1,
            10,
            ManuscriptAnnotation("method", (), "idea-1", (), 9),
        ),
        ManuscriptBlock("Methods", 2, 16, None),
    )
    assert parsed.syntax_issues == ()


def test_ordinary_html_comments_do_not_consume_pending_annotation() -> None:
    parsed = parse_manuscript(
        "## Results\n"
        "<!-- research-os:kind=result; artifacts=table-1.csv -->\n"
        "<!-- editorial note -->\n"
        "<!--\n"
        "multi-line editorial note -->\n"
        "Reported result.\n"
    )

    assert parsed.blocks == (
        ManuscriptBlock(
            "Results",
            1,
            6,
            ManuscriptAnnotation("result", (), "", ("table-1.csv",), 2),
        ),
    )
    assert parsed.syntax_issues == ()


def test_editorial_comments_between_annotations_preserve_multiple_annotation_error() -> None:
    parsed = parse_manuscript(
        "## Results\n"
        "<!-- research-os:kind=result; artifacts=table-1.csv -->\n"
        "<!-- editorial note -->\n"
        "<!--\n"
        "more notes\n"
        "-->\n"
        "<!-- research-os:kind=fact; claims=claim-1 -->\n"
        "Reported result.\n"
    )

    assert parsed.blocks == (
        ManuscriptBlock(
            "Results",
            1,
            8,
            ManuscriptAnnotation("result", (), "", ("table-1.csv",), 2),
        ),
    )
    assert parsed.syntax_issues == (
        MarkupIssue("INVALID_ANNOTATION", "Results", 1, 7),
    )


def test_malformed_research_os_comment_remains_an_invalid_annotation() -> None:
    parsed = parse_manuscript(
        "## Results\n"
        "<!-- research-os:kind=result; artifacts=not safe.csv -->\n"
        "Reported result.\n"
    )

    assert parsed.blocks == (ManuscriptBlock("Results", 1, 3, None),)
    assert parsed.syntax_issues == (
        MarkupIssue("INVALID_ANNOTATION", "Results", 1, 2),
    )


def test_mid_block_annotation_is_invalid_without_splitting_the_block() -> None:
    parsed = parse_manuscript(
        "## Introduction\n"
        "First paragraph fragment.\n"
        "<!-- research-os:kind=fact; claims=claim-1 -->\n"
        "Second paragraph fragment.\n"
    )

    assert parsed.blocks == (ManuscriptBlock("Introduction", 1, 2, None),)
    assert parsed.syntax_issues == (
        MarkupIssue("INVALID_ANNOTATION", "Introduction", 1, 3),
    )


def test_fences_require_at_most_three_leading_spaces_and_never_tabs() -> None:
    parsed = parse_manuscript(
        "## Methods\n"
        "````\n"
        "    ````\n"
        "<!-- research-os:kind=method; idea=inside-four-spaces -->\n"
        "\t````\n"
        "<!-- research-os:kind=method; idea=inside-tab -->\n"
        "````\n"
        "<!-- research-os:kind=method; idea=idea-1 -->\n"
        "Methods prose.\n"
        "\n"
        "    ```\n"
        "\n"
        "<!-- research-os:kind=method; idea=idea-2 -->\n"
        "More methods prose.\n"
    )

    assert parsed.blocks == (
        ManuscriptBlock(
            "Methods",
            1,
            9,
            ManuscriptAnnotation("method", (), "idea-1", (), 8),
        ),
        ManuscriptBlock("Methods", 2, 11, None),
        ManuscriptBlock(
            "Methods",
            3,
            14,
            ManuscriptAnnotation("method", (), "idea-2", (), 13),
        ),
    )
    assert parsed.syntax_issues == ()


def test_active_multiline_comment_ignores_fences_and_parses_trailing_text() -> None:
    parsed = parse_manuscript(
        "## Results\n"
        "<!-- research-os:kind=result; artifacts=table-1.csv -->\n"
        "<!--\n"
        "```\n"
        "editorial note --> trailing result text\n"
    )

    assert parsed.blocks == (
        ManuscriptBlock(
            "Results",
            1,
            5,
            ManuscriptAnnotation("result", (), "", ("table-1.csv",), 2),
        ),
    )
    assert parsed.syntax_issues == ()


def test_malformed_multiline_annotation_stays_a_comment_without_consuming_pending() -> None:
    parsed = parse_manuscript(
        "## Results\n"
        "<!-- research-os:kind=result; artifacts=table-1.csv -->\n"
        "<!-- research-os:kind=fact; claims=claim-1\n"
        "continuation that is not prose\n"
        "-->\n"
        "Reported result.\n"
    )

    assert parsed.blocks == (
        ManuscriptBlock(
            "Results",
            1,
            6,
            ManuscriptAnnotation("result", (), "", ("table-1.csv",), 2),
        ),
    )
    assert parsed.syntax_issues == (
        MarkupIssue("INVALID_ANNOTATION", "Results", 1, 3),
    )


def test_spaced_horizontal_rules_split_blocks_without_accepting_mixed_markers() -> None:
    parsed = parse_manuscript(
        "## Abstract\n"
        "First block.\n"
        "* * *\n"
        "Second block.\n"
        "- - -\n"
        "Third block.\n"
        "_ _ _ _\n"
        "Fourth block.\n"
        "\n"
        "* - *\n"
        "Still one ordinary block.\n"
    )

    assert parsed.blocks == (
        ManuscriptBlock("Abstract", 1, 2, None),
        ManuscriptBlock("Abstract", 2, 4, None),
        ManuscriptBlock("Abstract", 3, 6, None),
        ManuscriptBlock("Abstract", 4, 8, None),
        ManuscriptBlock("Abstract", 5, 10, None),
    )


def test_consecutive_ordinary_comments_are_not_a_prose_block() -> None:
    parsed = parse_manuscript(
        "## Abstract\n"
        "<!-- first --> \t <!-- second -->\n"
        "Actual prose.\n"
    )

    assert parsed.blocks == (ManuscriptBlock("Abstract", 1, 3, None),)
    assert parsed.syntax_issues == ()


def test_pending_annotation_followed_only_by_consecutive_comments_is_orphaned() -> None:
    parsed = parse_manuscript(
        "## Results\n"
        "<!-- research-os:kind=result; artifacts=table-1.csv -->\n"
        "<!-- first --><!-- second -->\n"
    )

    assert parsed.blocks == ()
    assert parsed.syntax_issues == (
        MarkupIssue("ORPHAN_ANNOTATION", "Results", 1, 2),
    )


def test_research_os_annotation_after_ordinary_same_line_comment_is_not_bound() -> None:
    parsed = parse_manuscript(
        "## Results\n"
        "<!-- editorial --><!-- research-os:kind=result; artifacts=table-1.csv -->\n"
        "Reported result.\n"
    )

    assert parsed.blocks == (ManuscriptBlock("Results", 1, 3, None),)
    assert parsed.syntax_issues == ()
