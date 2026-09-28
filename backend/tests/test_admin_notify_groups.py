"""TG notify groups catalog consistency + API (Task 1)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import require_admin
from app.database import Base, get_db
import app.models  # noqa: F401 — register ORM models on Base.metadata
from app.models import DEFAULT_TG_NOTIFY_EVENTS, User, UserRole
from app.routers import settings_telegram as settings_router
from app.routers.tg_mini.settings import _mini_notify_settings_response
from app.services.admin_notify import PERSONAL_OWNER_NOTIFY_KEY_ORDER, TG_NOTIFY_EVENT_GROUPS


def _group_keys() -> dict[str, list[str]]:
    return {group_id: list(keys) for group_id, _title, _icon, keys in TG_NOTIFY_EVENT_GROUPS}


def test_every_default_key_in_exactly_one_group():
    seen: dict[str, str] = {}
    for group_id, keys in _group_keys().items():
        assert keys, f"group {group_id} must not be empty"
        for key in keys:
            assert key not in seen, f"key {key} in both {seen[key]} and {group_id}"
            seen[key] = group_id
    assert set(seen) == set(DEFAULT_TG_NOTIFY_EVENTS), (
        f"missing={set(DEFAULT_TG_NOTIFY_EVENTS) - set(seen)} "
        f"extra={set(seen) - set(DEFAULT_TG_NOTIFY_EVENTS)}"
    )


def test_nine_groups_with_titles_and_icons():
    assert len(TG_NOTIFY_EVENT_GROUPS) == 9
    for group_id, title, icon, keys in TG_NOTIFY_EVENT_GROUPS:
        assert group_id and title and icon and keys


def _client(db, admin: User) -> TestClient:
    app = FastAPI()
    app.include_router(settings_router.router, prefix="/api")
    app.dependency_overrides[require_admin] = lambda: admin

    def _override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def test_admin_notify_get_returns_groups_and_event_group():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        admin = User(username="admin", role=UserRole.admin, password_hash="x")
        db.add(admin)
        db.commit()
        db.refresh(admin)
        client = _client(db, admin)
        resp = client.get("/api/settings/admin-notify")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # events kept (additive API), each item gains group
        assert body["events"], "events must be kept"
        groups = body["groups"]
        assert len(groups) == 9
        key_to_group = {g["group"]: g for g in groups}
        for item in body["events"]:
            assert item["group"] in key_to_group, f"unknown group for {item['key']}"
            assert item["key"] in key_to_group[item["group"]]["keys"]
        # groups cover all events exactly once
        all_keys = [k for g in groups for k in g["keys"]]
        assert sorted(all_keys) == sorted(item["key"] for item in body["events"])
        assert len(set(all_keys)) == len(all_keys)
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_mini_notify_non_admin_single_owner_group_admin_passthrough():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        owner = User(username="owner", role=UserRole.user, password_hash="x")
        admin = User(username="admin", role=UserRole.admin, password_hash="x")
        db.add_all([owner, admin])
        db.commit()
        db.refresh(owner)
        db.refresh(admin)

        mini = _mini_notify_settings_response(db, owner)
        assert [e.key for e in mini.events] == list(PERSONAL_OWNER_NOTIFY_KEY_ORDER)
        assert all(e.group == "owner_reminders" for e in mini.events)
        assert len(mini.groups) == 1
        group = mini.groups[0]
        assert group.group == "owner_reminders"
        assert group.title == "Мои напоминания"
        assert group.icon
        assert group.keys == list(PERSONAL_OWNER_NOTIFY_KEY_ORDER)

        admin_resp = _mini_notify_settings_response(db, admin)
        assert len(admin_resp.groups) == 9
        assert len(admin_resp.events) == len(DEFAULT_TG_NOTIFY_EVENTS)
        assert {e.key for e in admin_resp.events} == set(DEFAULT_TG_NOTIFY_EVENTS)
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
