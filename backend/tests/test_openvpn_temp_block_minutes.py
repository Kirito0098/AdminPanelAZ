"""Short OpenVPN temp block (minutes) used by «disconnect device + block»."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus, OpenVpnAccessPolicy
from app.services.access_policy import AccessPolicyService


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine)
    session = make()
    session.add(Node(id=1, name="1Cent-EE", host="h", is_local=True, status=NodeStatus.online))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _service(db, tmp_path: Path, monkeypatch) -> tuple[AccessPolicyService, list[str]]:
    service = AccessPolicyService(
        db,
        antizapret_path=tmp_path,
        node_id=1,
        node_name="1Cent-EE",
        adapter=SimpleNamespace(),
    )
    reconciled: list[str] = []
    monkeypatch.setattr(service, "reconcile_openvpn", lambda name: reconciled.append(name))
    return service, reconciled


def test_temp_block_minutes_blocks_until_the_deadline(db, tmp_path, monkeypatch):
    service, reconciled = _service(db, tmp_path, monkeypatch)
    before = datetime.now(timezone.utc).replace(tzinfo=None)

    state = service.openvpn_temp_block_minutes("bob", 15, actor="admin")

    row = db.query(OpenVpnAccessPolicy).filter_by(node_id=1, client_name="bob").one()
    assert row.is_temp_blocked is True
    assert row.is_permanent_blocked is False
    assert row.block_reason == "manual_temp"
    assert row.block_days is None
    assert row.updated_by == "admin"
    assert row.block_until is not None
    seconds = (row.block_until - before).total_seconds()
    assert 890 <= seconds <= 910
    assert state["is_blocked"] is True
    assert reconciled == ["bob"]


def test_temp_block_minutes_rejects_a_zero_window(db, tmp_path, monkeypatch):
    service, reconciled = _service(db, tmp_path, monkeypatch)

    with pytest.raises(ValueError):
        service.openvpn_temp_block_minutes("bob", 0)

    assert reconciled == []
