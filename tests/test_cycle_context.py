import hashlib
from pathlib import Path

import pytest

from research_os.cycle_context import build_external_context
from research_os.project import create_project, link_project_sources
from research_os.sources import SourceRegistry


def _workspace(
    tmp_path: Path, *, external_allowed: bool
) -> tuple[Path, Path, str]:
    project = create_project(tmp_path, "Topic A", "topic-a")
    library = tmp_path / "library"
    library.mkdir()
    (library / "papers").mkdir()
    source = tmp_path / "public-paper.txt"
    source.write_text("A public evidence summary.", encoding="utf-8")
    record = SourceRegistry(library / "sources.jsonl").add(
        str(source), external_api_allowed=external_allowed
    )
    link_project_sources(tmp_path, "topic-a", [record.source_id])
    run_dir = project / "cycles" / "run-test"
    run_dir.mkdir(parents=True)
    return project, run_dir, record.source_id


def test_external_context_requires_call_and_source_level_permission(
    tmp_path: Path,
) -> None:
    _project, run_dir, _source_id = _workspace(
        tmp_path, external_allowed=False
    )

    with pytest.raises(PermissionError, match="call-level|allow-external-api"):
        build_external_context(
            tmp_path,
            "topic-a",
            run_dir=run_dir,
            allow_external_api=False,
        )
    assert not (run_dir / "context.md").exists()

    with pytest.raises(PermissionError, match="source|外发|authorized"):
        build_external_context(
            tmp_path,
            "topic-a",
            run_dir=run_dir,
            allow_external_api=True,
        )


def test_external_context_requires_current_verified_project_sources(
    tmp_path: Path,
) -> None:
    _project, run_dir, _source_id = _workspace(tmp_path, external_allowed=True)
    source = tmp_path / "public-paper.txt"
    source.write_text("Changed after registration.", encoding="utf-8")

    with pytest.raises(PermissionError, match="verified|changed"):
        build_external_context(
            tmp_path,
            "topic-a",
            run_dir=run_dir,
            allow_external_api=True,
        )


def test_external_context_is_exactly_hashed_and_registered(
    tmp_path: Path,
) -> None:
    project, run_dir, source_id = _workspace(tmp_path, external_allowed=True)
    (tmp_path / "library" / "papers" / f"{source_id}.md").write_text(
        "# Paper card\n\nVerified claim with locator: p. 2.\n",
        encoding="utf-8",
    )

    snapshot = build_external_context(
        tmp_path,
        "topic-a",
        run_dir=run_dir,
        allow_external_api=True,
    )

    raw = snapshot.path.read_bytes()
    assert raw == snapshot.content.encode("utf-8")
    assert hashlib.sha256(raw).hexdigest() == snapshot.sha256
    assert snapshot.input_source_ids == (source_id,)
    records = SourceRegistry(tmp_path / "library" / "sources.jsonl").records()
    context_record = next(
        record for record in records if record.source_id == snapshot.context_source_id
    )
    assert context_record.external_api_allowed is True
    assert context_record.content_hash == snapshot.sha256
    assert "Paper card" in snapshot.content
    assert str(project.resolve()) not in snapshot.content


@pytest.mark.parametrize(
    "marker",
    ["姓名", "住院号", "身份证", "联系电话", "patient_id", "medical_record_number"],
)
def test_external_context_blocks_identifiable_medical_markers(
    tmp_path: Path, marker: str
) -> None:
    project, run_dir, _source_id = _workspace(tmp_path, external_allowed=True)
    (project / "00-research-brief.md").write_text(
        f"# Unsafe notes\n\n{marker}: example\n", encoding="utf-8"
    )

    with pytest.raises(PermissionError, match="identifiable|medical|隐私"):
        build_external_context(
            tmp_path,
            "topic-a",
            run_dir=run_dir,
            allow_external_api=True,
        )
    assert not (run_dir / "context.md").exists()


def test_context_cannot_use_a_run_directory_from_another_project(
    tmp_path: Path,
) -> None:
    _project, _run_dir, _source_id = _workspace(tmp_path, external_allowed=True)
    other = create_project(tmp_path, "Topic B", "topic-b")
    foreign_run = other / "cycles" / "run-test"
    foreign_run.mkdir(parents=True)

    with pytest.raises(ValueError, match="run directory"):
        build_external_context(
            tmp_path,
            "topic-a",
            run_dir=foreign_run,
            allow_external_api=True,
        )
