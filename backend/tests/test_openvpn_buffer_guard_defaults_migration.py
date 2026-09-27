from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, migrate_factory_buffer_guard_thresholds
from app.models import Node, OpenVpnBufferGuardSettings


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine)()


def test_migrate_factory_500_by_mode():
    engine, db = _session()
    try:
        n1 = Node(name="a", host="127.0.0.1", is_local=True)
        n2 = Node(name="b", host="10.0.0.2", is_local=False)
        n3 = Node(name="c", host="10.0.0.3", is_local=False)
        db.add_all([n1, n2, n3])
        db.commit()
        db.add_all(
            [
                OpenVpnBufferGuardSettings(
                    node_id=n1.id,
                    enabled=True,
                    mode="notify",
                    threshold_count=500,
                    window_seconds=60,
                ),
                OpenVpnBufferGuardSettings(
                    node_id=n2.id,
                    enabled=False,
                    mode="kill_restart",
                    threshold_count=500,
                    window_seconds=60,
                ),
                OpenVpnBufferGuardSettings(
                    node_id=n3.id,
                    enabled=False,
                    mode="kill",
                    threshold_count=499,
                    window_seconds=60,
                ),
            ]
        )
        db.commit()

        with engine.begin() as conn:
            updated = migrate_factory_buffer_guard_thresholds(conn)
        assert updated == 2

        db.expire_all()
        s1 = db.query(OpenVpnBufferGuardSettings).filter_by(node_id=n1.id).one()
        s2 = db.query(OpenVpnBufferGuardSettings).filter_by(node_id=n2.id).one()
        s3 = db.query(OpenVpnBufferGuardSettings).filter_by(node_id=n3.id).one()
        assert s1.threshold_count == 40
        assert s2.threshold_count == 120
        assert s3.threshold_count == 499
        assert s1.mode == "notify"
        assert s2.mode == "kill_restart"
    finally:
        db.close()
        engine.dispose()


def test_factory_threshold_migration_runs_once(monkeypatch):
    from app import database

    engine, db = _session()
    monkeypatch.setattr(database, "engine", engine)
    try:
        node = Node(name="a", host="127.0.0.1", is_local=True)
        db.add(node)
        db.commit()
        row = OpenVpnBufferGuardSettings(node_id=node.id, mode="notify", threshold_count=500, window_seconds=60)
        db.add(row)
        db.commit()

        database._migrate_openvpn_buffer_guard_factory_thresholds()
        db.refresh(row)
        assert row.threshold_count == 40

        # Администратор сам выставил 500/60 — следующий запуск панели их не трогает.
        row.threshold_count = 500
        db.commit()
        database._migrate_openvpn_buffer_guard_factory_thresholds()
        db.refresh(row)
        assert row.threshold_count == 500
    finally:
        db.close()
        engine.dispose()
