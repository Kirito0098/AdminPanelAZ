"""Temporary IP whitelist tests (adapted from AdminAntizapret)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AppSetting
from app.services.security import SecurityService


def _make_session(tmp_path):
    db_path = tmp_path / "temp_whitelist.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add_all(
        [
            AppSetting(key="security_ip_restriction", value="true"),
            AppSetting(key="security_allowed_ips", value="10.0.0.1"),
        ]
    )
    session.commit()
    return session


def test_temporary_allowed_when_enabled(tmp_path):
    session = _make_session(tmp_path)
    service = SecurityService()
    service.add_temp_whitelist(session, "203.0.113.10", hours=1)
    assert service.is_ip_allowed(session, "203.0.113.10") is True
    session.close()


def test_temporary_rejected_when_disabled(tmp_path):
    session = _make_session(tmp_path)
    session.query(AppSetting).filter(AppSetting.key == "security_ip_restriction").update({"value": "false"})
    session.commit()
    service = SecurityService()
    assert service.is_ip_allowed(session, "203.0.113.11") is True
    session.close()


def test_clear_settings_removes_temporary(tmp_path):
    session = _make_session(tmp_path)
    service = SecurityService()
    service.add_temp_whitelist(session, "203.0.113.12", hours=1)
    settings = service.get_settings(session)
    assert len(settings["temp_whitelist"]) == 1
    session.query(AppSetting).filter(AppSetting.key == "security_temp_whitelist").delete()
    session.commit()
    settings = service.get_settings(session)
    assert settings["temp_whitelist"] == []
    session.close()
