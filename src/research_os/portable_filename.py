"""Cross-platform direct-child filename validation."""

from __future__ import annotations

import re


_PORTABLE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_WINDOWS_RESERVED_BASENAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)


def is_portable_direct_filename(value: object) -> bool:
    """Return whether ``value`` is one portable ASCII direct-child filename."""
    if not isinstance(value, str) or _PORTABLE_FILENAME.fullmatch(value) is None:
        return False
    if value.endswith((".", " ")):
        return False
    basename = value.split(".", 1)[0].upper()
    return basename not in _WINDOWS_RESERVED_BASENAMES


def validate_portable_direct_filename(value: object) -> str:
    """Return a valid filename or raise without echoing the supplied value."""
    if not is_portable_direct_filename(value):
        raise ValueError("value must be a portable direct filename")
    return value
