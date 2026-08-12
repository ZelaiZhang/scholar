from pathlib import Path

import pytest

import research_os.cli as cli_module
from research_os.cli import build_parser
from research_os.cli import main
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
