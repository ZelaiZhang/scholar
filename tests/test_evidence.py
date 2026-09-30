from pathlib import Path

import pytest

from research_os.evidence import (
    LedgerFormatError,
    load_ledger,
    render_validation_report,
    validate_ledger,
)


def claim(**overrides):
    value = {
        "claim_id": "C001",
        "statement": "A improves B",
        "type": "fact",
        "status": "verified",
        "support": [{"source_id": "src-1", "locator": "p. 3"}],
        "opposition": [],
        "confidence": "medium",
        "limitations": "single dataset",
    }
    value.update(overrides)
    return value


def test_verified_fact_requires_source_locator() -> None:
    ledger = {
        "claims": [claim(support=[{"source_id": "src-1", "locator": ""}])]
    }

    errors = validate_ledger(ledger)

    assert any(error.code == "missing_locator" for error in errors)


def test_hypothesis_may_be_unverified_but_must_be_labeled() -> None:
    ledger = {
        "claims": [
            claim(
                claim_id="C002",
                statement="Structured reasoning may help",
                type="hypothesis",
                status="unverified",
                support=[],
                confidence="low",
                limitations="requires experiment",
            )
        ]
    }

    assert validate_ledger(ledger) == []


def test_duplicate_ids_and_unreferenced_verified_fact_are_rejected() -> None:
    ledger = {
        "claims": [
            claim(claim_id="C001"),
            claim(claim_id="C001", support=[]),
        ]
    }

    codes = {issue.code for issue in validate_ledger(ledger)}

    assert "duplicate_claim_id" in codes
    assert "missing_support" in codes


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("type", "opinion", "invalid_type"),
        ("status", "done", "invalid_status"),
        ("confidence", "certain", "invalid_confidence"),
        ("limitations", "", "missing_limitations"),
    ],
)
def test_invalid_claim_fields_are_reported(field: str, value: str, code: str) -> None:
    issues = validate_ledger({"claims": [claim(**{field: value})]})
    assert any(issue.code == code for issue in issues)


def test_load_ledger_and_render_report(tmp_path: Path) -> None:
    path = tmp_path / "ledger.yaml"
    path.write_text("claims:\n  - claim_id: C001\n", encoding="utf-8")

    ledger = load_ledger(path)
    report = render_validation_report(path, validate_ledger(ledger))

    assert "C001" in report
    assert "invalid_type" in report


def test_load_ledger_rejects_non_mapping(tmp_path: Path) -> None:
    path = tmp_path / "ledger.yaml"
    path.write_text("- item\n", encoding="utf-8")

    with pytest.raises(LedgerFormatError):
        load_ledger(path)


def test_missing_claim_id_is_an_error_even_when_fact_is_otherwise_valid() -> None:
    issues = validate_ledger({"claims": [claim(claim_id="")]})

    assert any(issue.code == "missing_claim_id" for issue in issues)


def test_source_ids_are_resolved_and_opposition_is_validated() -> None:
    ledger = {
        "claims": [
            claim(
                status="conflicted",
                support=[{"source_id": "src-known", "locator": "p. 2"}],
                opposition=[{"source_id": "src-invented", "locator": ""}],
            )
        ]
    }

    issues = validate_ledger(ledger, known_source_ids={"src-known"})
    codes = {issue.code for issue in issues}

    assert "unknown_source_id" in codes
    assert "missing_locator" in codes


def test_conflicted_claim_requires_opposition_evidence() -> None:
    issues = validate_ledger(
        {"claims": [claim(status="conflicted", opposition=[])]},
        known_source_ids={"src-1"},
    )

    assert any(issue.code == "missing_opposition" for issue in issues)


@pytest.mark.parametrize("field", ["claim_id", "statement", "limitations"])
@pytest.mark.parametrize("value", [None, False, 42, [], {}])
def test_non_text_claim_fields_cannot_pass_verification(field, value) -> None:
    issues = validate_ledger({"claims": [claim(**{field: value})]})
    assert any(issue.code == f"missing_{field}" for issue in issues)


@pytest.mark.parametrize("field", ["type", "status", "confidence"])
@pytest.mark.parametrize("value", [[], {}, None])
def test_malformed_enum_fields_report_issues_instead_of_crashing(field, value) -> None:
    issues = validate_ledger({"claims": [claim(**{field: value})]})
    assert any(issue.code == f"invalid_{field}" for issue in issues)


@pytest.mark.parametrize("lane", ["support", "opposition"])
@pytest.mark.parametrize("field", ["source_id", "locator"])
@pytest.mark.parametrize("value", [None, False, 42, [], {}])
def test_reference_fields_require_actual_text(lane, field, value) -> None:
    reference = {"source_id": "src-1", "locator": "p. 3", field: value}
    issues = validate_ledger({"claims": [claim(**{lane: [reference]})]})
    assert any(issue.code == f"missing_{field}" for issue in issues)


def test_duplicate_yaml_keys_cannot_silently_change_evidence_status(tmp_path) -> None:
    path = tmp_path / "ledger.yaml"
    path.write_text(
        "claims:\n  - claim_id: C001\n    status: unverified\n    status: verified\n",
        encoding="utf-8",
    )
    with pytest.raises(LedgerFormatError, match="duplicate"):
        load_ledger(path)
