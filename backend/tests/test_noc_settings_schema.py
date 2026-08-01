"""NOC personal schedule fields on settings/auth schemas + PATCH validation helpers."""

import pytest
from fastapi import HTTPException

from app.schemas import AppSettingsResponse, AppSettingsUpdate, UserResponse
from app.services.noc_schedule import parse_cron_dow, parse_hhmm


def _apply_noc_schedule_fields(payload: AppSettingsUpdate, user: dict) -> None:
    """Mirror settings.PATCH validation for NOC schedule fields (admin path)."""
    if payload.noc_daily_time is not None:
        raw = payload.noc_daily_time.strip()
        if raw and parse_hhmm(raw) is None:
            raise HTTPException(status_code=400, detail="Некорректное время ежедневной NOC-сводки")
        user["noc_daily_time"] = raw
    if payload.noc_weekly_time is not None:
        raw = payload.noc_weekly_time.strip()
        if raw and parse_hhmm(raw) is None:
            raise HTTPException(status_code=400, detail="Некорректное время еженедельной NOC-сводки")
        user["noc_weekly_time"] = raw
    if payload.noc_weekly_dow is not None:
        raw = payload.noc_weekly_dow.strip()
        if raw and parse_cron_dow(raw) is None:
            raise HTTPException(status_code=400, detail="Некорректный день недели для NOC-сводки")
        user["noc_weekly_dow"] = raw


def test_schemas_expose_noc_schedule_fields():
    assert "noc_daily_time" in AppSettingsResponse.model_fields
    assert "noc_weekly_dow" in AppSettingsResponse.model_fields
    assert "noc_weekly_time" in AppSettingsResponse.model_fields
    assert "noc_daily_time" in AppSettingsUpdate.model_fields
    assert "noc_weekly_dow" in UserResponse.model_fields


def test_patch_rejects_invalid_hhmm():
    user = {"noc_daily_time": "", "noc_weekly_dow": "", "noc_weekly_time": ""}
    with pytest.raises(HTTPException) as exc:
        _apply_noc_schedule_fields(AppSettingsUpdate(noc_daily_time="25:00"), user)
    assert exc.value.status_code == 400
    assert "ежедневной" in exc.value.detail


def test_patch_accepts_valid_and_clears_empty():
    user = {"noc_daily_time": "11:00", "noc_weekly_dow": "1", "noc_weekly_time": "12:00"}
    _apply_noc_schedule_fields(
        AppSettingsUpdate(noc_daily_time="09:30", noc_weekly_dow="", noc_weekly_time="08:00"),
        user,
    )
    assert user["noc_daily_time"] == "09:30"
    assert user["noc_weekly_dow"] == ""
    assert user["noc_weekly_time"] == "08:00"


def test_patch_rejects_invalid_dow():
    user = {"noc_daily_time": "", "noc_weekly_dow": "", "noc_weekly_time": ""}
    with pytest.raises(HTTPException) as exc:
        _apply_noc_schedule_fields(AppSettingsUpdate(noc_weekly_dow="7"), user)
    assert exc.value.status_code == 400
