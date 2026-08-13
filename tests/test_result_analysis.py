from __future__ import annotations

import pytest

from research_os.result_analysis import (
    RESULT_COMPLETE_MARKER,
    ResultInputBinding,
    parse_result_input_binding,
    render_result_input_binding,
    validate_result_analysis_completion,
)


SHA_A = "a" * 64
SHA_B = "b" * 64


def _analysis(*lines: str) -> str:
    return "# Result analysis\n\nHuman conservative interpretation.\n\n" + "\n".join(lines) + "\n"


def test_result_input_binding_parser_and_renderer_are_exact_and_anchored() -> None:
    binding = ResultInputBinding("aggregate-results.csv", SHA_A)
    rendered = render_result_input_binding(binding)

    assert rendered == (
        "<!-- research-os:result-input name=aggregate-results.csv; "
        f"sha256={SHA_A} -->"
    )
    assert parse_result_input_binding(rendered) == binding
    assert parse_result_input_binding(" " + rendered) is None
    assert parse_result_input_binding(rendered + " trailing") is None
    assert parse_result_input_binding(rendered.replace("; ", ";")) is None


def test_completed_result_analysis_requires_exact_current_binding_set() -> None:
    validation = validate_result_analysis_completion(
        _analysis(
            render_result_input_binding(ResultInputBinding("aggregate-results.csv", SHA_A)),
            render_result_input_binding(ResultInputBinding("ablation.tsv", SHA_B)),
            RESULT_COMPLETE_MARKER,
        ),
        (("aggregate-results.csv", SHA_A), ("ablation.tsv", SHA_B)),
    )

    assert validation.complete is True
    assert validation.code == "RESULT_BINDINGS_MATCH"
    assert validation.bindings == (
        ResultInputBinding("aggregate-results.csv", SHA_A),
        ResultInputBinding("ablation.tsv", SHA_B),
    )


@pytest.mark.parametrize(
    ("lines", "expected", "code"),
    (
        ((RESULT_COMPLETE_MARKER,), (("aggregate-results.csv", SHA_A),), "RESULT_BINDING_MISSING"),
        (
            (
                "<!-- research-os:result-input name=aggregate-results.csv; sha256=BAD -->",
                RESULT_COMPLETE_MARKER,
            ),
            (("aggregate-results.csv", SHA_A),),
            "RESULT_BINDING_MALFORMED",
        ),
        (
            (
                f"<!-- research-os:result-input name=aggregate-results.csv; sha256={SHA_A} -->",
                f"<!-- research-os:result-input name=aggregate-results.csv; sha256={SHA_A} -->",
                RESULT_COMPLETE_MARKER,
            ),
            (("aggregate-results.csv", SHA_A),),
            "RESULT_BINDING_DUPLICATE",
        ),
        (
            (
                f"<!-- research-os:result-input name=aggregate-results.csv; sha256={SHA_B} -->",
                RESULT_COMPLETE_MARKER,
            ),
            (("aggregate-results.csv", SHA_A),),
            "RESULT_BINDING_STALE",
        ),
        (
            (
                f"<!-- research-os:result-input name=aggregate-results.csv; sha256={SHA_A} -->",
                f"<!-- research-os:result-input name=unknown.csv; sha256={SHA_B} -->",
                RESULT_COMPLETE_MARKER,
            ),
            (("aggregate-results.csv", SHA_A),),
            "RESULT_BINDING_EXTRA",
        ),
        (
            (
                f"<!-- research-os:result-input name=aggregate-results.csv; sha256={SHA_A} -->",
            ),
            (("aggregate-results.csv", SHA_A),),
            "RESULT_MARKER_MISSING",
        ),
    ),
)
def test_result_analysis_rejects_missing_malformed_duplicate_stale_and_extra_bindings(
    lines: tuple[str, ...],
    expected: tuple[tuple[str, str], ...],
    code: str,
) -> None:
    validation = validate_result_analysis_completion(_analysis(*lines), expected)

    assert validation.complete is False
    assert validation.code == code
    assert validation.detail


def test_same_digest_remains_bound_independent_of_file_identity() -> None:
    text = _analysis(
        render_result_input_binding(ResultInputBinding("aggregate-results.csv", SHA_A)),
        RESULT_COMPLETE_MARKER,
    )

    first = validate_result_analysis_completion(
        text,
        (("aggregate-results.csv", SHA_A),),
    )
    replacement_with_same_bytes = validate_result_analysis_completion(
        text,
        (("aggregate-results.csv", SHA_A),),
    )

    assert first.complete is True
    assert replacement_with_same_bytes.complete is True


@pytest.mark.parametrize(
    "hidden_example",
    (
        "```markdown\n{binding}\n{marker}\n```",
        "~~~text\n{binding}\n{marker}\n~~~",
        "   ````markdown\n{binding}\n```\n{marker}\n   `````",
        "~~~text\n{binding}\n```\n{marker}\n~~~",
        "<!-- archived example\n{binding}\n{marker}\n-->",
        "<!-- archived fenced example\n```markdown\n{binding}\n```\n-->\n{marker}",
        "<!-- first --><!-- archived example\n{binding}\n{marker}\n-->",
        "<!-- first\nend --><!-- chained archive\n{binding}\n{marker}\n-->",
        "Prose opens an archive <!--\n{binding}\n{marker}\n-->",
        "    {binding}\n    {marker}",
    ),
)
def test_result_completion_ignores_non_live_markdown_examples(
    hidden_example: str,
) -> None:
    binding = render_result_input_binding(
        ResultInputBinding("aggregate-results.csv", SHA_A)
    )
    markdown = _analysis(
        hidden_example.format(binding=binding, marker=RESULT_COMPLETE_MARKER)
    )

    validation = validate_result_analysis_completion(
        markdown,
        (("aggregate-results.csv", SHA_A),),
    )

    assert validation.complete is False
    assert validation.code in {"RESULT_BINDING_MISSING", "RESULT_MARKER_MISSING"}
    assert validation.bindings == ()


def test_result_completion_ignores_non_live_duplicate_markers() -> None:
    binding = render_result_input_binding(
        ResultInputBinding("aggregate-results.csv", SHA_A)
    )
    validation = validate_result_analysis_completion(
        _analysis(
            "```markdown",
            RESULT_COMPLETE_MARKER,
            "```",
            binding,
            RESULT_COMPLETE_MARKER,
        ),
        (("aggregate-results.csv", SHA_A),),
    )

    assert validation.complete is True
    assert validation.code == "RESULT_BINDINGS_MATCH"


def test_result_completion_ignores_binding_comments_nested_in_outer_comment() -> None:
    binding = render_result_input_binding(
        ResultInputBinding("aggregate-results.csv", SHA_A)
    )
    validation = validate_result_analysis_completion(
        _analysis(
            "<!-- archived example",
            binding,
            RESULT_COMPLETE_MARKER,
            "-->",
            binding,
            RESULT_COMPLETE_MARKER,
        ),
        (("aggregate-results.csv", SHA_A),),
    )

    assert validation.complete is True
    assert validation.code == "RESULT_BINDINGS_MATCH"
    assert validation.bindings == (
        ResultInputBinding("aggregate-results.csv", SHA_A),
    )


def test_invalid_backtick_info_string_does_not_open_a_fence() -> None:
    binding = render_result_input_binding(
        ResultInputBinding("aggregate-results.csv", SHA_A)
    )
    validation = validate_result_analysis_completion(
        _analysis(
            "```markdown`invalid",
            binding,
            RESULT_COMPLETE_MARKER,
        ),
        (("aggregate-results.csv", SHA_A),),
    )

    assert validation.complete is True


@pytest.mark.parametrize("separator", ["\v", "\f", "\x85", "\u2028", "\u2029"])
def test_unicode_separators_cannot_create_live_result_comment_lines(
    separator: str,
) -> None:
    binding = render_result_input_binding(
        ResultInputBinding("aggregate-results.csv", SHA_A)
    )
    validation = validate_result_analysis_completion(
        _analysis(f"Prose{separator}{binding}{separator}{RESULT_COMPLETE_MARKER}"),
        (("aggregate-results.csv", SHA_A),),
    )

    assert validation.complete is False
    assert validation.bindings == ()


@pytest.mark.parametrize(
    ("lines", "code"),
    (
        (
            (
                RESULT_COMPLETE_MARKER,
                render_result_input_binding(
                    ResultInputBinding("aggregate-results.csv", SHA_A)
                ),
            ),
            "RESULT_MARKER_ORDER_INVALID",
        ),
        (
            (
                render_result_input_binding(
                    ResultInputBinding("aggregate-results.csv", SHA_A)
                ),
                RESULT_COMPLETE_MARKER,
                RESULT_COMPLETE_MARKER,
            ),
            "RESULT_MARKER_INVALID",
        ),
    ),
)
def test_completion_marker_must_be_unique_and_follow_every_live_binding(
    lines: tuple[str, ...],
    code: str,
) -> None:
    validation = validate_result_analysis_completion(
        _analysis(*lines),
        (("aggregate-results.csv", SHA_A),),
    )

    assert validation.complete is False
    assert validation.code == code
