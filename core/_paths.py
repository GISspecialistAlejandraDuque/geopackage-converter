"""
Cross-platform path helpers.

The Windows MAX_PATH limit (260 chars) breaks pretty much every stdlib
filesystem call on long paths unless they're prefixed with ``\\\\?\\``
(or ``\\\\?\\UNC\\`` for UNC paths). The helpers here apply that prefix
when needed so callers don't have to pepper the codebase with platform
checks.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Union

# Threshold below which we don't bother with the prefix. Some Windows
# subsystems (notably SQLite via OGR) start to misbehave well before
# the official 260 cap, so we trigger conservatively at 240.
_LONG_PATH_THRESHOLD = 240


def long_path(path: Union[str, Path]) -> str:
    """
    Return ``path`` as a string suitable for filesystem APIs.

    On Windows, paths longer than ~240 chars are rewritten with the
    ``\\\\?\\`` long-path prefix (or ``\\\\?\\UNC\\`` for UNC shares).
    Short paths and non-Windows platforms are returned verbatim.
    """
    s = str(path)
    if os.name != "nt":
        return s
    if s.startswith("\\\\?\\"):
        return s
    if len(s) < _LONG_PATH_THRESHOLD:
        return s
    abs_s = os.path.abspath(s)
    if abs_s.startswith("\\\\"):
        # \\server\share\... -> \\?\UNC\server\share\...
        return "\\\\?\\UNC\\" + abs_s.lstrip("\\")
    return "\\\\?\\" + abs_s


__all__ = ["long_path"]
