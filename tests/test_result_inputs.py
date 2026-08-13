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


@pytest.mark.parametrize("content", ["", " \t\n"])
def test_load_result_inputs_rejects_blank_artifact_content(
    tmp_path: Path,
    content: str,
) -> None:
    project = tmp_path / "project"
    artifacts = project / "artifacts"
    artifacts.mkdir(parents=True)
    result_path = artifacts / "aggregate-results.csv"
    result_path.write_text(content, encoding="utf-8")
    _write_manifest(
        artifacts,
        _result_entry(
            result_path.name,
            hashlib.sha256(result_path.read_bytes()).hexdigest(),
        ),
    )

    with pytest.raises(ValueError, match="blank"):
        result_inputs.load_result_inputs(project, directory_identity(project))


def test_load_result_inputs_rejects_unknown_manifest_fields(tmp_path: Path) -> None:
    project = tmp_path / "project"
    artifacts = project / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "results-manifest.yaml").write_text(
        "schema_version: 1\nresults: []\nunexpected: value\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="only schema_version and results"):
        result_inputs.load_result_inputs(project, directory_identity(project))


def test_load_result_inputs_rejects_unknown_artifact_fields(tmp_path: Path) -> None:
    project = tmp_path / "project"
    artifacts = project / "artifacts"
    artifacts.mkdir(parents=True)
    result_path = artifacts / "aggregate-results.csv"
    result_path.write_text("metric,value\naccuracy,0.8\n", encoding="utf-8")
    _write_manifest(
        artifacts,
        _result_entry(
            result_path.name,
            hashlib.sha256(result_path.read_bytes()).hexdigest(),
        )
        + "    unexpected: value\n",
    )

    with pytest.raises(ValueError, match="invalid fields"):
        result_inputs.load_result_inputs(project, directory_identity(project))


def test_load_result_inputs_rejects_duplicate_artifact_path(tmp_path: Path) -> None:
    project = tmp_path / "project"
    artifacts = project / "artifacts"
    artifacts.mkdir(parents=True)
    result_path = artifacts / "aggregate-results.csv"
    result_path.write_text("metric,value\naccuracy,0.8\n", encoding="utf-8")
    entry = _result_entry(
        result_path.name,
        hashlib.sha256(result_path.read_bytes()).hexdigest(),
    )
    _write_manifest(artifacts, entry + entry)

    with pytest.raises(ValueError, match="unsafe path"):
        result_inputs.load_result_inputs(project, directory_identity(project))


def test_load_result_inputs_rejects_unsupported_artifact_extension(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    artifacts = project / "artifacts"
    artifacts.mkdir(parents=True)
    _write_manifest(
        artifacts,
        _result_entry("aggregate-results.exe", "0" * 64),
    )

    with pytest.raises(ValueError, match="unsupported format"):
        result_inputs.load_result_inputs(project, directory_identity(project))


def test_load_result_inputs_rejects_traversal_path(tmp_path: Path) -> None:
    project = tmp_path / "project"
    artifacts = project / "artifacts"
    artifacts.mkdir(parents=True)
    _write_manifest(artifacts, _result_entry("../outside.csv", "0" * 64))

    with pytest.raises(ValueError, match="unsafe path"):
        result_inputs.load_result_inputs(project, directory_identity(project))


def test_load_result_inputs_rejects_invalid_generated_timestamp(tmp_path: Path) -> None:
    project = tmp_path / "project"
    artifacts = project / "artifacts"
    artifacts.mkdir(parents=True)
    _write_manifest(
        artifacts,
        _result_entry("aggregate-results.csv", "a" * 64).replace(
            "2026-08-13T00:00:00Z", "not-a-timestamp"
        ),
    )

    with pytest.raises(ValueError, match="invalid generated_at"):
        result_inputs.load_result_inputs(project, directory_identity(project))


def test_load_result_inputs_rejects_symlink_artifact(tmp_path: Path) -> None:
    project = tmp_path / "project"
    artifacts = project / "artifacts"
    artifacts.mkdir(parents=True)
    target = artifacts / "aggregate-results.csv"
    target.write_text("metric,value\naccuracy,0.8\n", encoding="utf-8")
    linked = artifacts / "linked-results.csv"
    try:
        linked.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    _write_manifest(
        artifacts,
        _result_entry(
            linked.name,
            hashlib.sha256(target.read_bytes()).hexdigest(),
        ),
    )

    with pytest.raises(ValueError, match="link or reparse"):
        result_inputs.load_result_inputs(project, directory_identity(project))


def test_load_result_inputs_rejects_manifest_replaced_after_stable_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    artifacts = project / "artifacts"
    artifacts.mkdir(parents=True)
    manifest_path = artifacts / "results-manifest.yaml"
    _write_manifest(artifacts, " []\n")
    original_read = result_inputs.read_stable_direct_text
    replaced = False

    def replace_manifest_after_read(path: Path, **kwargs: object) -> str:
        nonlocal replaced
        text = original_read(path, **kwargs)
        if path == manifest_path and not replaced:
            replacement = artifacts / "replacement-manifest.yaml"
            replacement.write_text(text, encoding="utf-8")
            replacement.replace(manifest_path)
            replaced = True
        return text

    monkeypatch.setattr(
        result_inputs,
        "read_stable_direct_text",
        replace_manifest_after_read,
    )

    with pytest.raises(OSError, match="manifest changed"):
        result_inputs.load_result_inputs(project, directory_identity(project))


def test_load_result_inputs_rejects_artifact_replaced_after_stable_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    artifacts = project / "artifacts"
    artifacts.mkdir(parents=True)
    result_path = artifacts / "aggregate-results.csv"
    result_path.write_text("metric,value\naccuracy,0.8\n", encoding="utf-8")
    _write_manifest(
        artifacts,
        _result_entry(
            result_path.name,
            hashlib.sha256(result_path.read_bytes()).hexdigest(),
        ),
    )
    original_read = result_inputs.read_stable_direct_text
    replaced = False

    def replace_artifact_after_read(path: Path, **kwargs: object) -> str:
        nonlocal replaced
        text = original_read(path, **kwargs)
        if path == result_path and not replaced:
            replacement = artifacts / "replacement-results.csv"
            replacement.write_text(text, encoding="utf-8")
            replacement.replace(result_path)
            replaced = True
        return text

    monkeypatch.setattr(
        result_inputs,
        "read_stable_direct_text",
        replace_artifact_after_read,
    )

    with pytest.raises(OSError, match="artifact changed"):
        result_inputs.load_result_inputs(project, directory_identity(project))
