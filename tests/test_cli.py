from pathlib import Path
import os
import subprocess

import pytest

import research_os.cli as cli_module
from research_os.cli import _configure_windows_utf8, build_parser, main
from research_os.project import create_project, load_project_manifest
from research_os.provider import CompletionResult


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
