from pathlib import Path

import pytest

import research_os.project as project_module
from research_os.project import (
    InvalidSlugError,
    ProjectExistsError,
    create_project,
    link_project_sources,
    load_project_manifest,
)


def test_create_project_instantiates_all_research_artifacts(tmp_path: Path) -> None:
    path = create_project(tmp_path, "医疗推理", "medical-reasoning")

    assert path.name == "medical-reasoning"
    assert (path / "00-research-brief.md").read_text(encoding="utf-8").startswith(
        "# 医疗推理"
    )
    assert (path / "02-evidence-ledger.yaml").exists()
    assert (path / "writing" / ".gitkeep").exists()
    assert (path / "reviews" / ".gitkeep").exists()
    assert (path / "artifacts" / ".gitkeep").exists()


def test_create_project_writes_manifest_and_start_here(tmp_path: Path) -> None:
    path = create_project(tmp_path, "医疗推理", "medical-reasoning")

    manifest = load_project_manifest(path)

    assert manifest.schema_version == 1
    assert manifest.title == "医疗推理"
    assert manifest.slug == "medical-reasoning"
    assert manifest.source_ids == ()
    assert manifest.persisted is True
    assert "research-os guide --project medical-reasoning" in (
        path / "START-HERE.md"
    ).read_text(encoding="utf-8")


def test_link_project_sources_is_ordered_and_idempotent(tmp_path: Path) -> None:
    path = create_project(tmp_path, "A", "topic-a")

    link_project_sources(tmp_path, "topic-a", ["src-b", "src-a", "src-b"])
    link_project_sources(tmp_path, "topic-a", ["src-a"])

    assert load_project_manifest(path).source_ids == ("src-b", "src-a")


def test_legacy_project_manifest_falls_back_to_brief_title(tmp_path: Path) -> None:
    project = tmp_path / "projects" / "legacy"
    project.mkdir(parents=True)
    (project / "00-research-brief.md").write_text(
        "# 旧课题\n", encoding="utf-8"
    )

    manifest = load_project_manifest(project, allow_legacy=True)

    assert manifest.title == "旧课题"
    assert manifest.slug == "legacy"
    assert manifest.source_ids == ()
    assert manifest.persisted is False


def test_create_project_refuses_to_overwrite(tmp_path: Path) -> None:
    create_project(tmp_path, "A", "topic-a")

    with pytest.raises(ProjectExistsError):
        create_project(tmp_path, "A", "topic-a")


@pytest.mark.parametrize("slug", ["", "Medical Topic", "../escape", "中文课题", "a_b"])
def test_create_project_rejects_unsafe_slug(tmp_path: Path, slug: str) -> None:
    with pytest.raises(InvalidSlugError):
        create_project(tmp_path, "A", slug)


def test_project_templates_do_not_depend_on_repository_relative_module_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_installed_module = tmp_path / "site-packages" / "research_os" / "project.py"
    monkeypatch.setattr(project_module, "__file__", str(fake_installed_module))

    path = create_project(tmp_path / "workspace", "Packaged", "packaged")

    assert (path / "00-research-brief.md").read_text(encoding="utf-8").startswith(
        "# Packaged"
    )
