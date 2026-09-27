"""Row owners must tell a live worker from a dead one, even after PID reuse."""

from __future__ import annotations

import os
import subprocess
import sys

from app.services import process_identity as pi


def test_current_process_is_alive():
    assert pi.is_owner_alive(pi.current_process_owner())


def test_exited_process_is_dead():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        owner = pi.owner_of(child.pid)
        assert pi.is_owner_alive(owner)
        child_started = owner.partition(":")[2]
        assert child_started and child_started != pi.current_process_owner().partition(":")[2]
    finally:
        child.kill()
        child.wait()
    assert not pi.is_owner_alive(owner)


def test_reused_pid_is_not_the_old_owner():
    """After a container restart the new worker can get the PID of the old one."""
    assert not pi.is_owner_alive(f"{os.getpid()}:1")


def test_missing_or_garbage_owner_is_dead():
    assert not pi.is_owner_alive(None)
    assert not pi.is_owner_alive("")
    assert not pi.is_owner_alive("not-a-pid:5")
    # os.kill(0 or -1, 0) would signal a whole process group and look alive.
    assert not pi.is_owner_alive("0:")
    assert not pi.is_owner_alive("-1:")
