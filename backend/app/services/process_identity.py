"""Owner tokens for rows held by one uvicorn worker (running tasks, scheduled reboots).

A PID alone is not enough: after a restart (especially in a container) a new
worker can get the PID of the dead one, so the token also carries the process
start time from ``/proc``.
"""

from __future__ import annotations

import os


def _start_ticks(pid: int) -> str | None:
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            stat = f.read().decode(errors="replace")
    except OSError:
        return None
    # The command name may contain spaces and ')'; fields after the last ')' start at field 3 (state).
    fields = stat.rsplit(")", 1)[-1].split()
    return fields[19] if len(fields) > 19 else None


def owner_of(pid: int) -> str:
    return f"{pid}:{_start_ticks(pid) or ''}"


def current_process_owner() -> str:
    return owner_of(os.getpid())


def is_owner_alive(owner: str | None) -> bool:
    pid_text, _, ticks = (owner or "").partition(":")
    try:
        pid = int(pid_text)
    except ValueError:
        return False
    if pid <= 0:
        return False
    if ticks:
        return _start_ticks(pid) == ticks
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
