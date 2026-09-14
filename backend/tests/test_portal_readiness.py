from app.services.portal_readiness import parse_portal_readiness_trailer


def test_parse_trailer_basic():
    raw = """
[nginx-setup] noise
READY=false
ISSUES=hash_bucket_low
SUGGESTED_PORTAL_DOMAIN=portal.example.com
MIGRATED_TO=
ACTIONS_TAKEN=
PORTAL_DOMAIN=portal.panel.example.com
MESSAGE=Нужна подготовка
"""
    p = parse_portal_readiness_trailer(raw)
    assert p["ready"] is False
    assert p["issues"] == ["hash_bucket_low"]
    assert p["suggested_portal_domain"] == "portal.example.com"
    assert p["migrated_to"] == ""
    assert p["portal_domain"] == "portal.panel.example.com"
    assert p["message"] == "Нужна подготовка"


def test_parse_trailer_ready_true():
    p = parse_portal_readiness_trailer("READY=true\nISSUES=\nMESSAGE=OK\n")
    assert p["ready"] is True
    assert p["issues"] == []


def test_task_prepare_keeps_nested_portal_domain():
    """Prepare must not rewrite DB portal_domain for nested hosts (or MIGRATED_TO)."""
    from unittest.mock import patch

    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.database import Base
    from app.services import background_tasks as bg_tasks
    from app.services.background_tasks import BackgroundTaskService
    from app.services.client_portal import get_portal_domain, set_portal_domain

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db_session = Session()
    try:
        set_portal_domain(db_session, "portal.panel.example.com", panel_domain="panel.example.com")
        db_session.commit()
        assert get_portal_domain(db_session) == "portal.panel.example.com"

        stdout = "\n".join(
            [
                "READY=true",
                "ISSUES=",
                "SUGGESTED_PORTAL_DOMAIN=portal.example.com",
                "MIGRATED_TO=portal.example.com",
                "ACTIONS_TAKEN=synced_portal_domain_env",
                "PORTAL_DOMAIN=portal.panel.example.com",
                "MESSAGE=Портал готов к настройке",
            ]
        )

        svc = BackgroundTaskService()
        svc.run_checked_command = lambda *a, **k: (stdout, "")  # type: ignore[assignment]

        with patch.object(bg_tasks, "SessionLocal", lambda: db_session):
            result = svc.task_portal_readiness(
                {
                    "portal_domain": "portal.panel.example.com",
                    "domain": "panel.example.com",
                    "publish_mode": "nginx_le",
                },
                mode="prepare",
            )

        assert result["ready"] is True
        assert result["portal_domain"] == "portal.panel.example.com"
        # Even if trailer wrongly had MIGRATED_TO, DB must stay nested host.
        assert get_portal_domain(db_session) == "portal.panel.example.com"
    finally:
        db_session.close()
        engine.dispose()
