from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from research_os.knowledge import (
    load_knowledge_base,
    load_profile,
    inspect_knowledge_base,
)
from research_os.sources import SourceRegistry


CARD_SECTIONS = (
    "阅读范围",
    "研究问题与设置",
    "方法",
    "已报告事实",
    "作者报告的限制",
    "模型综合推断",
    "可迁移方法建议",
    "不应外推的结论",
    "与其他来源的关系",
    "人工备注",
)


def _catalog_entry(
    source_id: str,
    canonical: str,
    *,
    title: str = "Calibration for medical AI",
    fulltext: str = "unverified",
    abstract: str = "verified",
    status: str = "active",
    superseded_by: str = "",
    reviewed_at: str = "2026-08-12",
) -> dict[str, object]:
    return {
        "source_id": source_id,
        "canonical": canonical,
        "title": title,
        "authors": ["Ada Researcher"],
        "year": 2025,
        "source_type": "paper",
        "venue": "Journal of Reliable AI",
        "topics": ["medical-ai", "evaluation"],
        "methods": ["calibration", "external-validation"],
        "stages": ["experiment-design", "review"],
        "priority": "core",
        "verification": {
            "metadata": "verified",
            "abstract": abstract,
            "fulltext": fulltext,
        },
        "reviewed_at": reviewed_at,
        "status": status,
        "superseded_by": superseded_by,
        "access_url": f"https://doi.org/{canonical}",
        "license": "unknown",
        "notes": "",
    }


def _make_workspace(tmp_path: Path, *, canonical: str = "10.1000/calibration"):
    (tmp_path / "library" / "knowledge" / "cards").mkdir(parents=True)
    registry = SourceRegistry(tmp_path / "library" / "sources.jsonl")
    record = registry.add(f"doi:{canonical}")
    return record


def _write_catalog(root: Path, entries: list[dict[str, object]]) -> None:
    payload = {"schema_version": 1, "entries": entries}
    (root / "library" / "knowledge" / "catalog.yaml").write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (root / "library" / "knowledge" / "aliases.yaml").write_text(
        "schema_version: 1\naliases: {}\n",
        encoding="utf-8",
    )


def _write_card(
    root: Path,
    source_id: str,
    *,
    reading_scope: str,
    locators: list[str],
) -> None:
    front_matter = yaml.safe_dump(
        {
            "schema_version": 1,
            "source_id": source_id,
            "title": "Calibration for medical AI",
            "reading_scope": reading_scope,
            "locators": locators,
            "reviewed_at": "2026-08-12",
        },
        allow_unicode=True,
        sort_keys=False,
    ).strip()
    body = "\n\n".join(f"## {section}\n\n内容。" for section in CARD_SECTIONS)
    (root / "library" / "knowledge" / "cards" / f"{source_id}.md").write_text(
        f"---\n{front_matter}\n---\n\n# Calibration for medical AI\n\n{body}\n",
        encoding="utf-8",
    )


def test_load_knowledge_base_rejects_unknown_catalog_key(tmp_path: Path) -> None:
    record = _make_workspace(tmp_path)
    entry = _catalog_entry(record.source_id, record.canonical)
    entry["invented"] = True
    _write_catalog(tmp_path, [entry])

    with pytest.raises(ValueError, match="未知字段"):
        load_knowledge_base(tmp_path)


def test_load_knowledge_base_rejects_duplicate_canonical(tmp_path: Path) -> None:
    first = _make_workspace(tmp_path)
    second = SourceRegistry(tmp_path / "library" / "sources.jsonl").add(
        "doi:10.1000/other"
    )
    _write_catalog(
        tmp_path,
        [
            _catalog_entry(first.source_id, first.canonical),
            _catalog_entry(second.source_id, first.canonical),
        ],
    )

    with pytest.raises(ValueError, match="canonical 重复"):
        load_knowledge_base(tmp_path)


def test_catalog_source_must_match_registry_canonical(tmp_path: Path) -> None:
    record = _make_workspace(tmp_path)
    _write_catalog(
        tmp_path,
        [_catalog_entry(record.source_id, "10.1000/not-the-registry-value")],
    )

    with pytest.raises(ValueError, match="与来源登记表不一致"):
        load_knowledge_base(tmp_path)


def test_fulltext_verified_requires_fulltext_card_and_locator(tmp_path: Path) -> None:
    record = _make_workspace(tmp_path)
    _write_catalog(
        tmp_path,
        [_catalog_entry(record.source_id, record.canonical, fulltext="verified")],
    )
    _write_card(
        tmp_path,
        record.source_id,
        reading_scope="abstract",
        locators=["abstract"],
    )

    with pytest.raises(ValueError, match="全文定位"):
        load_knowledge_base(tmp_path)


def test_valid_fulltext_card_loads_with_fixed_sections(tmp_path: Path) -> None:
    record = _make_workspace(tmp_path)
    _write_catalog(
        tmp_path,
        [_catalog_entry(record.source_id, record.canonical, fulltext="verified")],
    )
    _write_card(
        tmp_path,
        record.source_id,
        reading_scope="fulltext",
        locators=["p. 4, Results", "p. 8, Limitations"],
    )

    kb = load_knowledge_base(tmp_path)

    assert kb.entries[0].source_id == record.source_id
    assert kb.cards[record.source_id].reading_scope == "fulltext"


def test_superseded_entry_requires_valid_acyclic_target(tmp_path: Path) -> None:
    first = _make_workspace(tmp_path)
    second = SourceRegistry(tmp_path / "library" / "sources.jsonl").add(
        "doi:10.1000/other"
    )
    _write_catalog(
        tmp_path,
        [
            _catalog_entry(
                first.source_id,
                first.canonical,
                status="superseded",
                superseded_by=second.source_id,
            ),
            _catalog_entry(
                second.source_id,
                second.canonical,
                status="superseded",
                superseded_by=first.source_id,
            ),
        ],
    )

    with pytest.raises(ValueError, match="替代关系存在环"):
        load_knowledge_base(tmp_path)


def test_profile_uses_strict_schema_and_controlled_values(tmp_path: Path) -> None:
    profile = tmp_path / "knowledge-profile.yaml"
    profile.write_text(
        """schema_version: 1
domains: [medical-ai]
tracks: [diagnostic-reasoning, rag]
study_type: offline-model-evaluation
data_modalities: [text]
reporting_context: [diagnostic-accuracy]
""",
        encoding="utf-8",
    )

    loaded = load_profile(profile)
    assert loaded.domains == ("medical-ai",)

    profile.write_text(profile.read_text(encoding="utf-8").replace("rag", "magic"), encoding="utf-8")
    with pytest.raises(ValueError, match="tracks"):
        load_profile(profile)


def test_knowledge_doctor_warns_when_review_is_older_than_365_days(
    tmp_path: Path,
) -> None:
    record = _make_workspace(tmp_path)
    _write_catalog(
        tmp_path,
        [
            _catalog_entry(
                record.source_id,
                record.canonical,
                reviewed_at="2024-01-01",
            )
        ],
    )

    report = inspect_knowledge_base(tmp_path, today=date(2026, 8, 12))

    assert report.exit_code == 0
    assert any(issue.level == "WARN" and "超过 365 天" in issue.message for issue in report.issues)


def test_knowledge_root_cannot_be_a_symlink(tmp_path: Path) -> None:
    target = tmp_path / "outside"
    (target / "cards").mkdir(parents=True)
    (tmp_path / "library").mkdir(exist_ok=True)
    link = tmp_path / "library" / "knowledge"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")

    with pytest.raises(ValueError, match="符号链接|目录联接"):
        load_knowledge_base(tmp_path)
