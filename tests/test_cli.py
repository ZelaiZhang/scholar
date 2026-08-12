from pathlib import Path
import json
import os
import subprocess

import pytest

import research_os.cli as cli_module
from research_os.cli import _configure_windows_utf8, build_parser, main
from research_os.project import create_project, link_project_sources, load_project_manifest
from research_os.provider import CompletionResult
from research_os.ideas import (
    IdeaArchive,
    IdeaRecord,
    IdeaScores,
    NoveltyEvidence,
    load_idea_archive,
    save_idea_archive,
)
from research_os.cycle import advance_cycle, load_cycle_manifest


def test_cli_creates_project_and_registers_note(
    tmp_path: Path, capsys
) -> None:
    assert (
        main(
            [
                "new-project",
                "--workspace",
                str(tmp_path),
                "--title",
                "医疗推理",
                "--slug",
                "medical-reasoning",
            ]
        )
        == 0
    )
    note = tmp_path / "note.md"
    note.write_text("公开资料笔记", encoding="utf-8")

    assert (
        main(
            [
                "add-source",
                str(note),
                "--workspace",
                str(tmp_path),
                "--notes",
                "seed",
            ]
        )
        == 0
    )

    assert (
        tmp_path / "projects/medical-reasoning/00-research-brief.md"
    ).exists()
    assert "src-" in capsys.readouterr().out


def test_cli_turns_duplicate_project_into_concise_error(
    tmp_path: Path, capsys
) -> None:
    args = [
        "new-project",
        "--workspace",
        str(tmp_path),
        "--title",
        "A",
        "--slug",
        "topic-a",
    ]
    assert main(args) == 0

    exit_code = main(args)

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "错误:" in captured.err
    assert "课题已存在" in captured.err
    assert "Traceback" not in captured.err


def test_cli_turns_missing_pdf_into_concise_error(
    tmp_path: Path, capsys
) -> None:
    exit_code = main(
        [
            "extract-pdf",
            str(tmp_path / "missing.pdf"),
            "--output",
            str(tmp_path / "out.md"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "错误:" in captured.err
    assert "missing.pdf" in captured.err


def test_model_call_requires_source_level_authorization_arguments() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [
                "model-call",
                "--base-url",
                "https://example.test/v1",
                "--model",
                "model",
                "--api-key-env",
                "TEST_KEY",
                "--system",
                "system.md",
                "--user",
                "user.md",
                "--output",
                "out.md",
                "--allow-external-api",
            ]
        )


def test_cycle_cli_creates_and_resumes_one_local_action(
    tmp_path: Path, capsys
) -> None:
    create_project(tmp_path, "A", "topic-a")
    args = ["cycle", "--project", "topic-a", "--workspace", str(tmp_path)]

    assert main(args) == 0
    first = capsys.readouterr().out
    assert "状态: candidate_generation" in first
    assert "调用: 0/6" in first
    assert first.count("下一步:") == 1
    run_id = next(line.split(": ", 1)[1] for line in first.splitlines() if line.startswith("Run: "))

    assert main(args) == 0
    second = capsys.readouterr().out
    assert f"Run: {run_id}" in second


def test_cycle_cli_rejects_invalid_bounds_and_provider_without_permission(
    tmp_path: Path, capsys
) -> None:
    create_project(tmp_path, "A", "topic-a")
    assert (
        main(
            [
                "cycle",
                "--project",
                "topic-a",
                "--max-ideas",
                "0",
                "--workspace",
                str(tmp_path),
            ]
        )
        == 2
    )
    assert "max_ideas" in capsys.readouterr().err

    assert (
        main(
            [
                "cycle",
                "--project",
                "topic-a",
                "--provider-role",
                "economy",
                "--workspace",
                str(tmp_path),
            ]
        )
        == 2
    )
    assert "--allow-external-api" in capsys.readouterr().err


def _shortlisted_idea() -> IdeaRecord:
    return IdeaRecord(
        idea_id="idea-0001",
        parent_ids=(),
        title="A testable idea",
        scientific_question="Does X improve Y?",
        hypothesis="X improves Y.",
        contribution="A bounded comparison.",
        evidence_source_ids=(),
        novelty=NoveltyEvidence(
            status="checked",
            queries=("X Y comparison",),
            nearest_source_ids=("src-neighbour",),
            differences="Uses a different evidence gate.",
            unresolved_overlap="",
        ),
        scores=IdeaScores(8, 7, 7, 6),
        method_risks=("Leakage",),
        medical_safety_risks=("No clinical claim",),
        failure_criterion="Y does not improve.",
        external_experiment="Evaluate in an independent repository.",
        status="shortlisted",
        generated_by_run="run-test",
        provenance={"generator": "fixture"},
        researcher_decision=None,
    )


def test_approve_idea_cli_is_human_only_and_records_decision(
    tmp_path: Path, capsys
) -> None:
    project = create_project(tmp_path, "A", "topic-a")
    link_project_sources(tmp_path, "topic-a", ["src-neighbour"])
    created = advance_cycle(tmp_path, "topic-a")
    candidate = IdeaRecord(
        **{
            **_shortlisted_idea().__dict__,
            "status": "draft",
            "generated_by_run": created.run_id,
        }
    )
    candidate_path = project / "cycles" / created.run_id / "candidates.yaml"
    save_idea_archive(
        candidate_path, IdeaArchive(1, "topic-a", (candidate,))
    )
    assert advance_cycle(tmp_path, "topic-a").state == "independent_review"
    reviews = project / "cycles" / created.run_id / "reviews"
    reviews.mkdir()
    assessment = {
        "idea_id": "idea-0001",
        "strengths": ["Testable"],
        "concerns": ["Scope"],
        "blocking_issues": [],
        "recommendation": "advance",
        "confidence": 4,
    }
    for role in ("novelty", "methods", "medical-safety"):
        (reviews / f"{role}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "run_id": created.run_id,
                    "role": role,
                    "assessments": [assessment],
                }
            ),
            encoding="utf-8",
        )
    assert advance_cycle(tmp_path, "topic-a").state == "meta_review"
    (project / "cycles" / created.run_id / "meta-review.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": created.run_id,
                "consensus": ["Testable"],
                "conflicts": [],
                "blocking_issues": [],
                "shortlist_ids": ["idea-0001"],
                "rationale_by_idea": {"idea-0001": "Best bounded option"},
            }
        ),
        encoding="utf-8",
    )
    assert advance_cycle(tmp_path, "topic-a").state == "awaiting_human_decision"
    archive_path = project / "ideas" / "archive.yaml"

    exit_code = main(
        [
            "approve-idea",
            "--project",
            "topic-a",
            "--idea",
            "idea-0001",
            "--reason",
            "Evidence and scope are acceptable",
            "--workspace",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert "idea-0001" in capsys.readouterr().out
    selected = load_idea_archive(
        archive_path, allowed_source_ids={"src-neighbour"}
    ).ideas[0]
    assert selected.status == "selected"
    assert selected.researcher_decision is not None
    assert selected.researcher_decision.actor == "researcher"
    assert load_cycle_manifest(
        project / "cycles" / created.run_id / "manifest.yaml"
    ).state == "completed"
    assert (project / "research-journal.jsonl").is_file()


def test_approve_idea_cli_rejects_handcrafted_shortlist_without_active_review(
    tmp_path: Path, capsys
) -> None:
    project = create_project(tmp_path, "A", "topic-a")
    link_project_sources(tmp_path, "topic-a", ["src-neighbour"])
    save_idea_archive(
        project / "ideas" / "archive.yaml",
        IdeaArchive(1, "topic-a", (_shortlisted_idea(),)),
    )

    exit_code = main(
        [
            "approve-idea",
            "--project",
            "topic-a",
            "--idea",
            "idea-0001",
            "--reason",
            "Bypass attempt",
            "--workspace",
            str(tmp_path),
        ]
    )

    assert exit_code == 2
    error = capsys.readouterr().err
    assert "active" in error or "run" in error


def test_validate_ledger_rejects_source_id_missing_from_registry(
    tmp_path: Path, capsys
) -> None:
    ledger = tmp_path / "ledger.yaml"
    ledger.write_text(
        """claims:
  - claim_id: C001
    statement: unsupported
    type: fact
    status: verified
    support:
      - source_id: src-invented
        locator: p. 1
    opposition: []
    confidence: high
    limitations: none stated
""",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "validate-ledger",
            str(ledger),
            "--workspace",
            str(tmp_path),
        ]
    )

    assert exit_code == 1
    assert "unknown_source_id" in capsys.readouterr().out


def test_validate_ledger_refuses_to_overwrite_input_or_existing_report(
    tmp_path: Path, capsys
) -> None:
    ledger = tmp_path / "ledger.yaml"
    original = "claims: []\n"
    ledger.write_text(original, encoding="utf-8")

    assert (
        main(
            [
                "validate-ledger",
                str(ledger),
                "--workspace",
                str(tmp_path),
                "--report",
                str(ledger),
            ]
        )
        == 2
    )
    assert ledger.read_text(encoding="utf-8") == original

    report = tmp_path / "report.md"
    report.write_text("manual report", encoding="utf-8")
    assert (
        main(
            [
                "validate-ledger",
                str(ledger),
                "--workspace",
                str(tmp_path),
                "--report",
                str(report),
            ]
        )
        == 2
    )
    assert report.read_text(encoding="utf-8") == "manual report"
    assert "错误:" in capsys.readouterr().err


def test_extract_pdf_refuses_to_replace_its_source_even_with_force(
    tmp_path: Path, capsys
) -> None:
    source = tmp_path / "paper.pdf"
    original = b"%PDF-test"
    source.write_bytes(original)

    exit_code = main(
        [
            "extract-pdf",
            str(source),
            "--output",
            str(source),
            "--force",
        ]
    )

    assert exit_code == 2
    assert source.read_bytes() == original
    error = capsys.readouterr().err
    assert "错误:" in error
    assert "不能与输入 PDF 相同" in error


def test_model_call_sends_the_exact_snapshot_checked_by_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system = tmp_path / "system.md"
    user = tmp_path / "user.md"
    output = tmp_path / "out.md"
    system.write_text("changed system", encoding="utf-8")
    user.write_text("changed user", encoding="utf-8")
    captured: dict[str, str] = {}

    monkeypatch.setattr(
        cli_module,
        "load_authorized_external_texts",
        lambda *_: ("verified system", "verified user"),
        raising=False,
    )

    class FakeProvider:
        def __init__(self, *args, **kwargs):
            pass

        def complete(self, system_text, user_text, *, external_api_allowed):
            captured["system"] = system_text
            captured["user"] = user_text
            return CompletionResult("ok", {"model": "fake"})

    monkeypatch.setattr(cli_module, "OpenAICompatibleProvider", FakeProvider)

    exit_code = main(
        [
            "model-call",
            "--workspace",
            str(tmp_path),
            "--base-url",
            "https://example.test/v1",
            "--model",
            "fake",
            "--api-key-env",
            "FAKE_KEY",
            "--system",
            str(system),
            "--user",
            str(user),
            "--output",
            str(output),
            "--source-id",
            "src-system",
            "--source-id",
            "src-user",
            "--allow-external-api",
        ]
    )

    assert exit_code == 0
    assert captured == {"system": "verified system", "user": "verified user"}


@pytest.mark.parametrize("collision", ["system", "existing"])
def test_model_call_refuses_provenance_collisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    collision: str,
) -> None:
    output = tmp_path / "out.md"
    provenance = tmp_path / "out.md.provenance.json"
    system = provenance if collision == "system" else tmp_path / "system.md"
    user = tmp_path / "user.md"
    system.write_text("manual system", encoding="utf-8")
    user.write_text("manual user", encoding="utf-8")
    if collision == "existing":
        provenance.write_text("manual provenance", encoding="utf-8")

    monkeypatch.setattr(
        cli_module,
        "load_authorized_external_texts",
        lambda *_: ("verified system", "verified user"),
        raising=False,
    )

    exit_code = main(
        [
            "model-call",
            "--workspace",
            str(tmp_path),
            "--base-url",
            "https://example.test/v1",
            "--model",
            "fake",
            "--api-key-env",
            "FAKE_KEY",
            "--system",
            str(system),
            "--user",
            str(user),
            "--output",
            str(output),
            "--source-id",
            "src-system",
            "--source-id",
            "src-user",
            "--allow-external-api",
        ]
    )

    assert exit_code == 2
    assert system.read_text(encoding="utf-8") == "manual system"
    if collision == "existing":
        assert provenance.read_text(encoding="utf-8") == "manual provenance"
    assert not output.exists()


def test_cli_guide_recommends_project_creation_when_workspace_is_empty(
    tmp_path: Path, capsys
) -> None:
    (tmp_path / "projects").mkdir()

    assert main(["guide", "--workspace", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "new-project" in output
    assert "下一步" in output


def test_cli_guide_selects_the_only_project(tmp_path: Path, capsys) -> None:
    create_project(tmp_path, "A", "topic-a")

    assert main(["guide", "--workspace", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "A · 科研驾驶舱" in output
    assert "$research-project-init" in output


def test_cli_guide_requires_explicit_project_when_multiple_exist(
    tmp_path: Path, capsys
) -> None:
    create_project(tmp_path, "A", "topic-a")
    create_project(tmp_path, "B", "topic-b")

    assert main(["guide", "--workspace", str(tmp_path)]) == 2

    error = capsys.readouterr().err
    assert "topic-a" in error
    assert "topic-b" in error
    assert "--project" in error


def test_cli_guide_turns_broken_project_yaml_into_concise_error(
    tmp_path: Path, capsys
) -> None:
    project = create_project(tmp_path, "A", "topic-a")
    (project / "project.yaml").write_text(
        "schema_version: [broken", encoding="utf-8"
    )

    assert (
        main(
            [
                "guide",
                "--workspace",
                str(tmp_path),
                "--project",
                "topic-a",
            ]
        )
        == 2
    )

    captured = capsys.readouterr()
    assert "YAML 无法解析" in captured.err
    assert "Traceback" not in captured.err


def test_cli_batch_import_links_sources_to_project(tmp_path: Path) -> None:
    create_project(tmp_path, "A", "topic-a")
    manifest = tmp_path / "sources.txt"
    manifest.write_text(
        "doi:10.1000/a\narXiv:2401.01234\n", encoding="utf-8"
    )

    exit_code = main(
        [
            "add-sources",
            str(manifest),
            "--workspace",
            str(tmp_path),
            "--project",
            "topic-a",
        ]
    )

    assert exit_code == 0
    project = tmp_path / "projects" / "topic-a"
    assert len(load_project_manifest(project).source_ids) == 2


def test_cli_invalid_batch_does_not_partially_register_or_link(
    tmp_path: Path,
) -> None:
    project = create_project(tmp_path, "A", "topic-a")
    manifest = tmp_path / "sources.txt"
    manifest.write_text(
        "doi:10.1000/good\nmissing.pdf\n", encoding="utf-8"
    )

    exit_code = main(
        [
            "add-sources",
            str(manifest),
            "--workspace",
            str(tmp_path),
            "--project",
            "topic-a",
        ]
    )

    assert exit_code == 2
    assert not (tmp_path / "library" / "sources.jsonl").exists()
    assert load_project_manifest(project).source_ids == ()


def test_cli_batch_rolls_back_registry_when_project_link_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = create_project(tmp_path, "A", "topic-a")
    registry_path = tmp_path / "library" / "sources.jsonl"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        '{"canonical":"10.1000/existing","content_hash":null,'
        '"external_api_allowed":false,"imported_at":"2026-01-01T00:00:00Z",'
        '"kind":"doi","metadata_status":"unverified","notes":"manual",'
        '"source_id":"src-existing"}\n',
        encoding="utf-8",
    )
    before = registry_path.read_bytes()
    manifest = tmp_path / "sources.txt"
    manifest.write_text("doi:10.1000/new\n", encoding="utf-8")
    project_manifest_path = project / "project.yaml"
    project_before = project_manifest_path.read_bytes()

    def fail_after_partial_project_write(*_args) -> None:
        project_manifest_path.write_text(
            "schema_version: 1\nsource_ids: [src-corrupt]\n", encoding="utf-8"
        )
        raise OSError("simulated disk failure")

    monkeypatch.setattr(
        cli_module, "link_project_sources", fail_after_partial_project_write
    )

    exit_code = main(
        [
            "add-sources",
            str(manifest),
            "--workspace",
            str(tmp_path),
            "--project",
            "topic-a",
        ]
    )

    assert exit_code == 2
    assert registry_path.read_bytes() == before
    assert project_manifest_path.read_bytes() == project_before
    assert load_project_manifest(project).source_ids == ()


def test_cli_rolls_back_registry_when_project_disappears_after_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = create_project(tmp_path, "A", "topic-a")
    real_resolve = cli_module.resolve_project_path
    calls = 0

    def fail_second_resolve(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("simulated project replacement")
        return real_resolve(*args, **kwargs)

    monkeypatch.setattr(cli_module, "resolve_project_path", fail_second_resolve)

    exit_code = main(
        [
            "add-source",
            "doi:10.1000/must-roll-back",
            "--workspace",
            str(tmp_path),
            "--project",
            "topic-a",
        ]
    )

    assert exit_code == 2
    assert not (tmp_path / "library" / "sources.jsonl").exists()
    assert load_project_manifest(project).source_ids == ()


def test_cli_rollback_never_writes_through_replaced_project_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = create_project(tmp_path, "A", "topic-a")
    moved_project = tmp_path / "moved-project"
    outside = tmp_path / "outside-project"
    outside.mkdir()
    outside_manifest = outside / "project.yaml"
    outside_manifest.write_text("external sentinel\n", encoding="utf-8")

    def replace_project_then_fail(*_args) -> None:
        project.rename(moved_project)
        if os.name == "nt":
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(project), str(outside)],
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            project.symlink_to(outside, target_is_directory=True)
        raise OSError("simulated replacement during linking")

    monkeypatch.setattr(
        cli_module, "link_project_sources", replace_project_then_fail
    )

    exit_code = main(
        [
            "add-source",
            "doi:10.1000/no-external-rollback",
            "--workspace",
            str(tmp_path),
            "--project",
            "topic-a",
        ]
    )

    assert exit_code == 2
    assert not (tmp_path / "library" / "sources.jsonl").exists()
    assert outside_manifest.read_text(encoding="utf-8") == "external sentinel\n"
    assert load_project_manifest(moved_project).source_ids == ()


def test_cli_rollback_never_unlinks_through_replaced_library_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_project(tmp_path, "A", "topic-a")
    library = tmp_path / "library"
    moved_library = tmp_path / "moved-library"
    outside = tmp_path / "outside-library"
    outside.mkdir()
    outside_registry = outside / "sources.jsonl"
    outside_registry.write_text("external sentinel\n", encoding="utf-8")

    def replace_library_then_fail(*_args) -> None:
        library.rename(moved_library)
        if os.name == "nt":
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(library), str(outside)],
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            library.symlink_to(outside, target_is_directory=True)
        raise OSError("simulated library replacement during linking")

    monkeypatch.setattr(
        cli_module, "link_project_sources", replace_library_then_fail
    )

    exit_code = main(
        [
            "add-source",
            "doi:10.1000/no-external-unlink",
            "--workspace",
            str(tmp_path),
            "--project",
            "topic-a",
        ]
    )

    assert exit_code == 2
    assert outside_registry.read_text(encoding="utf-8") == "external sentinel\n"
    assert (moved_library / "sources.jsonl").is_file()


def test_cli_rollback_never_unlinks_replacement_library_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_project(tmp_path, "A", "topic-a")
    library = tmp_path / "library"
    moved_library = tmp_path / "moved-library"
    replacement_registry = library / "sources.jsonl"

    def replace_library_then_fail(*_args) -> None:
        library.rename(moved_library)
        library.mkdir()
        replacement_registry.write_text(
            "replacement sentinel\n", encoding="utf-8"
        )
        raise OSError("simulated real library replacement")

    monkeypatch.setattr(
        cli_module, "link_project_sources", replace_library_then_fail
    )

    exit_code = main(
        [
            "add-source",
            "doi:10.1000/no-replacement-unlink",
            "--workspace",
            str(tmp_path),
            "--project",
            "topic-a",
        ]
    )

    assert exit_code == 2
    assert replacement_registry.read_text(encoding="utf-8") == (
        "replacement sentinel\n"
    )
    assert (moved_library / "sources.jsonl").is_file()


def test_cli_rollback_never_overwrites_replacement_project_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = create_project(tmp_path, "A", "topic-a")
    moved_project = tmp_path / "moved-project"
    replacement_manifest = project / "project.yaml"

    def replace_project_then_fail(*_args) -> None:
        project.rename(moved_project)
        project.mkdir()
        replacement_manifest.write_text(
            "replacement sentinel\n", encoding="utf-8"
        )
        raise OSError("simulated real directory replacement")

    monkeypatch.setattr(
        cli_module, "link_project_sources", replace_project_then_fail
    )

    exit_code = main(
        [
            "add-source",
            "doi:10.1000/no-replacement-overwrite",
            "--workspace",
            str(tmp_path),
            "--project",
            "topic-a",
        ]
    )

    assert exit_code == 2
    assert replacement_manifest.read_text(encoding="utf-8") == (
        "replacement sentinel\n"
    )
    assert load_project_manifest(moved_project).source_ids == ()
    assert not (tmp_path / "library" / "sources.jsonl").exists()


def test_cli_source_write_rejects_mid_command_library_link_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = create_project(tmp_path, "A", "topic-a")
    library = tmp_path / "library"
    library.mkdir()
    moved_library = tmp_path / "moved-library"
    outside = tmp_path / "outside-library"
    outside.mkdir()
    real_add = cli_module.SourceRegistry.add

    def replace_library_then_add(registry, *args, **kwargs):
        library.rename(moved_library)
        if os.name == "nt":
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(library), str(outside)],
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            library.symlink_to(outside, target_is_directory=True)
        return real_add(registry, *args, **kwargs)

    monkeypatch.setattr(
        cli_module.SourceRegistry, "add", replace_library_then_add
    )

    exit_code = main(
        [
            "add-source",
            "doi:10.1000/no-mid-command-external-write",
            "--workspace",
            str(tmp_path),
            "--project",
            "topic-a",
        ]
    )

    assert exit_code == 2
    assert not (outside / "sources.jsonl").exists()
    assert not (moved_library / "sources.jsonl").exists()
    assert load_project_manifest(project).source_ids == ()


def test_cli_project_write_rejects_mid_command_directory_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_project = create_project(tmp_path, "A", "topic-a")
    moved_project = tmp_path / "moved-project"
    real_link = cli_module.link_project_sources

    def replace_project_then_link(*args, **kwargs):
        original_project.rename(moved_project)
        create_project(tmp_path, "Replacement", "topic-a")
        return real_link(*args, **kwargs)

    monkeypatch.setattr(
        cli_module, "link_project_sources", replace_project_then_link
    )

    exit_code = main(
        [
            "add-source",
            "doi:10.1000/no-mid-command-project-write",
            "--workspace",
            str(tmp_path),
            "--project",
            "topic-a",
        ]
    )

    replacement = tmp_path / "projects" / "topic-a"
    assert exit_code == 2
    assert load_project_manifest(moved_project).source_ids == ()
    assert load_project_manifest(replacement).source_ids == ()
    assert not (tmp_path / "library" / "sources.jsonl").exists()


def test_cli_preflights_project_before_registering_single_source(
    tmp_path: Path,
) -> None:
    exit_code = main(
        [
            "add-source",
            "doi:10.1000/should-not-write",
            "--workspace",
            str(tmp_path),
            "--project",
            "missing-project",
        ]
    )

    assert exit_code == 2
    assert not (tmp_path / "library" / "sources.jsonl").exists()


def test_cli_rejects_library_directory_link_outside_workspace(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside-library"
    outside.mkdir()
    library = tmp_path / "library"
    try:
        if os.name == "nt":
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(library), str(outside)],
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            library.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"无法在当前环境创建目录链接: {exc}")

    exit_code = main(
        [
            "add-source",
            "doi:10.1000/must-stay-inside",
            "--workspace",
            str(tmp_path),
        ]
    )

    assert exit_code == 2
    assert not (outside / "sources.jsonl").exists()


def test_cli_doctor_uses_report_exit_code(tmp_path: Path, capsys) -> None:
    assert main(["doctor", "--workspace", str(tmp_path)]) == 1
    assert "[FAIL]" in capsys.readouterr().out


def test_windows_entrypoint_reconfigures_both_output_streams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStream:
        def __init__(self) -> None:
            self.calls: list[dict[str, str]] = []

        def reconfigure(self, **kwargs: str) -> None:
            self.calls.append(kwargs)

    stdout = FakeStream()
    stderr = FakeStream()
    monkeypatch.setattr(cli_module.sys, "platform", "win32")
    monkeypatch.setattr(cli_module.sys, "stdout", stdout)
    monkeypatch.setattr(cli_module.sys, "stderr", stderr)

    _configure_windows_utf8()

    assert stdout.calls == [{"encoding": "utf-8", "errors": "replace"}]
    assert stderr.calls == [{"encoding": "utf-8", "errors": "replace"}]
