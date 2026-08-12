import json
from pathlib import Path

import pytest

from research_os.journal import append_event, validate_journal


def make_artifact(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_journal_is_hash_chained_and_detects_tampering(tmp_path: Path) -> None:
    first_artifact = make_artifact(
        tmp_path, "cycles/run-a/manifest.yaml", "state: prepared\n"
    )
    second_artifact = make_artifact(
        tmp_path, "cycles/run-a/work-packet.md", "# Work\n"
    )
    journal = tmp_path / "research-journal.jsonl"

    first = append_event(
        journal,
        event_type="run_created",
        run_id="run-a",
        actor="system",
        artifact_path="cycles/run-a/manifest.yaml",
        artifact_hash="a" * 64,
        summary="created",
    )
    second = append_event(
        journal,
        event_type="work_packet_created",
        run_id="run-a",
        actor="system",
        artifact_path="cycles/run-a/work-packet.md",
        artifact_hash="b" * 64,
        summary="prepared",
    )

    assert first.sequence == 1
    assert second.sequence == 2
    assert second.previous_event_hash == first.event_hash
    assert validate_journal(journal, project_root=tmp_path) == ()
    assert first_artifact.is_file() and second_artifact.is_file()

    rows = [
        json.loads(line)
        for line in journal.read_text(encoding="utf-8").splitlines()
    ]
    rows[0]["summary"] = "tampered"
    journal.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    assert any(
        "哈希" in issue for issue in validate_journal(journal, project_root=tmp_path)
    )


def test_journal_rejects_broken_sequence_and_external_artifact(
    tmp_path: Path,
) -> None:
    journal = tmp_path / "research-journal.jsonl"
    outside = tmp_path.parent / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    journal.write_text(
        json.dumps(
            {
                "sequence": 2,
                "event_type": "run_created",
                "run_id": "run-a",
                "created_at": "2026-08-12T00:00:00+00:00",
                "actor": "system",
                "artifact_path": "../outside.md",
                "artifact_hash": "a" * 64,
                "summary": "bad",
                "previous_event_hash": "",
                "event_hash": "b" * 64,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    issues = validate_journal(journal, project_root=tmp_path)

    assert any("序号" in issue for issue in issues)
    assert any("越出课题目录" in issue for issue in issues)


def test_journal_does_not_accept_hidden_reasoning_fields(tmp_path: Path) -> None:
    journal = tmp_path / "research-journal.jsonl"

    with pytest.raises(TypeError):
        append_event(
            journal,
            event_type="run_created",
            run_id="run-a",
            actor="system",
            artifact_path="cycles/run-a/manifest.yaml",
            artifact_hash="a" * 64,
            summary="created",
            reasoning="private chain",  # type: ignore[call-arg]
        )


def test_append_refuses_to_extend_corrupt_journal(tmp_path: Path) -> None:
    journal = tmp_path / "research-journal.jsonl"
    journal.write_text("not-json\n", encoding="utf-8")

    with pytest.raises(ValueError, match="损坏"):
        append_event(
            journal,
            event_type="run_created",
            run_id="run-a",
            actor="system",
            artifact_path="cycles/run-a/manifest.yaml",
            artifact_hash="a" * 64,
            summary="created",
        )
