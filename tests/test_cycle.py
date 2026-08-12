import json
import shutil
from pathlib import Path

import pytest
import research_os.cycle as cycle_module

from research_os.cycle import (
    advance_cycle,
    load_cycle_manifest,
    save_cycle_manifest,
    validate_cycle_artifacts,
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
from research_os.provider import CompletionResult
from research_os.sources import SourceRegistry


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


def _external_project(tmp_path: Path) -> Path:
    project = create_project(tmp_path, "Topic A", "topic-a")
    library = tmp_path / "library"
    library.mkdir()
    (library / "papers").mkdir()
    source = tmp_path / "public-source.txt"
    source.write_text("Public source with no medical identifiers.", encoding="utf-8")
    record = SourceRegistry(library / "sources.jsonl").add(
        str(source), external_api_allowed=True
    )
    link_project_sources(tmp_path, "topic-a", [record.source_id])
    return project


def test_cycle_artifact_validation_rejects_reviews_replaced_mid_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    created = advance_cycle(tmp_path, "topic-a")
    _write_candidates(project, created.run_id, checked=False)
    advance_cycle(tmp_path, "topic-a")
    _write_candidates(project, created.run_id, checked=True)
    advance_cycle(tmp_path, "topic-a")
    _write_reviews(project, created.run_id)
    advance_cycle(tmp_path, "topic-a")
    _write_meta(project, created.run_id)
    assert advance_cycle(tmp_path, "topic-a").state == "awaiting_human_decision"

    run_dir = project / "cycles" / created.run_id
    reviews = run_dir / "reviews"
    outside = tmp_path / "original-reviews"
    real_hash = cycle_module._sha256_direct_text
    replaced = False

    def replace_after_first_review(
        path: Path,
        *,
        parent: Path,
        parent_identity: tuple[int, int],
    ) -> str:
        nonlocal replaced
        digest = real_hash(
            path,
            parent=parent,
            parent_identity=parent_identity,
        )
        if parent == reviews and not replaced:
            replaced = True
            reviews.replace(outside)
            shutil.copytree(outside, reviews)
        return digest

    monkeypatch.setattr(
        cycle_module,
        "_sha256_direct_text",
        replace_after_first_review,
    )

    issues = validate_cycle_artifacts(
        run_dir,
        load_cycle_manifest(run_dir / "manifest.yaml"),
        source_ids={"src-a"},
        archive_path=project / "ideas" / "archive.yaml",
    )

    assert replaced is True
    assert any(issue.startswith("reviews:") for issue in issues)


def _candidate_json(run_id: str, source_id: str) -> str:
    idea = _idea(run_id)
    idea = IdeaRecord(
        **{**idea.__dict__, "evidence_source_ids": (source_id,)}
    )
    path_payload = {
        "schema_version": 1,
        "project_slug": "topic-a",
        "ideas": [
            {
                **idea.__dict__,
                "parent_ids": [],
                "evidence_source_ids": [source_id],
                "novelty": {
                    **idea.novelty.__dict__,
                    "queries": [],
                    "nearest_source_ids": [],
                },
                "scores": idea.scores.__dict__,
                "method_risks": list(idea.method_risks),
                "medical_safety_risks": list(idea.medical_safety_risks),
            }
        ],
    }
    return json.dumps(path_payload)


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


def test_provider_budget_reservation_rejects_a_stale_manifest(tmp_path: Path) -> None:
    project = _external_project(tmp_path)
    created = advance_cycle(tmp_path, "topic-a", max_calls=1)
    run_dir = project / "cycles" / created.run_id
    stale = load_cycle_manifest(run_dir / "manifest.yaml")
    context = cycle_module.ExternalContextSnapshot(
        path=run_dir / "context.md",
        content="bounded context",
        sha256="0" * 64,
        context_source_id="src-context",
        input_source_ids=("src-a",),
    )

    class Provider:
        base_url = "https://provider.test/v1"
        model = "test-model"
        temperature = 0.1

    cycle_module._begin_provider_call(
        project,
        run_dir,
        stale,
        provider=Provider(),
        context=context,
        stage="candidate_generation",
        system_prompt="system",
        user_prompt="user",
        expected_run_identity=cycle_module._directory_identity(run_dir),
    )

    with pytest.raises(RuntimeError, match="concurrent|changed|stale"):
        cycle_module._begin_provider_call(
            project,
            run_dir,
            stale,
            provider=Provider(),
            context=context,
            stage="candidate_generation",
            system_prompt="system",
            user_prompt="user",
            expected_run_identity=cycle_module._directory_identity(run_dir),
        )

    assert load_cycle_manifest(run_dir / "manifest.yaml").calls_used == 1


def test_abandoned_budget_lock_file_does_not_block_a_new_reservation(
    tmp_path: Path,
) -> None:
    project = _external_project(tmp_path)
    created = advance_cycle(tmp_path, "topic-a", max_calls=1)
    run_dir = project / "cycles" / created.run_id
    (run_dir / ".provider-budget.lock").write_text("stale-pid", encoding="ascii")
    manifest = load_cycle_manifest(run_dir / "manifest.yaml")
    context = cycle_module.ExternalContextSnapshot(
        path=run_dir / "context.md",
        content="bounded context",
        sha256="0" * 64,
        context_source_id="src-context",
        input_source_ids=("src-a",),
    )

    class Provider:
        base_url = "https://provider.test/v1"
        model = "test-model"
        temperature = 0.1

    updated, call_number = cycle_module._begin_provider_call(
        project,
        run_dir,
        manifest,
        provider=Provider(),
        context=context,
        stage="candidate_generation",
        system_prompt="system",
        user_prompt="user",
        expected_run_identity=cycle_module._directory_identity(run_dir),
    )

    assert call_number == 1
    assert updated.calls_used == 1


def test_live_budget_lock_rejects_a_second_process(tmp_path: Path) -> None:
    project = _external_project(tmp_path)
    created = advance_cycle(tmp_path, "topic-a")
    run_dir = project / "cycles" / created.run_id
    identity = cycle_module._directory_identity(run_dir)

    with cycle_module._provider_budget_lock(run_dir, identity):
        with pytest.raises(RuntimeError, match="another cycle process"):
            with cycle_module._provider_budget_lock(run_dir, identity):
                raise AssertionError("second lock unexpectedly acquired")


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


def test_provider_candidate_call_is_authorized_counted_and_validated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _external_project(tmp_path)
    linked_id = next(
        record.source_id
        for record in SourceRegistry(tmp_path / "library" / "sources.jsonl").records()
    )
    monkeypatch.setenv("TEST_API_KEY", "super-secret")

    class FakeProvider:
        base_url = "https://provider.test/v1"
        model = "test-model"
        temperature = 0.1

        def complete(
            self, system: str, user: str, *, external_api_allowed: bool
        ) -> CompletionResult:
            assert external_api_allowed is True
            assert "candidate" in system.lower()
            assert "External co-researcher context" in user
            return CompletionResult(
                content=_candidate_json(active_run_id[0], linked_id),
                provenance={"model": self.model, "usage": {"total_tokens": 17}},
            )

    first = advance_cycle(tmp_path, "topic-a")
    active_run_id = [first.run_id]
    action = advance_cycle(
        tmp_path,
        "topic-a",
        provider=FakeProvider(),
        allow_external_api=True,
    )

    assert action.state == "novelty_check"
    assert action.manifest.calls_used == 1
    assert (project / "cycles" / first.run_id / "candidates.yaml").is_file()
    provenance = list(
        (project / "cycles" / first.run_id / "provenance").glob("call-*.json")
    )
    assert len(provenance) == 2
    assert "super-secret" not in "".join(
        path.read_text(encoding="utf-8") for path in provenance
    )


def test_invalid_provider_output_consumes_budget_without_committing_artifact(
    tmp_path: Path,
) -> None:
    project = _external_project(tmp_path)

    class InvalidProvider:
        base_url = "https://provider.test/v1"
        model = "test-model"
        temperature = 0.1

        def complete(self, *_args: object, **_kwargs: object) -> CompletionResult:
            return CompletionResult(content="{broken", provenance={"model": self.model})

    action = advance_cycle(
        tmp_path,
        "topic-a",
        provider=InvalidProvider(),
        allow_external_api=True,
    )

    assert action.state == "blocked"
    assert action.manifest.calls_used == 1
    assert not (
        project / "cycles" / action.run_id / "candidates.yaml"
    ).exists()
    finished = list(
        (project / "cycles" / action.run_id / "provenance").glob("call-*-finished.json")
    )
    assert len(finished) == 1
    assert '"status": "invalid_output"' in finished[0].read_text(encoding="utf-8")


def test_review_provider_preflights_required_budget_before_any_dispatch(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    created = advance_cycle(tmp_path, "topic-a", max_calls=2)
    _write_candidates(project, created.run_id, checked=True)
    review_action = advance_cycle(tmp_path, "topic-a", max_calls=2)
    assert review_action.state == "independent_review"

    class ProviderThatMustNotRun:
        def complete(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("partial independent review dispatch")

    exhausted = advance_cycle(
        tmp_path,
        "topic-a",
        max_calls=2,
        provider=ProviderThatMustNotRun(),
        allow_external_api=True,
    )
    assert exhausted.state == "budget_exhausted"
    assert exhausted.manifest.calls_used == 0


def test_provider_completes_three_independent_reviews_then_meta_review(
    tmp_path: Path,
) -> None:
    project = _external_project(tmp_path)
    source_id = next(
        record.source_id
        for record in SourceRegistry(tmp_path / "library" / "sources.jsonl").records()
    )
    created = advance_cycle(tmp_path, "topic-a")
    checked = _idea(created.run_id, novelty_checked=True)
    checked = IdeaRecord(
        **{
            **checked.__dict__,
            "evidence_source_ids": (source_id,),
            "novelty": NoveltyEvidence(
                status="checked",
                queries=checked.novelty.queries,
                nearest_source_ids=(source_id,),
                differences=checked.novelty.differences,
                unresolved_overlap="",
            ),
        }
    )
    save_idea_archive(
        project / "cycles" / created.run_id / "candidates.yaml",
        IdeaArchive(1, "topic-a", (checked,)),
    )
    ready = advance_cycle(tmp_path, "topic-a")
    assert ready.state == "independent_review"
    seen_roles: list[str] = []

    class ReviewProvider:
        base_url = "https://provider.test/v1"
        model = "test-model"
        temperature = 0.1

        def complete(
            self, system: str, _user: str, *, external_api_allowed: bool
        ) -> CompletionResult:
            assert external_api_allowed
            if "meta-review" in system:
                return CompletionResult(
                    content=json.dumps(
                        {
                            "schema_version": 1,
                            "run_id": created.run_id,
                            "consensus": ["Testable with scope revision"],
                            "conflicts": ["Novelty confidence differs"],
                            "blocking_issues": [],
                            "shortlist_ids": ["idea-0001"],
                            "rationale_by_idea": {
                                "idea-0001": "Best bounded option"
                            },
                        }
                    ),
                    provenance={"model": self.model},
                )
            role = next(
                role
                for role in ("novelty", "methods", "medical-safety")
                if role in system
            )
            seen_roles.append(role)
            return CompletionResult(
                content=json.dumps(
                    {
                        "schema_version": 1,
                        "run_id": created.run_id,
                        "role": role,
                        "assessments": [_assessment("idea-0001")],
                    }
                ),
                provenance={"model": self.model},
            )

    action = advance_cycle(
        tmp_path,
        "topic-a",
        provider=ReviewProvider(),
        allow_external_api=True,
    )

    assert action.state == "awaiting_human_decision"
    assert action.manifest.calls_used == 4
    assert seen_roles == ["novelty", "methods", "medical-safety"]
    for role in seen_roles:
        assert (
            project / "cycles" / created.run_id / "reviews" / f"{role}.json"
        ).is_file()
    assert (project / "cycles" / created.run_id / "meta-review.json").is_file()


def test_provider_never_fakes_novelty_search(tmp_path: Path) -> None:
    project = _project(tmp_path)
    created = advance_cycle(tmp_path, "topic-a")
    _write_candidates(project, created.run_id, checked=False)
    novelty = advance_cycle(tmp_path, "topic-a")
    assert novelty.state == "novelty_check"

    class ProviderThatMustNotRun:
        def complete(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("provider attempted to fake novelty search")

    action = advance_cycle(
        tmp_path,
        "topic-a",
        provider=ProviderThatMustNotRun(),
        allow_external_api=True,
    )
    assert action.state == "novelty_check"
    assert action.next_action == "document_novelty"
    assert action.manifest.calls_used == 0


def test_cycle_blocks_reviews_copied_from_another_run(tmp_path: Path) -> None:
    project = _project(tmp_path)
    created = advance_cycle(tmp_path, "topic-a")
    _write_candidates(project, created.run_id, checked=True)
    assert advance_cycle(tmp_path, "topic-a").state == "independent_review"
    target_reviews = project / "cycles" / created.run_id / "reviews"
    target_reviews.mkdir()
    for role in ("novelty", "methods", "medical-safety"):
        (target_reviews / f"{role}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "run_id": "run-other",
                    "role": role,
                    "assessments": [_assessment("idea-0001")],
                }
            ),
            encoding="utf-8",
        )

    blocked = advance_cycle(tmp_path, "topic-a")

    assert blocked.state == "blocked"
    assert blocked.next_action == "repair_independent_reviews"
    assert "run_id" in blocked.reason


def test_existing_invalid_review_blocks_before_provider_dispatch(
    tmp_path: Path,
) -> None:
    project = _external_project(tmp_path)
    source_id = next(
        record.source_id
        for record in SourceRegistry(tmp_path / "library" / "sources.jsonl").records()
    )
    created = advance_cycle(tmp_path, "topic-a")
    idea = _idea(created.run_id, novelty_checked=True)
    idea = IdeaRecord(
        **{
            **idea.__dict__,
            "evidence_source_ids": (source_id,),
            "novelty": NoveltyEvidence(
                status="checked",
                queries=idea.novelty.queries,
                nearest_source_ids=(source_id,),
                differences=idea.novelty.differences,
                unresolved_overlap="",
            ),
        }
    )
    save_idea_archive(
        project / "cycles" / created.run_id / "candidates.yaml",
        IdeaArchive(1, "topic-a", (idea,)),
    )
    assert advance_cycle(tmp_path, "topic-a").state == "independent_review"
    reviews = project / "cycles" / created.run_id / "reviews"
    reviews.mkdir()
    (reviews / "novelty.json").write_text("{broken", encoding="utf-8")

    class ProviderThatMustNotRun:
        def complete(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("provider ran before existing review validation")

    blocked = advance_cycle(
        tmp_path,
        "topic-a",
        provider=ProviderThatMustNotRun(),
        allow_external_api=True,
    )

    assert blocked.state == "blocked"
    assert blocked.manifest.calls_used == 0
    assert blocked.next_action == "repair_independent_reviews"


def test_cycle_refuses_to_resume_with_tampered_journal(tmp_path: Path) -> None:
    project = _project(tmp_path)
    advance_cycle(tmp_path, "topic-a")
    journal = project / "research-journal.jsonl"
    journal.write_text(
        journal.read_text(encoding="utf-8").replace("bounded", "tampered", 1),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="journal|日志"):
        advance_cycle(tmp_path, "topic-a")


def test_state_transition_rolls_back_manifest_and_archive_if_journal_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    created = advance_cycle(tmp_path, "topic-a")
    _write_candidates(project, created.run_id)
    run_dir = project / "cycles" / created.run_id
    manifest_path = run_dir / "manifest.yaml"
    archive_path = project / "ideas" / "archive.yaml"
    manifest_before = manifest_path.read_bytes()
    archive_before = archive_path.read_bytes()
    original_record = cycle_module._record

    def fail_transition(*args: object, **kwargs: object) -> None:
        if kwargs.get("event_type") == "state_transition":
            raise OSError("simulated journal commit failure")
        original_record(*args, **kwargs)

    monkeypatch.setattr(cycle_module, "_record", fail_transition)

    with pytest.raises(OSError, match="journal commit failure"):
        advance_cycle(tmp_path, "topic-a")

    assert manifest_path.read_bytes() == manifest_before
    assert archive_path.read_bytes() == archive_before


def test_new_run_work_packet_reserves_existing_idea_ids(tmp_path: Path) -> None:
    project = _project(tmp_path)
    first = advance_cycle(tmp_path, "topic-a")
    _write_candidates(project, first.run_id)
    assert advance_cycle(tmp_path, "topic-a").state == "novelty_check"

    second = advance_cycle(tmp_path, "topic-a", new_run=True)
    packet = (
        project / "cycles" / second.run_id / "work-packet.md"
    ).read_text(encoding="utf-8")

    assert "Reserved Idea IDs: idea-0001" in packet
    assert "Suggested first ID: idea-0002" in packet


def test_provider_duplicate_idea_id_is_not_committed_in_new_run(
    tmp_path: Path,
) -> None:
    project = _external_project(tmp_path)
    source_id = next(
        record.source_id
        for record in SourceRegistry(tmp_path / "library" / "sources.jsonl").records()
    )
    first = advance_cycle(tmp_path, "topic-a")
    idea = _idea(first.run_id)
    idea = IdeaRecord(
        **{**idea.__dict__, "evidence_source_ids": (source_id,)}
    )
    save_idea_archive(
        project / "cycles" / first.run_id / "candidates.yaml",
        IdeaArchive(1, "topic-a", (idea,)),
    )
    assert advance_cycle(tmp_path, "topic-a").state == "novelty_check"
    second = advance_cycle(tmp_path, "topic-a", new_run=True)

    class DuplicateProvider:
        base_url = "https://provider.test/v1"
        model = "test-model"
        temperature = 0.1

        def complete(self, *_args: object, **_kwargs: object) -> CompletionResult:
            return CompletionResult(
                content=_candidate_json(second.run_id, source_id),
                provenance={"model": self.model},
            )

    blocked = advance_cycle(
        tmp_path,
        "topic-a",
        provider=DuplicateProvider(),
        allow_external_api=True,
    )

    assert blocked.state == "blocked"
    assert "belongs to another run" in blocked.reason
    assert not (project / "cycles" / second.run_id / "candidates.yaml").exists()


def test_run_directory_replacement_during_candidate_load_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    created = advance_cycle(tmp_path, "topic-a")
    _write_candidates(project, created.run_id)
    run_dir = project / "cycles" / created.run_id
    moved = tmp_path / "moved-run"
    original_load = cycle_module._load_candidates
    sentinel = b"replacement sentinel\n"
    replaced = False

    def replace_then_load(*args, **kwargs):
        nonlocal replaced
        if not replaced:
            replaced = True
            run_dir.rename(moved)
            run_dir.mkdir()
            (run_dir / "manifest.yaml").write_bytes(sentinel)
            (run_dir / "candidates.yaml").write_bytes(
                (moved / "candidates.yaml").read_bytes()
            )
        return original_load(*args, **kwargs)

    monkeypatch.setattr(cycle_module, "_load_candidates", replace_then_load)

    blocked = advance_cycle(tmp_path, "topic-a")

    assert blocked.state == "blocked"
    assert "replaced" in blocked.reason or "changed" in blocked.reason
    assert (run_dir / "manifest.yaml").read_bytes() == sentinel
    archive = load_idea_archive(
        project / "ideas" / "archive.yaml", allowed_source_ids={"src-a"}
    )
    assert archive.ideas == ()


def test_run_directory_replacement_during_provider_call_is_not_written(
    tmp_path: Path,
) -> None:
    project = _external_project(tmp_path)
    source_id = next(
        record.source_id
        for record in SourceRegistry(tmp_path / "library" / "sources.jsonl").records()
    )
    created = advance_cycle(tmp_path, "topic-a")
    run_dir = project / "cycles" / created.run_id
    moved = tmp_path / "provider-moved-run"
    sentinel = b"replacement sentinel\n"

    class ReplacingProvider:
        base_url = "https://provider.test/v1"
        model = "test-model"
        temperature = 0.1

        def complete(self, *_args: object, **_kwargs: object) -> CompletionResult:
            run_dir.rename(moved)
            run_dir.mkdir()
            (run_dir / "manifest.yaml").write_bytes(sentinel)
            return CompletionResult(
                content=_candidate_json(created.run_id, source_id),
                provenance={"model": self.model},
            )

    with pytest.raises(OSError, match="replaced|changed"):
        advance_cycle(
            tmp_path,
            "topic-a",
            provider=ReplacingProvider(),
            allow_external_api=True,
        )

    assert (run_dir / "manifest.yaml").read_bytes() == sentinel
    assert sorted(path.name for path in run_dir.iterdir()) == ["manifest.yaml"]


def test_provider_does_not_overwrite_candidate_created_during_call(
    tmp_path: Path,
) -> None:
    project = _external_project(tmp_path)
    source_id = next(
        record.source_id
        for record in SourceRegistry(tmp_path / "library" / "sources.jsonl").records()
    )
    created = advance_cycle(tmp_path, "topic-a")
    candidates_path = project / "cycles" / created.run_id / "candidates.yaml"
    human_bytes = (_candidate_json(created.run_id, source_id) + "\n").encode("utf-8")

    class SlowProvider:
        base_url = "https://provider.test/v1"
        model = "test-model"
        temperature = 0.1

        def complete(self, *_args: object, **_kwargs: object) -> CompletionResult:
            candidates_path.write_bytes(human_bytes)
            return CompletionResult(
                content=_candidate_json(created.run_id, source_id),
                provenance={"model": self.model},
            )

    action = advance_cycle(
        tmp_path,
        "topic-a",
        provider=SlowProvider(),
        allow_external_api=True,
    )

    assert action.state == "blocked"
    assert "appeared" in action.reason or "overwrite" in action.reason
    assert candidates_path.read_bytes() == human_bytes
