import json
from pathlib import Path

import pytest

from research_os.cycle import (
    advance_cycle,
    load_cycle_manifest,
    save_cycle_manifest,
)
from research_os.ideas import (
    IdeaArchive,
    IdeaRecord,
    IdeaScores,
    NoveltyEvidence,
    approve_idea,
    load_idea_archive,
    save_idea_archive,
)
from research_os.project import create_project, link_project_sources


def _idea(run_id: str, *, novelty_checked: bool = False) -> IdeaRecord:
    return IdeaRecord(
        idea_id="idea-0001",
        parent_ids=(),
        title="Evidence-constrained diagnostic reasoning",
        scientific_question="Can explicit counterevidence reduce unsupported conclusions?",
        hypothesis="A counterevidence gate will reduce unsupported conclusions.",
        contribution="A falsifiable evidence gate for diagnostic reasoning.",
        evidence_source_ids=("src-a",),
        novelty=NoveltyEvidence(
            status="checked" if novelty_checked else "pending",
            queries=("counterevidence medical reasoning",) if novelty_checked else (),
            nearest_source_ids=("src-a",) if novelty_checked else (),
            differences="Uses an explicit evidence gate." if novelty_checked else "",
            unresolved_overlap="" if novelty_checked else "Search required.",
        ),
        scores=IdeaScores(8, 7, 7, 6),
        method_risks=("Evaluation leakage",),
        medical_safety_risks=("No clinical efficacy claim",),
        failure_criterion="Unsupported conclusions do not decrease.",
        external_experiment="Compare on a separate public benchmark repository.",
        status="draft",
        generated_by_run=run_id,
        provenance={"generator": "local", "response_sha256": "a" * 64},
        researcher_decision=None,
    )


def _write_candidates(project: Path, run_id: str, *, checked: bool = False) -> None:
    save_idea_archive(
        project / "cycles" / run_id / "candidates.yaml",
        IdeaArchive(1, project.name, (_idea(run_id, novelty_checked=checked),)),
    )


def _assessment(idea_id: str) -> dict[str, object]:
    return {
        "idea_id": idea_id,
        "strengths": ["Falsifiable"],
        "concerns": ["Scope needs refinement"],
        "blocking_issues": [],
        "recommendation": "advance",
        "confidence": 4,
    }


def _write_reviews(project: Path, run_id: str) -> None:
    folder = project / "cycles" / run_id / "reviews"
    folder.mkdir()
    for role in ("novelty", "methods", "medical-safety"):
        payload = {
            "schema_version": 1,
            "run_id": run_id,
            "role": role,
            "assessments": [_assessment("idea-0001")],
        }
        (folder / f"{role}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )


def _write_meta(project: Path, run_id: str) -> None:
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "consensus": ["The idea is testable."],
        "conflicts": [],
        "blocking_issues": [],
        "shortlist_ids": ["idea-0001"],
        "rationale_by_idea": {"idea-0001": "Best evidence-to-cost tradeoff."},
    }
    (project / "cycles" / run_id / "meta-review.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _project(tmp_path: Path) -> Path:
    project = create_project(tmp_path, "Topic A", "topic-a")
    link_project_sources(tmp_path, "topic-a", ["src-a"])
    return project


def test_cycle_creates_local_run_and_resumes_without_duplicate_work(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)

    first = advance_cycle(tmp_path, "topic-a", max_ideas=4, max_calls=6)
    journal = project / "research-journal.jsonl"
    first_events = journal.read_text(encoding="utf-8").splitlines()
    second = advance_cycle(tmp_path, "topic-a", max_ideas=4, max_calls=6)

    assert first.run_id == second.run_id
    assert first.state == "candidate_generation"
    assert first.next_action == "create_candidates"
    assert first.manifest.calls_used == 0
    assert second.target == first.target
    assert journal.read_text(encoding="utf-8").splitlines() == first_events
    assert (project / "cycles" / first.run_id / "work-packet.md").is_file()
    assert (project / "ideas" / "archive.yaml").is_file()


def test_new_run_is_explicit_and_ids_are_unique(tmp_path: Path) -> None:
    _project(tmp_path)
    first = advance_cycle(tmp_path, "topic-a")
    second = advance_cycle(tmp_path, "topic-a", new_run=True)

    assert first.run_id != second.run_id
    assert second.state == "candidate_generation"


@pytest.mark.parametrize(
    ("max_ideas", "max_calls"),
    [(0, 6), (11, 6), (4, 0), (4, 21), (True, 6)],
)
def test_cycle_rejects_invalid_bounds(
    tmp_path: Path, max_ideas: int, max_calls: int
) -> None:
    _project(tmp_path)
    with pytest.raises(ValueError, match="max_ideas|max_calls"):
        advance_cycle(
            tmp_path,
            "topic-a",
            max_ideas=max_ideas,
            max_calls=max_calls,
        )


def test_cycle_reconciles_full_gate_order_and_requires_human_approval(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    created = advance_cycle(tmp_path, "topic-a")
    run_id = created.run_id

    _write_candidates(project, run_id)
    novelty = advance_cycle(tmp_path, "topic-a")
    assert novelty.state == "novelty_check"
    assert novelty.next_action == "document_novelty"
    archive_path = project / "ideas" / "archive.yaml"
    archive = load_idea_archive(archive_path, allowed_source_ids={"src-a"})
    assert archive.ideas[0].status == "needs_novelty_check"

    _write_candidates(project, run_id, checked=True)
    independent = advance_cycle(tmp_path, "topic-a")
    assert independent.state == "independent_review"
    assert independent.next_action == "create_independent_reviews"

    _write_reviews(project, run_id)
    meta = advance_cycle(tmp_path, "topic-a")
    assert meta.state == "meta_review"
    assert meta.next_action == "create_meta_review"

    _write_meta(project, run_id)
    human = advance_cycle(tmp_path, "topic-a")
    assert human.state == "awaiting_human_decision"
    assert human.next_action == "approve_or_reject_idea"
    archive = load_idea_archive(archive_path, allowed_source_ids={"src-a"})
    assert archive.ideas[0].status == "shortlisted"

    selected = approve_idea(archive, "idea-0001", reason="Researcher approved")
    save_idea_archive(archive_path, selected)
    completed = advance_cycle(tmp_path, "topic-a")
    assert completed.state == "completed"
    assert completed.next_action == "none"

    manifest = load_cycle_manifest(
        project / "cycles" / run_id / "manifest.yaml"
    )
    assert manifest.state == "completed"
    assert manifest.calls_used == 0


def test_invalid_candidate_artifact_blocks_without_import(tmp_path: Path) -> None:
    project = _project(tmp_path)
    action = advance_cycle(tmp_path, "topic-a")
    candidate_path = project / "cycles" / action.run_id / "candidates.yaml"
    candidate_path.write_text("schema_version: [broken", encoding="utf-8")

    blocked = advance_cycle(tmp_path, "topic-a")

    assert blocked.state == "blocked"
    assert blocked.next_action == "repair_candidates"
    assert load_idea_archive(
        project / "ideas" / "archive.yaml", allowed_source_ids={"src-a"}
    ).ideas == ()


def test_candidate_content_is_frozen_before_reviews(tmp_path: Path) -> None:
    project = _project(tmp_path)
    created = advance_cycle(tmp_path, "topic-a")
    _write_candidates(project, created.run_id, checked=True)
    review_action = advance_cycle(tmp_path, "topic-a")
    assert review_action.state == "independent_review"

    archive_path = project / "cycles" / created.run_id / "candidates.yaml"
    candidates = load_idea_archive(archive_path, allowed_source_ids={"src-a"})
    changed = IdeaArchive(
        1,
        "topic-a",
        (
            IdeaRecord(
                **{
                    **candidates.ideas[0].__dict__,
                    "title": "Changed after review began",
                }
            ),
        ),
    )
    save_idea_archive(archive_path, changed)

    blocked = advance_cycle(tmp_path, "topic-a")
    assert blocked.state == "blocked"
    assert blocked.next_action == "restore_frozen_candidates"


def test_provider_is_not_dispatched_after_budget_is_exhausted(tmp_path: Path) -> None:
    project = _project(tmp_path)
    created = advance_cycle(tmp_path, "topic-a", max_calls=1)
    manifest_path = project / "cycles" / created.run_id / "manifest.yaml"
    manifest = load_cycle_manifest(manifest_path)
    save_cycle_manifest(
        manifest_path,
        type(manifest)(**{**manifest.__dict__, "calls_used": 1}),
    )

    class ProviderThatMustNotRun:
        def complete(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("provider was dispatched after budget exhaustion")

    action = advance_cycle(
        tmp_path,
        "topic-a",
        max_calls=1,
        provider=ProviderThatMustNotRun(),
    )
    assert action.state == "budget_exhausted"
    assert action.manifest.calls_used == 1


def test_approved_idea_must_match_the_reviewed_candidate(tmp_path: Path) -> None:
    project = _project(tmp_path)
    created = advance_cycle(tmp_path, "topic-a")
    _write_candidates(project, created.run_id, checked=True)
    advance_cycle(tmp_path, "topic-a")
    _write_reviews(project, created.run_id)
    advance_cycle(tmp_path, "topic-a")
    _write_meta(project, created.run_id)
    human = advance_cycle(tmp_path, "topic-a")
    assert human.state == "awaiting_human_decision"

    archive_path = project / "ideas" / "archive.yaml"
    archive = load_idea_archive(archive_path, allowed_source_ids={"src-a"})
    changed = IdeaRecord(
        **{**archive.ideas[0].__dict__, "title": "Changed after all reviews"}
    )
    changed_archive = IdeaArchive(1, "topic-a", (changed,))
    selected = approve_idea(
        changed_archive,
        "idea-0001",
        reason="Researcher approved a changed version",
    )
    save_idea_archive(archive_path, selected)

    blocked = advance_cycle(tmp_path, "topic-a")
    assert blocked.state == "blocked"
    assert blocked.next_action == "restore_reviewed_idea"
