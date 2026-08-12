from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


MAX_REVIEW_BYTES = 1024 * 1024
REVIEW_ROLES = ("novelty", "methods", "medical-safety")
RECOMMENDATIONS = {"advance", "revise", "reject"}

REVIEW_KEYS = {"schema_version", "run_id", "role", "assessments"}
ASSESSMENT_KEYS = {
    "idea_id",
    "strengths",
    "concerns",
    "blocking_issues",
    "recommendation",
    "confidence",
}
META_REVIEW_KEYS = {
    "schema_version",
    "run_id",
    "consensus",
    "conflicts",
    "blocking_issues",
    "shortlist_ids",
    "rationale_by_idea",
}


@dataclass(frozen=True)
class ReviewAssessment:
    idea_id: str
    strengths: tuple[str, ...]
    concerns: tuple[str, ...]
    blocking_issues: tuple[str, ...]
    recommendation: str
    confidence: int


@dataclass(frozen=True)
class IndependentReview:
    schema_version: int
    run_id: str
    role: str
    assessments: tuple[ReviewAssessment, ...]


@dataclass(frozen=True)
class ReviewBundle:
    novelty: IndependentReview
    methods: IndependentReview
    medical_safety: IndependentReview

    @property
    def run_id(self) -> str:
        return self.novelty.run_id

    @property
    def by_role(self) -> dict[str, IndependentReview]:
        return {
            "novelty": self.novelty,
            "methods": self.methods,
            "medical-safety": self.medical_safety,
        }


@dataclass(frozen=True)
class MetaReview:
    schema_version: int
    run_id: str
    consensus: tuple[str, ...]
    conflicts: tuple[str, ...]
    blocking_issues: tuple[str, ...]
    shortlist_ids: tuple[str, ...]
    rationale_by_idea: dict[str, str]


def _require_exact_keys(
    raw: dict[str, object], expected: set[str], *, context: str
) -> None:
    actual = set(raw)
    if actual != expected:
        raise ValueError(
            f"{context} fields are invalid: missing {sorted(expected - actual)}, "
            f"extra {sorted(actual - expected)}"
        )


def _require_string(raw: object, *, context: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{context} must be a non-empty string")
    return raw.strip()


def _require_string_tuple(raw: object, *, context: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"{context} must be a list")
    values = tuple(_require_string(item, context=context) for item in raw)
    if len(values) != len(set(values)):
        raise ValueError(f"{context} contains duplicate values")
    return values


def _read_json_object(path: Path, *, context: str) -> dict[str, object]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError(f"{context} cannot be read: {path}") from exc
    if size > MAX_REVIEW_BYTES:
        raise ValueError(f"{context} exceeds the 1 MiB limit")
    try:
        text = path.read_bytes().decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{context} must be UTF-8") from exc
    except OSError as exc:
        raise ValueError(f"{context} cannot be read: {path}") from exc
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{context} contains invalid JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{context} must be a JSON object")
    return raw


def _require_schema_version(raw: object, *, context: str) -> None:
    if type(raw) is not int or raw != 1:
        raise ValueError(f"{context} schema_version must be 1")


def _parse_assessment(raw: object) -> ReviewAssessment:
    if not isinstance(raw, dict):
        raise ValueError("review assessment must be an object")
    _require_exact_keys(raw, ASSESSMENT_KEYS, context="review assessment")
    recommendation = _require_string(
        raw["recommendation"], context="recommendation"
    )
    if recommendation not in RECOMMENDATIONS:
        raise ValueError(
            "recommendation must be advance, revise, or reject; "
            "reviewers cannot select Ideas"
        )
    confidence = raw["confidence"]
    if type(confidence) is not int or not 1 <= confidence <= 5:
        raise ValueError("confidence must be an integer from 1 to 5")
    return ReviewAssessment(
        idea_id=_require_string(raw["idea_id"], context="idea_id"),
        strengths=_require_string_tuple(raw["strengths"], context="strengths"),
        concerns=_require_string_tuple(raw["concerns"], context="concerns"),
        blocking_issues=_require_string_tuple(
            raw["blocking_issues"], context="blocking_issues"
        ),
        recommendation=recommendation,
        confidence=confidence,
    )


def load_independent_review(
    path: Path,
    *,
    expected_role: str,
    expected_idea_ids: set[str],
) -> IndependentReview:
    if expected_role not in REVIEW_ROLES:
        raise ValueError(f"unknown expected review role: {expected_role}")
    raw = _read_json_object(path, context=f"{expected_role} review")
    _require_exact_keys(raw, REVIEW_KEYS, context="independent review")
    _require_schema_version(raw["schema_version"], context="independent review")
    role = _require_string(raw["role"], context="review role")
    if role not in REVIEW_ROLES or role != expected_role:
        raise ValueError(
            f"review role mismatch: expected {expected_role}, found {role}"
        )
    assessments_raw = raw["assessments"]
    if not isinstance(assessments_raw, list):
        raise ValueError("review assessments must be a list")
    assessments = tuple(_parse_assessment(item) for item in assessments_raw)
    actual_ids = [assessment.idea_id for assessment in assessments]
    if len(actual_ids) != len(set(actual_ids)):
        raise ValueError("review contains duplicate Idea assessments")
    if set(actual_ids) != expected_idea_ids:
        raise ValueError(
            "review candidate Idea set mismatch: "
            f"missing {sorted(expected_idea_ids - set(actual_ids))}, "
            f"unknown {sorted(set(actual_ids) - expected_idea_ids)}"
        )
    return IndependentReview(
        schema_version=1,
        run_id=_require_string(raw["run_id"], context="run_id"),
        role=role,
        assessments=assessments,
    )


def load_review_bundle(
    folder: Path, *, expected_idea_ids: set[str]
) -> ReviewBundle:
    reviews: dict[str, IndependentReview] = {}
    for role in REVIEW_ROLES:
        path = folder / f"{role}.json"
        if not path.is_file():
            raise ValueError(f"missing independent review: {role}")
        reviews[role] = load_independent_review(
            path,
            expected_role=role,
            expected_idea_ids=expected_idea_ids,
        )
    run_ids = {review.run_id for review in reviews.values()}
    if len(run_ids) != 1:
        raise ValueError("independent review run_id values do not match")
    return ReviewBundle(
        novelty=reviews["novelty"],
        methods=reviews["methods"],
        medical_safety=reviews["medical-safety"],
    )


def load_meta_review(
    path: Path,
    *,
    expected_idea_ids: set[str],
    expected_run_id: str,
) -> MetaReview:
    raw = _read_json_object(path, context="meta-review")
    _require_exact_keys(raw, META_REVIEW_KEYS, context="meta-review")
    _require_schema_version(raw["schema_version"], context="meta-review")
    run_id = _require_string(raw["run_id"], context="run_id")
    if run_id != expected_run_id:
        raise ValueError(
            f"meta-review run_id mismatch: expected {expected_run_id}, found {run_id}"
        )
    shortlist_ids = _require_string_tuple(
        raw["shortlist_ids"], context="shortlist_ids"
    )
    unknown_shortlist = set(shortlist_ids) - expected_idea_ids
    if unknown_shortlist:
        raise ValueError(
            f"meta-review shortlist contains unknown Ideas: {sorted(unknown_shortlist)}"
        )
    rationale_raw = raw["rationale_by_idea"]
    if not isinstance(rationale_raw, dict):
        raise ValueError("rationale_by_idea must be an object")
    if set(rationale_raw) != expected_idea_ids:
        raise ValueError(
            "meta-review rationale Idea set mismatch: "
            f"missing {sorted(expected_idea_ids - set(rationale_raw))}, "
            f"unknown {sorted(set(rationale_raw) - expected_idea_ids)}"
        )
    rationale = {
        idea_id: _require_string(value, context=f"rationale for {idea_id}")
        for idea_id, value in rationale_raw.items()
    }
    return MetaReview(
        schema_version=1,
        run_id=run_id,
        consensus=_require_string_tuple(raw["consensus"], context="consensus"),
        conflicts=_require_string_tuple(raw["conflicts"], context="conflicts"),
        blocking_issues=_require_string_tuple(
            raw["blocking_issues"], context="blocking_issues"
        ),
        shortlist_ids=shortlist_ids,
        rationale_by_idea=rationale,
    )
