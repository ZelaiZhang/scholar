import json
from pathlib import Path

import pytest

from research_os.review import (
    load_independent_review,
    load_meta_review,
    load_review_bundle,
)


IDEA_IDS = {"idea-0001", "idea-0002"}


def _assessment(idea_id: str) -> dict[str, object]:
    return {
        "idea_id": idea_id,
        "strengths": ["The question is falsifiable."],
        "concerns": ["The evaluation population needs tighter definition."],
        "blocking_issues": [],
        "recommendation": "revise",
        "confidence": 4,
    }


def _write_review(
    path: Path,
    *,
    role: str,
    run_id: str = "run-a",
    idea_ids: set[str] = IDEA_IDS,
) -> None:
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "role": role,
        "assessments": [_assessment(idea_id) for idea_id in sorted(idea_ids)],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_bundle(folder: Path, *, run_id: str = "run-a") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for role in ("novelty", "methods", "medical-safety"):
        _write_review(folder / f"{role}.json", role=role, run_id=run_id)


def _write_meta(
    path: Path,
    *,
    run_id: str = "run-a",
    shortlist_ids: list[str] | None = None,
) -> None:
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "consensus": ["Both ideas require a narrower evaluation scope."],
        "conflicts": ["Reviewers disagree on novelty strength."],
        "blocking_issues": [],
        "shortlist_ids": shortlist_ids or ["idea-0001"],
        "rationale_by_idea": {
            "idea-0001": "Promising after scope revision.",
            "idea-0002": "Evidence support is currently weaker.",
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_independent_review_round_trip_requires_exact_candidate_set(
    tmp_path: Path,
) -> None:
    path = tmp_path / "novelty.json"
    _write_review(path, role="novelty")

    review = load_independent_review(
        path,
        expected_role="novelty",
        expected_idea_ids=IDEA_IDS,
    )

    assert review.run_id == "run-a"
    assert review.role == "novelty"
    assert {item.idea_id for item in review.assessments} == IDEA_IDS

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["assessments"] = payload["assessments"][:1]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="candidate|Idea"):
        load_independent_review(
            path,
            expected_role="novelty",
            expected_idea_ids=IDEA_IDS,
        )


def test_review_rejects_unknown_role_duplicate_ideas_and_invalid_values(
    tmp_path: Path,
) -> None:
    path = tmp_path / "review.json"
    _write_review(path, role="novelty")
    payload = json.loads(path.read_text(encoding="utf-8"))

    payload["role"] = "general"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="role"):
        load_independent_review(
            path,
            expected_role="novelty",
            expected_idea_ids=IDEA_IDS,
        )

    payload["role"] = "novelty"
    payload["assessments"][1]["idea_id"] = "idea-0001"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate|candidate|Idea"):
        load_independent_review(
            path,
            expected_role="novelty",
            expected_idea_ids=IDEA_IDS,
        )

    payload["assessments"][1]["idea_id"] = "idea-0002"
    payload["assessments"][0]["recommendation"] = "selected"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="recommendation"):
        load_independent_review(
            path,
            expected_role="novelty",
            expected_idea_ids=IDEA_IDS,
        )

    payload["assessments"][0]["recommendation"] = "advance"
    payload["assessments"][0]["confidence"] = 6
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="confidence"):
        load_independent_review(
            path,
            expected_role="novelty",
            expected_idea_ids=IDEA_IDS,
        )


def test_review_rejects_extra_fields_invalid_json_utf8_and_oversize(
    tmp_path: Path,
) -> None:
    path = tmp_path / "review.json"
    _write_review(path, role="methods")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["selected"] = "idea-0001"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="field"):
        load_independent_review(
            path,
            expected_role="methods",
            expected_idea_ids=IDEA_IDS,
        )

    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON"):
        load_independent_review(
            path,
            expected_role="methods",
            expected_idea_ids=IDEA_IDS,
        )

    path.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="UTF-8"):
        load_independent_review(
            path,
            expected_role="methods",
            expected_idea_ids=IDEA_IDS,
        )

    path.write_bytes(b" " * (1024 * 1024 + 1))
    with pytest.raises(ValueError, match="1 MiB"):
        load_independent_review(
            path,
            expected_role="methods",
            expected_idea_ids=IDEA_IDS,
        )


def test_review_bundle_requires_all_roles_and_one_run(tmp_path: Path) -> None:
    _write_review(tmp_path / "novelty.json", role="novelty")
    _write_review(tmp_path / "methods.json", role="methods")

    with pytest.raises(ValueError, match="medical-safety"):
        load_review_bundle(tmp_path, expected_idea_ids=IDEA_IDS)

    _write_review(
        tmp_path / "medical-safety.json",
        role="medical-safety",
        run_id="run-other",
    )
    with pytest.raises(ValueError, match="run_id"):
        load_review_bundle(tmp_path, expected_idea_ids=IDEA_IDS)


def test_meta_review_is_bound_to_bundle_and_cannot_select(tmp_path: Path) -> None:
    reviews = tmp_path / "reviews"
    _write_bundle(reviews)
    bundle = load_review_bundle(reviews, expected_idea_ids=IDEA_IDS)
    meta_path = tmp_path / "meta-review.json"
    _write_meta(meta_path)

    meta = load_meta_review(
        meta_path,
        expected_idea_ids=IDEA_IDS,
        expected_run_id=bundle.run_id,
    )

    assert meta.shortlist_ids == ("idea-0001",)
    assert set(meta.rationale_by_idea) == IDEA_IDS

    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    payload["selected"] = "idea-0001"
    meta_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="field"):
        load_meta_review(
            meta_path,
            expected_idea_ids=IDEA_IDS,
            expected_run_id="run-a",
        )


def test_meta_review_rejects_unknown_shortlist_missing_rationale_and_run(
    tmp_path: Path,
) -> None:
    path = tmp_path / "meta-review.json"
    _write_meta(path, shortlist_ids=["idea-9999"])
    with pytest.raises(ValueError, match="shortlist"):
        load_meta_review(
            path,
            expected_idea_ids=IDEA_IDS,
            expected_run_id="run-a",
        )

    _write_meta(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["rationale_by_idea"]["idea-0002"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="rationale"):
        load_meta_review(
            path,
            expected_idea_ids=IDEA_IDS,
            expected_run_id="run-a",
        )

    _write_meta(path, run_id="run-other")
    with pytest.raises(ValueError, match="run_id"):
        load_meta_review(
            path,
            expected_idea_ids=IDEA_IDS,
            expected_run_id="run-a",
        )
