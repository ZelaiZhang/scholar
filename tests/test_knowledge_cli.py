from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from research_os.cli import main
from research_os.project import create_project
from research_os.sources import SourceRegistry


ROOT = Path(__file__).resolve().parents[1]


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


@pytest.mark.parametrize(
    ("query", "expected_title"),
    [
        ("诊断准确性", "STARD-AI"),
        ("思维链", "Chain-of-Thought Prompting"),
        ("微调量化", "QLoRA"),
    ],
)
def test_bundled_kb_search_supports_chinese_queries(
    query: str, expected_title: str, capsys
) -> None:
    code = main(
        [
            "kb",
            "search",
            query,
            "--format",
            "json",
            "--workspace",
            str(ROOT),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert expected_title in payload[0]["title"]
    assert "alias" in payload[0]["matched_fields"]


def test_kb_doctor_returns_two_for_corrupt_catalog(tmp_path: Path, capsys) -> None:
    workspace, _ = _workspace(tmp_path)
    (workspace / "library" / "knowledge" / "catalog.yaml").write_text(
        "entries: [", encoding="utf-8"
    )

    code = main(["kb", "doctor", "--workspace", str(workspace)])

    captured = capsys.readouterr()
    assert code == 2
    assert "FAIL" in captured.out


def test_kb_gaps_json_is_read_only_and_machine_readable(tmp_path: Path, capsys) -> None:
    workspace, source_id = _workspace(tmp_path)
    catalog = workspace / "library" / "knowledge" / "catalog.yaml"
    project_manifest = workspace / "projects" / "medical-reasoning" / "project.yaml"
    catalog_before = catalog.read_bytes()
    project_before = project_manifest.read_bytes()

    code = main(
        [
            "kb",
            "gaps",
            "--as-of",
            "2026-08-12",
            "--format",
            "json",
            "--workspace",
            str(workspace),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload == [
        {
            "kind": "missing-card",
            "source_id": source_id,
            "title": "Calibration and external validation",
            "priority": 3,
            "reason": "来源已核验摘要或全文，但尚无结构化知识卡。",
            "next_action": (
                f"$paper-deep-read 为 {source_id} 生成逐事实带 locator 的知识卡。"
            ),
            "access_url": "https://doi.org/10.1000/calibration",
        }
    ]
    assert catalog.read_bytes() == catalog_before
    assert project_manifest.read_bytes() == project_before


def test_kb_gaps_text_is_actionable_and_filterable(tmp_path: Path, capsys) -> None:
    workspace, source_id = _workspace(tmp_path)

    code = main(
        [
            "kb",
            "gaps",
            "--kind",
            "missing-card",
            "--topic",
            "medical-ai",
            "--as-of",
            "2026-08-12",
            "--workspace",
            str(workspace),
        ]
    )

    output = capsys.readouterr().out
    assert code == 0
    assert "1 项" in output
    assert source_id in output
    assert "$paper-deep-read" in output
    assert "只读" in output


@pytest.mark.parametrize(
    ("extra_args", "message"),
    [
        (["--as-of", "not-a-date"], "as-of"),
        (["--limit", "0"], "limit"),
    ],
)
def test_kb_gaps_invalid_date_or_limit_returns_two(
    tmp_path: Path, capsys, extra_args: list[str], message: str
) -> None:
    workspace, _ = _workspace(tmp_path)

    code = main(
        ["kb", "gaps", *extra_args, "--workspace", str(workspace)]
    )

    captured = capsys.readouterr()
    assert code == 2
    assert message in captured.err


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
