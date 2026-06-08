"""Tests for action logs CSV export."""

import csv
import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_access_token, get_password_hash
from app.database import Base, get_db
from app.main import app
from app.models import User, UserActionLog, UserRole
from app.services.action_log import log_action


@pytest.fixture()
def action_logs_client(tmp_path):
    db_path = tmp_path / "action_logs.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    admin = User(
        username="export_admin",
        password_hash=get_password_hash("secret123"),
        role=UserRole.admin,
        is_active=True,
    )
    viewer = User(
        username="export_viewer",
        password_hash=get_password_hash("secret123"),
        role=UserRole.viewer,
        is_active=True,
    )
    session.add_all([admin, viewer])
    session.commit()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    token = create_access_token({"sub": admin.username, "role": admin.role.value})
    viewer_token = create_access_token({"sub": viewer.username, "role": viewer.role.value})

    yield client, TestingSession, token, viewer_token

    app.dependency_overrides.clear()
    session.close()


def test_export_action_logs_csv_header_and_row(action_logs_client):
    client, session_factory, token, _ = action_logs_client

    db = session_factory()
    try:
        log_action(
            db,
            action="test_export",
            username="export_admin",
            details="export smoke test",
            remote_addr="10.0.0.1",
        )
        row = db.query(UserActionLog).order_by(UserActionLog.id.desc()).first()
        assert row is not None
        row_id = row.id
    finally:
        db.close()

    response = client.get(
        "/api/logs/action-logs/export",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers.get("content-disposition", "")

    reader = csv.reader(io.StringIO(response.text))
    rows = list(reader)
    assert rows[0] == ["id", "username", "action", "details", "remote_addr", "created_at"]
    assert any(
        r[0] == str(row_id)
        and r[1] == "export_admin"
        and r[2] == "test_export"
        and r[3] == "export smoke test"
        and r[4] == "10.0.0.1"
        for r in rows[1:]
    )


def test_export_action_logs_requires_admin(action_logs_client):
    client, _, _, viewer_token = action_logs_client
    response = client.get(
        "/api/logs/action-logs/export",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert response.status_code == 403
