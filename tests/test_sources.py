import json
from pathlib import Path

import pytest

from research_os.sources import (
    InvalidSourceError,
    SourceRegistry,
    normalize_source,
)


def test_normalize_doi_url_and_arxiv() -> None:
    assert normalize_source("https://doi.org/10.1000/XYZ") == (
        "doi",
        "10.1000/xyz",
    )
    assert normalize_source("arXiv:2401.01234v2") == (
        "arxiv",
        "2401.01234v2",
    )
    assert normalize_source("https://example.org/paper?a=1") == (
        "url",
        "https://example.org/paper?a=1",
    )


def test_normalize_local_file_uses_resolved_path(tmp_path: Path) -> None:
    note = tmp_path / "note.md"
    note.write_text("公开资料笔记", encoding="utf-8")

    kind, canonical = normalize_source(str(note))

    assert kind == "file"
    assert canonical == note.resolve().as_posix()


def test_normalize_rejects_unknown_free_text() -> None:
    with pytest.raises(InvalidSourceError):
        normalize_source("this is not a source")


def test_registry_deduplicates_without_overwriting_notes(tmp_path: Path) -> None:
    registry = SourceRegistry(tmp_path / "sources.jsonl")
    first = registry.add("doi:10.1000/test", notes="人工笔记")
    second = registry.add("https://doi.org/10.1000/TEST")

    assert first.source_id == second.source_id
    rows = [
        json.loads(line)
        for line in (tmp_path / "sources.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["notes"] == "人工笔记"


def test_registry_hashes_local_file_and_defaults_to_no_external_api(
    tmp_path: Path,
) -> None:
    note = tmp_path / "note.md"
    note.write_text("公开资料笔记", encoding="utf-8")
    registry = SourceRegistry(tmp_path / "registry" / "sources.jsonl")

    record = registry.add(str(note))

    assert record.content_hash is not None
    assert len(record.content_hash) == 64
    assert record.external_api_allowed is False
