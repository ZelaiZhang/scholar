"""Validated external result artifacts for Research OS projects."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from research_os.io import (
    assert_directory_identity,
    direct_file_identity,
    directory_identity,
    read_stable_direct_text,
)


_RESULT_EXTENSIONS = {".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml"}
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ResultArtifact:
    name: str
    path: Path
    sha256: str
    source_repository: str
    generated_at: str
    identity: tuple[int, int]


@dataclass(frozen=True)
class ResultInputSnapshot:
    artifacts: tuple[ResultArtifact, ...]
    token: str
    directory_identity: tuple[int, int] | None
    manifest_identity: tuple[int, int] | None


def load_result_inputs(
    project_path: Path,
    expected_project_identity: tuple[int, int],
) -> ResultInputSnapshot:
    """Load result artifacts only when their manifest and contents are stable."""
    artifacts_directory = project_path / "artifacts"
    if not artifacts_directory.is_dir():
        return ResultInputSnapshot((), "missing", None, None)
    assert_directory_identity(
        project_path,
        expected_project_identity,
        context="project",
    )
    artifacts_identity = directory_identity(artifacts_directory)
    manifest_path = artifacts_directory / "results-manifest.yaml"
    if not manifest_path.exists():
        return ResultInputSnapshot((), "missing", artifacts_identity, None)
    manifest_identity_before = direct_file_identity(
        manifest_path,
        expected_parent=artifacts_directory,
        expected_parent_identity=artifacts_identity,
    )
    raw_text = read_stable_direct_text(
        manifest_path,
        expected_parent=artifacts_directory,
        expected_parent_identity=artifacts_identity,
        max_bytes=1024 * 1024,
    )
    manifest_identity = direct_file_identity(
        manifest_path,
        expected_parent=artifacts_directory,
        expected_parent_identity=artifacts_identity,
    )
    if manifest_identity != manifest_identity_before:
        raise OSError("results manifest changed during validation")
    try:
        raw = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ValueError("results manifest is not valid YAML") from exc
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "results"}:
        raise ValueError("results manifest must contain only schema_version and results")
    if raw["schema_version"] != 1 or not isinstance(raw["results"], list):
        raise ValueError("results manifest schema_version must be 1 and results a list")

    artifacts: list[ResultArtifact] = []
    seen: set[str] = set()
    required = {"path", "sha256", "source_repository", "generated_at"}
    for index, item in enumerate(raw["results"], 1):
        if not isinstance(item, dict) or set(item) != required:
            raise ValueError(f"results manifest entry {index} has invalid fields")
        relative = item["path"]
        digest = item["sha256"]
        repository = item["source_repository"]
        generated_at = item["generated_at"]
        if (
            not isinstance(relative, str)
            or not relative.strip()
            or Path(relative).name != relative
            or relative in seen
        ):
            raise ValueError(f"results manifest entry {index} has an unsafe path")
        if Path(relative).suffix.lower() not in _RESULT_EXTENSIONS:
            raise ValueError(f"results manifest entry {index} has an unsupported format")
        if not isinstance(digest, str) or not _SHA256_PATTERN.fullmatch(digest):
            raise ValueError(f"results manifest entry {index} has an invalid sha256")
        if not isinstance(repository, str) or not repository.strip():
            raise ValueError(
                f"results manifest entry {index} needs source_repository provenance"
            )
        if not isinstance(generated_at, str) or not generated_at.strip():
            raise ValueError(f"results manifest entry {index} needs generated_at")
        try:
            datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(
                f"results manifest entry {index} has invalid generated_at"
            ) from exc
        path = artifacts_directory / relative
        identity_before = direct_file_identity(
            path,
            expected_parent=artifacts_directory,
            expected_parent_identity=artifacts_identity,
        )
        actual_text = read_stable_direct_text(
            path,
            expected_parent=artifacts_directory,
            expected_parent_identity=artifacts_identity,
        )
        identity_after = direct_file_identity(
            path,
            expected_parent=artifacts_directory,
            expected_parent_identity=artifacts_identity,
        )
        if identity_after != identity_before:
            raise OSError(f"result artifact changed during validation: {relative}")
        actual_digest = hashlib.sha256(actual_text.encode("utf-8")).hexdigest()
        if actual_digest != digest:
            raise ValueError(f"result artifact hash mismatch: {relative}")
        seen.add(relative)
        artifacts.append(
            ResultArtifact(
                relative,
                path,
                digest,
                repository,
                generated_at,
                identity_after,
            )
        )

    assert_directory_identity(
        artifacts_directory,
        artifacts_identity,
        context="artifacts",
    )
    assert_directory_identity(
        project_path,
        expected_project_identity,
        context="project",
    )
    identity_parts = [str(artifacts_identity), str(manifest_identity)]
    for artifact in artifacts:
        current_identity = direct_file_identity(
            artifact.path,
            expected_parent=artifacts_directory,
            expected_parent_identity=artifacts_identity,
        )
        if current_identity != artifact.identity:
            raise OSError(f"result artifact changed during validation: {artifact.name}")
        identity_parts.append(str(current_identity))
    if (
        direct_file_identity(
            manifest_path,
            expected_parent=artifacts_directory,
            expected_parent_identity=artifacts_identity,
        )
        != manifest_identity
    ):
        raise OSError("results manifest changed during validation")
    dependency_token = "\n".join(
        (raw_text, *(artifact.name for artifact in artifacts), *identity_parts)
    )
    return ResultInputSnapshot(
        tuple(artifacts),
        hashlib.sha256(dependency_token.encode("utf-8")).hexdigest(),
        artifacts_identity,
        manifest_identity,
    )
