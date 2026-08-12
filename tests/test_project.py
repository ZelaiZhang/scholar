from pathlib import Path
import os
import subprocess

import pytest

import research_os.project as project_module
from research_os.project import (
    InvalidSlugError,
    ProjectExistsError,
    create_project,
    link_project_sources,
    load_project_manifest,
    resolve_project_path,
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


def test_project_manifest_rejects_source_id_with_shell_syntax(
    tmp_path: Path,
) -> None:
    project = create_project(tmp_path, "A", "topic-a")
    manifest = project / "project.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "source_ids: []",
            "source_ids:\n- 'src-safe; Write-Output injected'",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source_ids"):
        load_project_manifest(project)


def test_link_project_sources_rejects_unsafe_id_without_changing_manifest(
    tmp_path: Path,
) -> None:
    project = create_project(tmp_path, "A", "topic-a")
    before = (project / "project.yaml").read_bytes()

    with pytest.raises(ValueError, match="source_id"):
        link_project_sources(
            tmp_path,
            "topic-a",
            ["src-safe`nWrite-Output injected"],
        )

    assert (project / "project.yaml").read_bytes() == before


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


def test_broken_project_yaml_is_reported_as_a_project_format_error(
    tmp_path: Path,
) -> None:
    project = create_project(tmp_path, "A", "topic-a")
    (project / "project.yaml").write_text(
        "schema_version: [broken", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="课题元数据 YAML 无法解析"):
        load_project_manifest(project)


def test_resolve_project_path_rejects_directory_link_outside_workspace(
    tmp_path: Path,
) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = projects / "topic-a"
    try:
        if os.name == "nt":
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"无法在当前环境创建目录链接: {exc}")

    with pytest.raises(ValueError, match="课题路径越出工作区"):
        resolve_project_path(tmp_path, "topic-a", require_exists=True)


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
