"""Cheap nonempty-line counters for CIDR list / route files.

Overview polls used to `read_text` every provider and include file on each request.
Cache by (mtime_ns, size) and stream lines so unchanged files skip I/O.
"""

from __future__ import annotations

from pathlib import Path

# path_str -> (mtime_ns, size, count)
_CACHE: dict[str, tuple[int, int, int]] = {}


def count_nonempty_lines_in_text(content: str) -> int:
    count = 0
    for line in content.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            count += 1
    return count


def count_nonempty_lines(path: Path) -> int:
    try:
        st = path.stat()
    except OSError:
        return 0
    key = str(path)
    cached = _CACHE.get(key)
    if cached is not None and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
        return cached[2]
    count = 0
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            s = line.strip()
            if s and not s.startswith("#"):
                count += 1
    _CACHE[key] = (st.st_mtime_ns, st.st_size, count)
    return count


def remember_line_count(path: Path, count: int) -> None:
    """Seed cache after a write when the count is already known from content."""
    try:
        st = path.stat()
    except OSError:
        return
    _CACHE[str(path)] = (st.st_mtime_ns, st.st_size, count)


def clear_line_count_cache() -> None:
    _CACHE.clear()
