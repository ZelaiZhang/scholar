from __future__ import annotations

import os
import stat
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


def _identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _is_link_or_reparse(metadata: os.stat_result, path: Path) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(metadata, "st_file_attributes", 0)
    return path.is_symlink() or bool(reparse_flag and attributes & reparse_flag)


def directory_identity(path: Path) -> tuple[int, int]:
    """Capture the identity of one real directory without following a link."""
    metadata = path.lstat()
    if _is_link_or_reparse(metadata, path):
        raise ValueError(f"directory cannot be a link or reparse point: {path}")
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"expected a real directory: {path}")
    return _identity(metadata)


def assert_directory_identity(
    path: Path,
    expected: tuple[int, int],
    *,
    context: str,
) -> None:
    """Fail closed when a directory path no longer names the captured object."""
    try:
        current = directory_identity(path)
    except OSError as exc:
        raise OSError(f"{context} directory is unavailable: {path}") from exc
    if current != expected:
        raise OSError(f"{context} directory was replaced or changed: {path}")


def direct_file_identity(
    path: Path,
    *,
    expected_parent: Path | None = None,
    expected_parent_identity: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """Capture one direct regular file identity while its parent stays stable."""
    parent = (expected_parent or path.parent).resolve()
    if path.parent.resolve() != parent:
        raise ValueError(f"file escapes its expected parent: {path}")
    parent_before = parent.stat()
    if (
        expected_parent_identity is not None
        and _identity(parent_before) != expected_parent_identity
    ):
        raise OSError(f"file parent was replaced before identity capture: {parent}")
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise FileNotFoundError(path) from exc
    if _is_link_or_reparse(metadata, path):
        raise ValueError(f"file cannot be a link or reparse point: {path}")
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"expected a regular file: {path}")
    parent_after = parent.stat()
    if _identity(parent_after) != _identity(parent_before):
        raise OSError(f"file parent changed during identity capture: {parent}")
    return _identity(metadata)


def read_stable_direct_text(
    path: Path,
    *,
    expected_parent: Path | None = None,
    expected_parent_identity: tuple[int, int] | None = None,
    max_bytes: int | None = None,
) -> str:
    """Read one direct UTF-8 file while rejecting links and identity changes."""
    parent = (expected_parent or path.parent).resolve()
    if path.parent.resolve() != parent:
        raise ValueError(f"读取文件越出预期父目录: {path}")
    parent_before = parent.stat()
    if (
        expected_parent_identity is not None
        and _identity(parent_before) != expected_parent_identity
    ):
        raise OSError(f"读取目录在打开文件前被替换: {parent}")
    try:
        before = path.lstat()
    except OSError as exc:
        raise FileNotFoundError(path) from exc
    if _is_link_or_reparse(before, path):
        raise ValueError(f"读取文件不能是符号链接或目录联接: {path}")
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"读取目标必须是普通文件: {path}")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if _identity(opened) != _identity(before):
            raise OSError(f"读取文件在打开期间被替换: {path}")
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if max_bytes is not None and size > max_bytes:
                raise ValueError(f"读取文件超过 {max_bytes} 字节限制: {path}")
            chunks.append(chunk)
    finally:
        os.close(descriptor)

    after = path.lstat()
    parent_after = parent.stat()
    if _is_link_or_reparse(after, path) or _identity(after) != _identity(before):
        raise OSError(f"读取文件在读取期间被替换: {path}")
    if _identity(parent_after) != _identity(parent_before):
        raise OSError(f"读取目录在读取期间被替换: {parent}")
    try:
        return b"".join(chunks).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnicodeError(f"读取文件不是有效 UTF-8: {path}") from exc


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


def atomic_create_text(
    path: Path,
    content: str,
    *,
    expected_parent_identity: tuple[int, int] | None = None,
) -> None:
    """Atomically create UTF-8 text and fail if the destination already exists."""
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
        # A hard-link creates the destination atomically but never replaces it.
        os.link(temporary_path, path)
        _assert_parent_identity(path, expected_parent_identity)
    except FileExistsError as exc:
        raise FileExistsError(
            f"destination appeared during provider work; refusing to overwrite: {path}"
        ) from exc
    finally:
        temporary_path.unlink(missing_ok=True)
