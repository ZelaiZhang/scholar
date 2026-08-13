import hashlib
import importlib.util
from pathlib import Path

import pytest

import research_os.result_inputs as result_inputs
from research_os.io import direct_file_identity, directory_identity


def test_result_inputs_module_is_available() -> None:
    assert importlib.util.find_spec("research_os.result_inputs") is not None


def _write_manifest(artifacts: Path, results: str) -> None:
    (artifacts / "results-manifest.yaml").write_text(
        "schema_version: 1\nresults:\n" + results,
        encoding="utf-8",
    )


def _result_entry(name: str, digest: str) -> str:
    return (
        f"  - path: {name}\n"
        f"    sha256: {digest}\n"
        "    source_repository: public-experiment-repository\n"
        "    generated_at: '2026-08-13T00:00:00Z'\n"
    )


def test_load_result_inputs_returns_validated_provenance_snapshot(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    artifacts = project / "artifacts"
    artifacts.mkdir(parents=True)
    content = "metric,value\naccuracy,0.8\n"
    result_path = artifacts / "aggregate-results.csv"
    result_path.write_text(content, encoding="utf-8")
    digest = hashlib.sha256(result_path.read_bytes()).hexdigest()
    _write_manifest(artifacts, _result_entry(result_path.name, digest))

    snapshot = result_inputs.load_result_inputs(
        project, directory_identity(project)
    )

    assert isinstance(snapshot, result_inputs.ResultInputSnapshot)
    assert len(snapshot.artifacts) == 1
    artifact = snapshot.artifacts[0]
    assert artifact.name == "aggregate-results.csv"
    assert artifact.path == artifacts / "aggregate-results.csv"
    assert artifact.sha256 == digest
    assert artifact.source_repository == "public-experiment-repository"
    assert artifact.generated_at == "2026-08-13T00:00:00Z"
    assert artifact.identity == direct_file_identity(
        artifact.path, expected_parent=artifacts
    )
    assert snapshot.token != "missing"
    assert snapshot.directory_identity == directory_identity(artifacts)
    assert snapshot.manifest_identity is not None


def test_missing_result_manifest_returns_exact_empty_snapshot(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "artifacts").mkdir(parents=True)

    snapshot = result_inputs.load_result_inputs(
        project, directory_identity(project)
    )

    assert snapshot.artifacts == ()
    assert snapshot.token == "missing"
    assert snapshot.directory_identity is not None
    assert snapshot.manifest_identity is None


def test_empty_result_manifest_is_valid_but_not_missing(tmp_path: Path) -> None:
    project = tmp_path / "project"
    artifacts = project / "artifacts"
    artifacts.mkdir(parents=True)
    _write_manifest(artifacts, " []\n")

    snapshot = result_inputs.load_result_inputs(
        project, directory_identity(project)
    )

    assert snapshot.artifacts == ()
    assert snapshot.token != "missing"
    assert snapshot.manifest_identity is not None


def test_load_result_inputs_rejects_blank_artifact_name(tmp_path: Path) -> None:
    project = tmp_path / "project"
    artifacts = project / "artifacts"
    artifacts.mkdir(parents=True)
    content = "metric,value\naccuracy,0.8\n"
    _write_manifest(
        artifacts,
        _result_entry(" ", hashlib.sha256(content.encode("utf-8")).hexdigest()),
    )

    with pytest.raises(ValueError, match="unsafe path"):
        result_inputs.load_result_inputs(
            project, directory_identity(project)
        )


def test_load_result_inputs_rejects_artifact_changed_after_snapshot(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    artifacts = project / "artifacts"
    artifacts.mkdir(parents=True)
    content = "metric,value\naccuracy,0.8\n"
    result_path = artifacts / "aggregate-results.csv"
    result_path.write_text(content, encoding="utf-8")
    _write_manifest(
        artifacts,
        _result_entry(
            result_path.name,
            hashlib.sha256(result_path.read_bytes()).hexdigest(),
        ),
    )
    expected_project_identity = directory_identity(project)
    first = result_inputs.load_result_inputs(project, expected_project_identity)
    assert first.token != "missing"
    result_path.write_text("metric,value\naccuracy,0.9\n", encoding="utf-8")

    with pytest.raises(ValueError, match="hash mismatch"):
        result_inputs.load_result_inputs(project, expected_project_identity)
