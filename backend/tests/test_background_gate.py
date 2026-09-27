"""Scheduled background work pauses while a backup restore replaces the database files."""

from __future__ import annotations

import asyncio
import inspect
import subprocess
import sys
import textwrap
import threading
import time

import pytest

from app.services import background_gate, lifespan_workers
from app.services.background_gate import (
    pause_background_work,
    resume_background_work,
    run_background_step,
    run_long_background_step,
)


@pytest.fixture
def gate(tmp_path):
    db_path = tmp_path / "adminpanel.db"
    background_gate.configure_background_gate(db_path)
    yield db_path
    resume_background_work()
    background_gate.configure_background_gate(None)


def _step(fn, *args, long=False):
    runner = run_long_background_step if long else run_background_step
    return asyncio.run(runner(fn, *args))


def test_step_runs_without_configured_gate():
    background_gate.configure_background_gate(None)
    assert _step(lambda x: x + 1, 1) == 2


@pytest.mark.parametrize("long", [False, True])
def test_step_runs_and_returns_result(gate, long):
    assert _step(lambda x: x * 2, 21, long=long) == 42


@pytest.mark.parametrize("long", [False, True])
def test_steps_are_skipped_while_paused_and_resume_afterwards(gate, long):
    calls: list[int] = []
    pause_background_work(gate, timeout=1)
    assert _step(calls.append, 1, long=long) is None
    assert calls == []
    resume_background_work()
    _step(calls.append, 2, long=long)
    assert calls == [2]


def test_steps_do_not_wait_for_each_other(gate):
    started = threading.Event()
    release = threading.Event()

    def slow():
        started.set()
        release.wait(5)

    runner = threading.Thread(target=_step, args=(slow,))
    runner.start()
    try:
        assert started.wait(5)
        done: list[str] = []
        other = threading.Thread(target=_step, args=(done.append, "fast"))
        other.start()
        other.join(2)
        assert done == ["fast"]
    finally:
        release.set()
        runner.join(5)


def test_pause_waits_for_running_step_and_blocks_new_ones(gate):
    started = threading.Event()
    release = threading.Event()
    finished: list[str] = []

    def slow():
        started.set()
        release.wait(5)
        finished.append("slow")

    runner = threading.Thread(target=_step, args=(slow,))
    runner.start()
    assert started.wait(5)

    paused = threading.Event()

    def do_pause():
        pause_background_work(gate, timeout=5)
        paused.set()

    pauser = threading.Thread(target=do_pause)
    pauser.start()
    time.sleep(0.3)
    assert not paused.is_set(), "restore must wait for the running step"

    newcomer: list[str] = []
    assert _step(newcomer.append, "new") is None
    assert newcomer == [], "no new step may start once a restore is waiting"

    release.set()
    runner.join(5)
    pauser.join(5)
    assert paused.is_set()
    assert finished == ["slow"]


def test_pause_times_out_and_lets_steps_run_again(gate):
    started = threading.Event()
    release = threading.Event()

    def slow():
        started.set()
        release.wait(5)

    runner = threading.Thread(target=_step, args=(slow,))
    runner.start()
    assert started.wait(5)
    try:
        with pytest.raises(TimeoutError):
            pause_background_work(gate, timeout=0.3)
    finally:
        release.set()
        runner.join(5)

    calls: list[int] = []
    _step(calls.append, 1)
    assert calls == [1]


def test_resume_without_pause_is_noop(gate):
    resume_background_work()
    assert _step(lambda: "ok") == "ok"


def test_pause_in_another_process_skips_steps_here(gate):
    ready_marker = gate.with_name("child-ready")
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            textwrap.dedent(
                f"""
                import sys, time
                from pathlib import Path
                from app.services.background_gate import pause_background_work
                pause_background_work(Path({str(gate)!r}), timeout=5)
                Path({str(ready_marker)!r}).touch()
                sys.stdin.read()
                """
            ),
        ],
        stdin=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 20
        while not ready_marker.exists():
            assert child.poll() is None, "child failed to pause"
            assert time.monotonic() < deadline
            time.sleep(0.05)
        calls: list[int] = []
        assert _step(calls.append, 1) is None
        assert calls == []
    finally:
        child.communicate(b"", timeout=10)

    calls = []
    _step(calls.append, 2)
    assert calls == [2], "the kernel drops the pause when the restoring process exits"


def _loop_functions():
    return [
        obj
        for name, obj in vars(lifespan_workers).items()
        if name.startswith("run_") and name.endswith("_loop") and inspect.iscoroutinefunction(obj)
    ]


def test_registry_is_not_empty():
    assert len(_loop_functions()) >= 20


@pytest.mark.parametrize("loop_fn", _loop_functions(), ids=lambda fn: fn.__name__)
def test_every_background_loop_goes_through_the_gate(loop_fn):
    source = inspect.getsource(loop_fn)
    assert "to_thread(" not in source
    assert "run_long_task(" not in source
    assert "run_background_step(" in source or "run_long_background_step(" in source


def test_lifespan_enables_gate_for_panel_db_and_disables_it_on_shutdown(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app import main

    db_path = tmp_path / "adminpanel.db"
    seen: list[object] = []
    monkeypatch.setattr(
        main, "settings", SimpleNamespace(database_url=f"sqlite:///{db_path}", backup_root=tmp_path / "backups")
    )
    monkeypatch.setattr(main, "seed_database", lambda: None)
    monkeypatch.setattr(main, "restrict_sensitive_file_permissions", lambda _paths: None)
    monkeypatch.setattr(main, "spawn_background_tasks", lambda **_kw: {})
    monkeypatch.setattr(main, "run_leader_startup_actions", lambda: None)
    monkeypatch.setattr(main, "should_start_resource_monitor", lambda: False)

    async def scenario():
        async with main.lifespan(main.app):
            seen.append(background_gate._gate_db_path)

    asyncio.run(scenario())
    assert seen == [db_path]
    assert background_gate._gate_db_path is None


def _result_loops():
    from types import SimpleNamespace

    from app.services import (
        access_expiry_worker,
        alert_rule_worker,
        awg2_expire_worker,
        nightly_idle_restart_worker,
        noc_report_scheduler,
    )

    noc_settings = SimpleNamespace(noc_report_check_interval_seconds=60, noc_report_enabled=True)
    return [
        pytest.param(access_expiry_worker, "run_access_expiry_loop", "_run_once", {"_is_access_expiry_enabled": lambda: True}, id="access_expiry"),
        pytest.param(alert_rule_worker, "run_alert_rules_loop", "run_alert_rules_tick", {"_is_alert_rules_runtime_enabled": lambda: True}, id="alert_rules"),
        pytest.param(awg2_expire_worker, "run_awg2_expire_loop", "run_awg2_expire_once", {"_is_awg2_module_enabled": lambda: True}, id="awg2_expire"),
        pytest.param(
            nightly_idle_restart_worker,
            "run_nightly_idle_restart_loop",
            "run_nightly_idle_restart_once",
            {"_is_nightly_idle_restart_enabled": lambda: True},
            id="nightly_idle_restart",
        ),
        pytest.param(
            noc_report_scheduler,
            "run_noc_report_scheduler_loop",
            "run_noc_report_scheduler_tick",
            {"get_settings": lambda: noc_settings, "_is_telegram_enabled": lambda: True},
            id="noc_report",
        ),
    ]


@pytest.mark.parametrize(("module", "loop_name", "work_name", "patches"), _result_loops())
def test_loops_using_step_result_tolerate_a_skipped_step(gate, monkeypatch, caplog, module, loop_name, work_name, patches):
    from unittest.mock import patch

    for name, value in patches.items():
        monkeypatch.setattr(module, name, value)
    calls: list[str] = []
    monkeypatch.setattr(module, work_name, lambda *_a, **_k: calls.append("work"))
    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps > 3:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(module.asyncio, "sleep", side_effect=fake_sleep):
            await getattr(module, loop_name)()

    pause_background_work(gate, timeout=1)
    caplog.set_level("DEBUG")
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run())

    assert calls == []
    assert any("skipped: backup restore in progress" in r.getMessage() for r in caplog.records)
    assert not [r for r in caplog.records if r.levelname in {"WARNING", "ERROR"}], caplog.text
