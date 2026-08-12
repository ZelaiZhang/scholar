import json
from pathlib import Path

import pytest

from research_os.sources import (
    InvalidSourceError,
    SourceAuthorizationError,
    SourceRegistry,
    authorize_external_files,
    authorize_external_sources,
    load_authorized_external_texts,
    load_source_manifest,
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


def test_duplicate_source_can_be_explicitly_authorized_without_losing_notes(
    tmp_path: Path,
) -> None:
    registry = SourceRegistry(tmp_path / "sources.jsonl")
    first = registry.add("doi:10.1000/permission", notes="人工笔记")

    updated = registry.add(
        "https://doi.org/10.1000/PERMISSION", external_api_allowed=True
    )

    assert updated.source_id == first.source_id
    assert updated.external_api_allowed is True
    assert updated.notes == "人工笔记"
    assert len(registry.records()) == 1


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


def test_external_authorization_requires_every_registered_source_to_opt_in(
    tmp_path: Path,
) -> None:
    allowed = tmp_path / "allowed.md"
    blocked = tmp_path / "blocked.md"
    allowed.write_text("public A", encoding="utf-8")
    blocked.write_text("public B", encoding="utf-8")
    registry = SourceRegistry(tmp_path / "sources.jsonl")
    allowed_record = registry.add(str(allowed), external_api_allowed=True)
    blocked_record = registry.add(str(blocked), external_api_allowed=False)

    assert authorize_external_sources(
        registry.path, [allowed_record.source_id]
    ) == (allowed_record,)
    with pytest.raises(SourceAuthorizationError, match=blocked_record.source_id):
        authorize_external_sources(registry.path, [blocked_record.source_id])
    with pytest.raises(SourceAuthorizationError, match="src-unknown"):
        authorize_external_sources(registry.path, ["src-unknown"])


def test_local_sources_deduplicate_by_content_across_file_names(tmp_path: Path) -> None:
    first_path = tmp_path / "first.pdf"
    second_path = tmp_path / "renamed.pdf"
    first_path.write_bytes(b"same public paper")
    second_path.write_bytes(b"same public paper")
    registry = SourceRegistry(tmp_path / "sources.jsonl")

    first = registry.add(str(first_path))
    second = registry.add(str(second_path))

    assert first.source_id == second.source_id
    assert len(registry._read()) == 1


def test_changed_file_at_same_path_creates_new_source_version(tmp_path: Path) -> None:
    paper = tmp_path / "paper.pdf"
    paper.write_bytes(b"version one")
    registry = SourceRegistry(tmp_path / "sources.jsonl")
    first = registry.add(str(paper))

    paper.write_bytes(b"version two")
    second = registry.add(str(paper))

    assert first.source_id != second.source_id
    assert first.content_hash != second.content_hash
    assert len(registry._read()) == 2


def test_external_payload_files_must_match_the_authorized_source_ids(
    tmp_path: Path,
) -> None:
    system = tmp_path / "system.md"
    user = tmp_path / "user.md"
    unrelated = tmp_path / "unrelated.md"
    system.write_text("public system", encoding="utf-8")
    user.write_text("public user", encoding="utf-8")
    unrelated.write_text("other allowed material", encoding="utf-8")
    registry = SourceRegistry(tmp_path / "sources.jsonl")
    system_record = registry.add(str(system), external_api_allowed=True)
    user_record = registry.add(str(user), external_api_allowed=True)
    unrelated_record = registry.add(str(unrelated), external_api_allowed=True)

    authorize_external_files(
        registry.path,
        [system, user],
        [system_record.source_id, user_record.source_id],
    )
    with pytest.raises(SourceAuthorizationError, match="请求文件未被 source_id 授权"):
        authorize_external_files(
            registry.path,
            [system, user],
            [system_record.source_id, unrelated_record.source_id],
        )


def test_authorized_external_text_is_a_verified_immutable_snapshot(
    tmp_path: Path,
) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("authorized public prompt", encoding="utf-8")
    registry = SourceRegistry(tmp_path / "sources.jsonl")
    record = registry.add(str(prompt), external_api_allowed=True)

    (snapshot,) = load_authorized_external_texts(
        registry.path, [prompt], [record.source_id]
    )
    prompt.write_text("replacement after authorization", encoding="utf-8")

    assert snapshot == "authorized public prompt"


def test_verified_source_ids_exclude_changed_or_missing_local_files(
    tmp_path: Path,
) -> None:
    paper = tmp_path / "paper.pdf"
    paper.write_bytes(b"version one")
    registry = SourceRegistry(tmp_path / "sources.jsonl")
    record = registry.add(str(paper))
    assert record.source_id in registry.verified_source_ids()

    paper.write_bytes(b"version two")
    assert record.source_id not in registry.verified_source_ids()

    paper.unlink()
    assert record.source_id not in registry.verified_source_ids()


def test_source_manifest_supports_comments_and_relative_files(
    tmp_path: Path,
) -> None:
    paper = tmp_path / "paper.pdf"
    paper.write_bytes(b"public paper")
    manifest = tmp_path / "sources.txt"
    manifest.write_text(
        "# seed\n\n./paper.pdf\ndoi:10.1000/ABC\n", encoding="utf-8"
    )

    values = load_source_manifest(manifest)

    assert values == [paper.resolve().as_posix(), "doi:10.1000/ABC"]


def test_add_many_is_atomic_when_one_source_is_invalid(tmp_path: Path) -> None:
    registry_path = tmp_path / "library" / "sources.jsonl"
    registry = SourceRegistry(registry_path)
    registry.add("doi:10.1000/existing")
    before = registry_path.read_bytes()

    with pytest.raises(InvalidSourceError):
        registry.add_many(["doi:10.1000/good", "missing.pdf"])

    assert registry_path.read_bytes() == before


def test_add_many_reports_added_duplicate_and_authorization_upgrade(
    tmp_path: Path,
) -> None:
    registry = SourceRegistry(tmp_path / "library" / "sources.jsonl")
    registry.add("doi:10.1000/existing")

    result = registry.add_many(
        ["doi:10.1000/existing", "doi:10.1000/new", "doi:10.1000/new"],
        external_api_allowed=True,
    )

    assert (
        result.added,
        result.duplicates,
        result.authorizations_upgraded,
    ) == (1, 2, 1)
    assert len(registry.records()) == 2
