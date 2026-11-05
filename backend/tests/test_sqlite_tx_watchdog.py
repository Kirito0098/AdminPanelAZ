"""Watchdog долгих транзакций записи SQLite: отчёт со стеком, один раз на транзакцию."""

from __future__ import annotations

from app.services import sqlite_tx_watchdog as wdt


def _reset() -> None:
    with wdt._lock:
        wdt._active.clear()
        wdt._reported.clear()


def test_long_write_transaction_reported_once():
    _reset()
    wdt.mark_write_started("UPDATE users SET is_active = 1", now=100.0)

    assert wdt.check_stalls(now=102.0) == []

    reports = wdt.check_stalls(now=130.0)
    assert len(reports) == 1
    assert "SQLite write transaction open 30s" in reports[0]
    assert "UPDATE users SET is_active = 1" in reports[0]
    assert "test_sqlite_tx_watchdog" in reports[0]

    # Повторно ту же транзакцию не репортим.
    assert wdt.check_stalls(now=140.0) == []

    wdt.mark_write_finished()
    assert wdt.check_stalls(now=200.0) == []


def test_write_detection_ignores_reads():
    assert not wdt._is_write_statement("SELECT * FROM users")
    assert not wdt._is_write_statement("SAVEPOINT sp1")
    assert wdt._is_write_statement("  insert into t values (1)")
    assert wdt._is_write_statement("DELETE FROM user_traffic_sample")
    assert wdt._is_write_statement("update wg_access_policy set x=1")
