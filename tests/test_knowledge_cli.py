from __future__ import annotations

import json
from pathlib import Path

import yaml

from research_os.cli import main
from research_os.project import create_project
from research_os.sources import SourceRegistry


def _entry(record) -> dict[str, object]:
    return {
        "source_id": record.source_id,
        "canonical": record.canonical,
        "title": "Calibration and external validation",
        "authors": ["Methods Group"],
        "year": 2026,
        "source_type": "paper",
        "venue": "Methods Journal",
        "topics": ["medical-ai", "evaluation"],
        "methods": ["calibration", "external-validation"],
        "stages": ["experiment-design", "review"],
        "priority": "core",
        "verification": {
            "metadata": "verified",
            "abstract": "verified",
            "fulltext": "unverified",
        },
        "reviewed_at": "2026-08-12",
        "status": "active",
        "superseded_by": "",
        "access_url": f"https://doi.org/{record.canonical}",
        "license": "unknown",
        "notes": "",
    }


def _workspace(tmp_path: Path) -> tuple[Path, str]:
    for name in ("library", "projects", "inbox"):
        (tmp_path / name).mkdir()
    create_project(tmp_path, "Medical reasoning", "medical-reasoning")
    root = tmp_path / "library" / "knowledge"
    (root / "cards").mkdir(parents=True)
    (root / "playbooks").mkdir()
    record = SourceRegistry(tmp_path / "library" / "sources.jsonl").add(
        "doi:10.1000/calibration"
    )
    (root / "catalog.yaml").write_text(
        yaml.safe_dump(
            {"schema_version": 1, "entries": [_entry(record)]},
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (root / "aliases.yaml").write_text(
        yaml.safe_dump(
            {"schema_version": 1, "aliases": {record.source_id: ["reliability"]}},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (root / "playbooks" / "evaluation-and-ablation.md").write_text(
        "# Evaluation\n", encoding="utf-8"
    )
    return tmp_path, record.source_id


def test_kb_search_json_is_machine_readable_and_deterministic(
    tmp_path: Path, capsys
) -> None:
    workspace, source_id = _workspace(tmp_path)

    code = main(
        [
            "kb",
            "search",
            "calibration",
            "--format",
            "json",
            "--workspace",
            str(workspace),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output[0]["source_id"] == source_id
    assert output[0]["score"] == 12
    assert output[0]["verification_scope"] == "abstract"


def test_kb_search_text_explains_evidence_link_boundary(
    tmp_path: Path, capsys
) -> None:
    workspace, source_id = _workspace(tmp_path)

    code = main(
        ["kb", "search", "reliability", "--workspace", str(workspace)]
    )

    output = capsys.readouterr().out
    assert code == 0
    assert source_id in output
    assert "paper-intake" in output
    assert "不能直接作为课题引用证据" in output


def test_kb_search_valid_empty_result_has_next_query_hint(
    tmp_path: Path, capsys
) -> None:
    workspace, _ = _workspace(tmp_path)

    code = main(["kb", "search", "no-such-term", "--workspace", str(workspace)])

    output = capsys.readouterr().out
    assert code == 0
    assert "没有匹配" in output
    assert "调整关键词或过滤条件" in output


def test_kb_doctor_returns_two_for_corrupt_catalog(tmp_path: Path, capsys) -> None:
    workspace, _ = _workspace(tmp_path)
    (workspace / "library" / "knowledge" / "catalog.yaml").write_text(
        "entries: [", encoding="utf-8"
    )

    code = main(["kb", "doctor", "--workspace", str(workspace)])

    captured = capsys.readouterr()
    assert code == 2
    assert "FAIL" in captured.out


def test_kb_recommend_json_never_claims_global_source_is_linked(
    tmp_path: Path, capsys
) -> None:
    workspace, source_id = _workspace(tmp_path)

    code = main(
        [
            "kb",
            "recommend",
            "--project",
            "medical-reasoning",
            "--format",
            "json",
            "--workspace",
            str(workspace),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output[0]["source_id"] == source_id
    assert "paper-intake" in output[0]["cannot_use_for"]
