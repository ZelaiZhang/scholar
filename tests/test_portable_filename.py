from __future__ import annotations

import pytest

from research_os.portable_filename import (
    is_portable_direct_filename,
    validate_portable_direct_filename,
)


@pytest.mark.parametrize(
    "name",
    (
        "aggregate-results.csv",
        "Data_2026-08-13.jsonl",
        "a.md",
        "9-results.tsv",
    ),
)
def test_portable_direct_filename_accepts_documented_ascii_grammar(name: str) -> None:
    assert is_portable_direct_filename(name) is True
    assert validate_portable_direct_filename(name) == name


@pytest.mark.parametrize(
    "name",
    (
        "",
        ".",
        "..",
        ".hidden.csv",
        "nested/result.csv",
        r"nested\result.csv",
        "result.csv:stream",
        "result name.csv",
        "result.csv.",
        "result.csv ",
        "result\x00.csv",
        "结果.csv",
        "a" * 125 + ".csv",
        "CON",
        "con.csv",
        "PRN.md",
        "aux.json",
        "NUL.tsv",
        "COM1.csv",
        "com9.anything",
        "LPT1.yaml",
        "lpt9.md",
    ),
)
def test_portable_direct_filename_rejects_cross_platform_aliases(name: str) -> None:
    assert is_portable_direct_filename(name) is False
    with pytest.raises(ValueError, match="portable direct filename"):
        validate_portable_direct_filename(name)


def test_portable_direct_filename_rejects_non_string_values() -> None:
    assert is_portable_direct_filename(None) is False
    with pytest.raises(ValueError, match="portable direct filename"):
        validate_portable_direct_filename(1)
