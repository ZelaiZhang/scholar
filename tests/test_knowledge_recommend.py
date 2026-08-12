from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from research_os.knowledge_recommend import recommend_for_project
from research_os.project import create_project, load_project_manifest
from research_os.sources import SourceRegistry


def _entry(
    record,
    *,
    title: str,
    topics: list[str],
    methods: list[str],
    stages: list[str],
    priority: str = "core",
) -> dict[str, object]:
    return {
        "source_id": record.source_id,
        "canonical": record.canonical,
        "title": title,
        "authors": ["Methods Group"],
        "year": 2025,
        "source_type": "guideline" if "reporting-guideline" in methods else "paper",
        "venue": "Methods Journal",
        "topics": topics,
        "methods": methods,
        "stages": stages,
        "priority": priority,
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


def _workspace(tmp_path: Path) -> tuple[Path, str, str]:
    for directory in ("library", "projects", "inbox"):
        (tmp_path / directory).mkdir()
    create_project(tmp_path, "Medical reasoning", "medical-reasoning")
    root = tmp_path / "library" / "knowledge"
    (root / "cards").mkdir(parents=True)
    (root / "playbooks").mkdir()
    registry = SourceRegistry(tmp_path / "library" / "sources.jsonl")
    medical = registry.add("doi:10.1000/medical-method")
    guideline = registry.add("doi:10.1000/reporting-guideline")
    general = registry.add("doi:10.1000/general-method")
    catalog = {
        "schema_version": 1,
        "entries": [
            _entry(
                medical,
                title="Reliable medical AI evaluation",
                topics=["medical-ai", "evaluation"],
                methods=["calibration", "external-validation"],
                stages=["experiment-design", "review"],
            ),
            _entry(
                guideline,
                title="Diagnostic accuracy reporting",
                topics=["medical-ai", "reporting-guidelines"],
                methods=["reporting-guideline", "diagnostic-accuracy"],
                stages=["experiment-design", "writing", "review"],
            ),
            _entry(
                general,
                title="General model evaluation",
                topics=["evaluation"],
                methods=["model-evaluation"],
                stages=["experiment-design"],
                priority="background",
            ),
        ],
    }
    (root / "catalog.yaml").write_text(
        yaml.safe_dump(catalog, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (root / "aliases.yaml").write_text(
        "schema_version: 1\naliases: {}\n", encoding="utf-8"
    )
    (root / "playbooks" / "medical-ai-study.md").write_text(
        "# Medical AI study\n", encoding="utf-8"
    )
    (root / "playbooks" / "evaluation-and-ablation.md").write_text(
        "# Evaluation\n", encoding="utf-8"
    )
    reporting = root / "reporting-guidelines"
    reporting.mkdir()
    (reporting / "applicability.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "contexts": [
                    {
                        "context": "diagnostic-accuracy",
                        "guideline_source_ids": [guideline.source_id],
                        "notes": "用于诊断准确性研究的报告范围检查。",
                    }
                ],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return tmp_path, medical.source_id, guideline.source_id


def _write_medical_profile(project: Path) -> None:
    (project / "knowledge-profile.yaml").write_text(
        """schema_version: 1
domains: [medical-ai]
tracks: [diagnostic-reasoning]
study_type: diagnostic-accuracy-study
data_modalities: [text]
reporting_context: [diagnostic-accuracy]
""",
        encoding="utf-8",
    )


def test_medical_project_gets_core_playbook_and_reporting_reference(
    tmp_path: Path,
) -> None:
    workspace, medical_id, guideline_id = _workspace(tmp_path)
    project = workspace / "projects" / "medical-reasoning"
    _write_medical_profile(project)

    recommendations = recommend_for_project(
        workspace, "medical-reasoning", stage="experiment-design"
    )

    assert len(recommendations) == 3
    assert recommendations[0].source_id == medical_id
    assert recommendations[0].kind == "method-source"
    assert recommendations[1].kind == "playbook"
    assert recommendations[1].path == workspace / "library" / "knowledge" / "playbooks" / "medical-ai-study.md"
    assert recommendations[2].source_id == guideline_id
    assert recommendations[2].kind == "reporting-guideline"
    assert all(item.cannot_use_for for item in recommendations)


def test_missing_profile_returns_generic_references_and_profile_hint(
    tmp_path: Path,
) -> None:
    workspace, _, _ = _workspace(tmp_path)
    project = workspace / "projects" / "medical-reasoning"

    recommendations = recommend_for_project(
        workspace, "medical-reasoning", stage="experiment-design"
    )

    assert len(recommendations) <= 3
    assert recommendations[-1].kind == "profile-hint"
    assert "knowledge-profile.yaml" in recommendations[-1].reason
    assert not (project / "knowledge-profile.yaml").exists()


def test_corrupt_profile_fails_instead_of_guessing_from_free_text(tmp_path: Path) -> None:
    workspace, _, _ = _workspace(tmp_path)
    project = workspace / "projects" / "medical-reasoning"
    _write_medical_profile(project)
    profile = project / "knowledge-profile.yaml"
    profile.write_text(
        profile.read_text(encoding="utf-8").replace(
            "diagnostic-reasoning", "unknown-track"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="tracks"):
        recommend_for_project(
            workspace, "medical-reasoning", stage="experiment-design"
        )


def test_recommendation_never_links_global_source_to_project(tmp_path: Path) -> None:
    workspace, _, _ = _workspace(tmp_path)
    project = workspace / "projects" / "medical-reasoning"
    _write_medical_profile(project)
    before = (project / "project.yaml").read_bytes()

    recommend_for_project(workspace, "medical-reasoning", stage="experiment-design")

    assert (project / "project.yaml").read_bytes() == before
    assert load_project_manifest(project).source_ids == ()
