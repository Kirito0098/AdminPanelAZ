from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.services.noc_schedule import (
    parse_hhmm,
    parse_cron_dow,
    should_run_daily,
    should_run_weekly,
)


def test_parse_hhmm_valid_and_invalid():
    assert parse_hhmm("11:00") == (11, 0)
    assert parse_hhmm(" 9:05 ") == (9, 5)
    assert parse_hhmm("") is None
    assert parse_hhmm("25:00") is None
    assert parse_hhmm("ab:cd") is None


def test_parse_cron_dow():
    assert parse_cron_dow("1") == 1
    assert parse_cron_dow("0") == 0
    assert parse_cron_dow("7") is None
    assert parse_cron_dow("") is None


def test_daily_personal_matches_moscow_not_utc():
    # 08:00 UTC == 11:00 Europe/Moscow
    user = SimpleNamespace(
        timezone="",
        last_client_timezone="Europe/Moscow",
        noc_daily_time="11:00",
        noc_weekly_dow="",
        noc_weekly_time="",
    )
    now = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
    assert should_run_daily(user, now_utc=now, env_daily_cron="0 8 * * *") is True
    earlier = datetime(2026, 8, 1, 7, 0, tzinfo=timezone.utc)
    assert should_run_daily(user, now_utc=earlier, env_daily_cron="0 8 * * *") is False


def test_daily_empty_falls_back_to_env_utc_cron():
    user = SimpleNamespace(
        timezone="Europe/Moscow",
        last_client_timezone="",
        noc_daily_time="",
        noc_weekly_dow="",
        noc_weekly_time="",
    )
    now = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
    assert should_run_daily(user, now_utc=now, env_daily_cron="0 8 * * *") is True
    # 11:00 MSK would be wrong for empty personal + env 08:00 UTC only
    at_msk_11_as_utc = datetime(2026, 8, 1, 11, 0, tzinfo=timezone.utc)
    assert should_run_daily(user, now_utc=at_msk_11_as_utc, env_daily_cron="0 8 * * *") is False


def test_weekly_requires_both_fields_else_env():
    user = SimpleNamespace(
        timezone="Europe/Moscow",
        last_client_timezone="",
        noc_daily_time="",
        noc_weekly_dow="1",  # Monday
        noc_weekly_time="",  # incomplete → env
    )
    # Monday 09:00 UTC
    now = datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc)  # 2026-08-03 is Monday
    assert should_run_weekly(user, now_utc=now, env_weekly_cron="0 9 * * 1") is True

    user2 = SimpleNamespace(
        timezone="Europe/Moscow",
        last_client_timezone="",
        noc_daily_time="",
        noc_weekly_dow="1",
        noc_weekly_time="12:00",
    )
    # Monday 09:00 UTC = 12:00 MSK
    assert should_run_weekly(user2, now_utc=now, env_weekly_cron="0 9 * * 1") is True
    assert should_run_weekly(
        user2,
        now_utc=datetime(2026, 8, 3, 8, 0, tzinfo=timezone.utc),
        env_weekly_cron="0 9 * * 1",
    ) is False


def test_scheduler_sends_only_matching_user(monkeypatch):
    from unittest.mock import MagicMock
    from app.services import noc_report_scheduler as sched
    from app.services.noc_report_scheduler import process_user_noc_tick

    u_match = SimpleNamespace(
        id=1, telegram_id="1", role="admin",
        timezone="Europe/Moscow", last_client_timezone="",
        noc_daily_time="11:00", noc_weekly_dow="", noc_weekly_time="",
        has_tg_notify_event=lambda k: True,
    )
    u_other = SimpleNamespace(
        id=2, telegram_id="2", role="admin",
        timezone="Europe/Moscow", last_client_timezone="",
        noc_daily_time="15:00", noc_weekly_dow="", noc_weekly_time="",
        has_tg_notify_event=lambda k: True,
    )
    sent: list[int] = []

    monkeypatch.setattr(sched, "get_settings", lambda: SimpleNamespace(
        noc_report_enabled=True,
        noc_report_daily_cron="0 8 * * *",
        noc_report_weekly_cron="0 9 * * 1",
        noc_report_weekly_image_enabled=False,
    ))
    monkeypatch.setattr(sched, "SessionLocal", lambda: MagicMock())
    monkeypatch.setattr(
        "app.services.noc_report_scheduler.send_noc_report",
        lambda db, period, recipients=None: sent.append(recipients[0].id) or {
            "status": "sent",
            "sent": 1,
            "recipients": 1,
        },
    )
    now = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
    db = MagicMock()
    monkeypatch.setattr(sched, "_already_ran_local_minute", lambda *a, **k: False)
    monkeypatch.setattr(sched, "_set_setting", lambda *a, **k: None)

    process_user_noc_tick(db, u_match, now=now, settings=sched.get_settings())
    process_user_noc_tick(db, u_other, now=now, settings=sched.get_settings())
    assert sent == [1]
