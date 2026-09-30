from pathlib import Path
from types import SimpleNamespace

import pytest

import research_os.io as io_module
from research_os.io import read_stable_direct_text


@pytest.mark.parametrize("operation", ["rewrite", "truncate", "replace"])
def test_stable_reader_rejects_changes_during_read(tmp_path, monkeypatch, operation):
    path = tmp_path / "evidence.md"
    path.write_text("original evidence", encoding="utf-8")
    original_read = io_module.os.read
    changed = False

    def concurrent_read(descriptor, size):
        nonlocal changed
        chunk = original_read(descriptor, size)
        if chunk and not changed:
            changed = True
            if operation == "replace":
                replacement = tmp_path / "replacement.md"
                replacement.write_text("modified evidence", encoding="utf-8")
                try:
                    replacement.replace(path)
                except PermissionError as exc:
                    pytest.skip(f"platform prevents replacing an open file: {exc}")
            else:
                path.write_text(
                    "modified evidence" if operation == "rewrite" else "",
                    encoding="utf-8",
                )
        return chunk

    monkeypatch.setattr(io_module.os, "read", concurrent_read)
    with pytest.raises(OSError, match="读取.*(修改|替换)"):
        read_stable_direct_text(path)


def test_stable_reader_rejects_oversized_file_before_opening(tmp_path, monkeypatch):
    path = tmp_path / "large.md"
    path.write_text("中文证据", encoding="utf-8")

    def unexpected_open(*args, **kwargs):
        pytest.fail("oversized inputs must be rejected before reading")

    monkeypatch.setattr(io_module.os, "open", unexpected_open)
    with pytest.raises(ValueError, match="字节限制"):
        read_stable_direct_text(path, max_bytes=3)


def test_stable_reader_preserves_exact_utf8_and_crlf_bytes(tmp_path):
    path = tmp_path / "text.md"
    expected = "中文证据\r\n原文定位\n"
    path.write_bytes(expected.encode("utf-8"))
    assert read_stable_direct_text(path, max_bytes=len(path.read_bytes())) == expected


def test_stable_reader_accepts_different_path_and_descriptor_time_precision(
    tmp_path, monkeypatch
):
    path = tmp_path / "evidence.md"
    path.write_text("public evidence", encoding="utf-8")
    original_fstat = io_module.os.fstat

    def coarse_fstat(descriptor):
        metadata = original_fstat(descriptor)
        return SimpleNamespace(
            st_dev=metadata.st_dev, st_ino=metadata.st_ino,
            st_size=metadata.st_size,
            st_mtime_ns=(metadata.st_mtime_ns // 1_000_000_000) * 1_000_000_000,
            st_ctime_ns=(metadata.st_ctime_ns // 1_000_000_000) * 1_000_000_000,
        )

    monkeypatch.setattr(io_module.os, "fstat", coarse_fstat)
    assert read_stable_direct_text(path) == "public evidence"


def test_stable_reader_rejects_in_place_edit_between_stat_and_open(
    tmp_path, monkeypatch
):
    path = tmp_path / "evidence.md"
    path.write_text("old text", encoding="utf-8")
    original_open = io_module.os.open

    def concurrent_open(*args, **kwargs):
        path.write_text("new text", encoding="utf-8")
        return original_open(*args, **kwargs)

    monkeypatch.setattr(io_module.os, "open", concurrent_open)
    with pytest.raises(OSError, match="读取.*(修改|替换)"):
        read_stable_direct_text(path)


def test_grouped_create_preserves_human_edit_during_rollback(tmp_path, monkeypatch):
    first = tmp_path / "output.md"
    second = tmp_path / "provenance.json"
    original_link = io_module.os.link

    def concurrent_link(source, target):
        if target == second:
            first.write_text("human revision", encoding="utf-8")
            raise OSError("second publication failed")
        return original_link(source, target)

    monkeypatch.setattr(io_module.os, "link", concurrent_link)
    with pytest.raises(OSError, match="second publication"):
        io_module.atomic_create_texts(
            {first: "generated", second: "metadata"},
            expected_parent_identity=io_module.directory_identity(tmp_path),
        )
    assert first.read_text(encoding="utf-8") == "human revision"
    assert not second.exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_grouped_create_does_not_clean_replacement_directory(tmp_path, monkeypatch):
    parent = tmp_path / "outputs"
    parent.mkdir()
    moved = tmp_path / "moved"
    first = parent / "output.md"
    second = parent / "provenance.json"
    original_link = io_module.os.link
    preserved = {}

    def concurrent_link(source, target):
        if target == second:
            parent.rename(moved)
            parent.mkdir()
            # Reuse every staged filename in a new, human-owned directory.
            for previous in moved.iterdir():
                replacement = parent / previous.name
                replacement.write_text("human file", encoding="utf-8")
                preserved[replacement] = replacement.read_bytes()
            raise OSError("directory swapped")
        return original_link(source, target)

    monkeypatch.setattr(io_module.os, "link", concurrent_link)
    with pytest.raises(OSError, match="directory swapped"):
        io_module.atomic_create_texts(
            {first: "generated", second: "metadata"},
            expected_parent_identity=io_module.directory_identity(parent),
        )
    assert preserved
    assert {p: p.read_bytes() for p in parent.iterdir()} == preserved
