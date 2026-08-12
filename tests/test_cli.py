from pathlib import Path

from research_os.cli import main


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
