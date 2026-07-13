"""Tests for user config ACL and can_create_configs."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models import UserRole
from app.services.config_access import (
    can_mutate_config,
    can_view_config,
    matches_user_config_grant,
)
from app.services.self_service import build_quota_payload, enforce_user_can_create_config


class _FakeGrantQuery:
    def __init__(self, grants: list[str]):
        self._grants = grants

    def filter_by(self, **_kwargs):
        return self

    def all(self):
        return [SimpleNamespace(config_group=g) for g in self._grants]

    def delete(self):
        return None


class _FakeDb:
    def __init__(self, grants: list[str] | None = None, setting_value: str | None = None):
        self.grants = grants or []
        self.setting_value = setting_value

    def query(self, *models):
        model = models[0] if models else None
        name = getattr(model, "__name__", str(model))
        # column entities: VpnConfig.client_name etc.
        if hasattr(model, "class_") or "VpnConfig" in name or "client_name" in name.lower():
            return _FakeVpnCountQuery(0)
        if "UserConfigAccess" in name or name.endswith("UserConfigAccess"):
            return _FakeGrantQuery(self.grants)
        if "AppSetting" in name or name.endswith("AppSetting"):
            return _FakeSettingQuery(self.setting_value)
        return _FakeGrantQuery([])

    def add(self, _obj):
        return None

    def commit(self):
        return None


class _FakeSettingQuery:
    def __init__(self, value: str | None):
        self._value = value

    def filter(self, *_a, **_k):
        return self

    def first(self):
        if self._value is None:
            return None
        return SimpleNamespace(value=self._value)


class _FakeVpnCountQuery:
    def __init__(self, count: int):
        self._count = count

    def filter(self, *_a, **_k):
        return self

    def distinct(self):
        return self

    def all(self):
        return []


def test_can_view_owned_without_grant():
    user = SimpleNamespace(id=1, role=UserRole.user)
    config = SimpleNamespace(owner_id=1, client_name="alice")
    db = _FakeDb(grants=[])
    assert can_view_config(user, config, db) is True
    assert can_mutate_config(user, config) is True


def test_can_view_grant_but_not_mutate():
    user = SimpleNamespace(id=2, role=UserRole.user)
    config = SimpleNamespace(owner_id=99, client_name="shared-client")
    db = _FakeDb(grants=["shared-client"])
    assert can_view_config(user, config, db) is True
    assert can_mutate_config(user, config) is False


def test_grant_prefix_match():
    db = _FakeDb(grants=["team-"])
    assert matches_user_config_grant(db, 1, "team-alice") is True
    assert matches_user_config_grant(db, 1, "other") is False


def test_no_access_without_owner_or_grant():
    user = SimpleNamespace(id=2, role=UserRole.user)
    config = SimpleNamespace(owner_id=99, client_name="secret")
    db = _FakeDb(grants=[])
    assert can_view_config(user, config, db) is False
    assert can_mutate_config(user, config) is False


def test_admin_always_view_and_mutate():
    user = SimpleNamespace(id=1, role=UserRole.admin)
    config = SimpleNamespace(owner_id=99, client_name="x")
    db = _FakeDb(grants=[])
    assert can_view_config(user, config, db) is True
    assert can_mutate_config(user, config) is True


def test_can_create_flag_false_blocks_create():
    user = SimpleNamespace(
        id=3,
        role=UserRole.user,
        can_create_configs=False,
        config_quota=None,
    )
    db = _FakeDb(setting_value="5")
    payload = build_quota_payload(db, user)
    assert payload["can_create"] is False
    with pytest.raises(HTTPException) as exc:
        enforce_user_can_create_config(db, user)
    assert exc.value.status_code == 403


def test_can_create_flag_true_under_quota():
    user = SimpleNamespace(
        id=3,
        role=UserRole.user,
        can_create_configs=True,
        config_quota=5,
    )
    db = _FakeDb(setting_value="5")
    payload = build_quota_payload(db, user)
    assert payload["can_create"] is True


def test_can_create_false_even_when_unlimited():
    """can_create_configs=false must block create even if quota is unlimited."""
    user = SimpleNamespace(
        id=4,
        role=UserRole.user,
        can_create_configs=False,
        config_quota=0,  # 0 / None → unlimited in self_service
    )
    db = _FakeDb(setting_value="0")
    payload = build_quota_payload(db, user)
    assert payload["unlimited"] is True
    assert payload["can_create"] is False
    with pytest.raises(HTTPException) as exc:
        enforce_user_can_create_config(db, user)
    assert exc.value.status_code == 403


def test_user_role_enum_has_no_viewer():
    assert set(UserRole.__members__) == {"admin", "user"}
    assert "viewer" not in UserRole.__members__
