"""Bot stall detector: a handler that runs too long must leave a stack in the log."""

from __future__ import annotations

import time

import pytest

from app.services import telegram_bot_loop as bot_loop


@pytest.fixture(autouse=True)
def _reset_state():
    bot_loop._end_call()
    yield
    bot_loop._end_call()


def test_reports_a_call_that_runs_longer_than_the_threshold(monkeypatch):
    monkeypatch.setattr(bot_loop, "STALL_REPORT_SECONDS", 60.0)
    bot_loop._begin_call("telegram_bot_service.handle_update")

    report = bot_loop.check_stall(now=time.monotonic() + 61)

    assert report is not None
    assert "telegram_bot_service.handle_update" in report
    assert "61s" in report
    assert "threshold 60s" in report


def test_reports_the_same_stall_only_once(monkeypatch):
    monkeypatch.setattr(bot_loop, "STALL_REPORT_SECONDS", 60.0)
    bot_loop._begin_call("handle_update")
    later = time.monotonic() + 120

    assert bot_loop.check_stall(now=later) is not None
    assert bot_loop.check_stall(now=later + 60) is None


def test_does_not_report_a_short_call(monkeypatch):
    monkeypatch.setattr(bot_loop, "STALL_REPORT_SECONDS", 60.0)
    bot_loop._begin_call("handle_update")

    assert bot_loop.check_stall(now=time.monotonic() + 5) is None


def test_does_not_report_when_the_bot_is_idle(monkeypatch):
    monkeypatch.setattr(bot_loop, "STALL_REPORT_SECONDS", 60.0)

    assert bot_loop.check_stall(now=time.monotonic() + 3600) is None


def test_finished_call_clears_the_state(monkeypatch):
    monkeypatch.setattr(bot_loop, "STALL_REPORT_SECONDS", 60.0)
    bot_loop._begin_call("handle_update")
    bot_loop._end_call()

    assert bot_loop.check_stall(now=time.monotonic() + 3600) is None
