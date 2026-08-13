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
