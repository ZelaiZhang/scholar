from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _assert_parent_identity(
    path: Path, expected_parent_identity: tuple[int, int] | None
) -> None:
    if expected_parent_identity is None:
        return
    metadata = path.parent.stat()
    if (metadata.st_dev, metadata.st_ino) != expected_parent_identity:
        raise OSError(f"写入目录在提交期间被替换: {path.parent}")


def atomic_write_text(
    path: Path,
    content: str,
    *,
    expected_parent_identity: tuple[int, int] | None = None,
) -> None:
    """Write UTF-8 text without exposing a partially written destination."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _assert_parent_identity(path, expected_parent_identity)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        _assert_parent_identity(path, expected_parent_identity)
        os.replace(temporary_path, path)
        _assert_parent_identity(path, expected_parent_identity)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def atomic_write_bytes(
    path: Path,
    content: bytes,
    *,
    expected_parent_identity: tuple[int, int] | None = None,
) -> None:
    """Write bytes without exposing a partially written destination."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _assert_parent_identity(path, expected_parent_identity)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        _assert_parent_identity(path, expected_parent_identity)
        os.replace(temporary_path, path)
        _assert_parent_identity(path, expected_parent_identity)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
