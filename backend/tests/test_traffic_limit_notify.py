"""Traffic limit Telegram notification tests."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, NodeStatus
from app.services.access_policy import AccessPolicyService
from app.services.traffic_limit_notify import TrafficLimitNotifyService


@pytest.fixture()
def notify_env(tmp_path: Path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    node = Node(
        name="local",
        host="127.0.0.1",
        port=9100,
        is_local=True,
        status=NodeStatus.online,
    )
    session.add(node)
    session.commit()

    consumed_by_client: dict = {}
    sent_events: list[dict] = []

    def _get_consumed(client_name, period_days=None):
        key = (client_name, period_days) if period_days else client_name
        return int(consumed_by_client.get(key, 0))

    adapter = MagicMock()
    adapter.read_config_file.return_value = ""
    svc = AccessPolicyService(
        session,
        antizapret_path=Path("/tmp/az"),
        node_id=node.id,
        adapter=adapter,
    )

    admin_notify = MagicMock()
    admin_notify.send_traffic_limit_block = lambda db, **kwargs: sent_events.append(
        {"event_type": "traffic_limit_block", **kwargs}
    )
    admin_notify.send_traffic_limit_unblock = lambda db, **kwargs: sent_events.append(
        {"event_type": "traffic_limit_unblock", **kwargs}
    )

    notify_service = TrafficLimitNotifyService(admin_notify=admin_notify)

    patcher = patch.object(
        svc,
        "_consumed_bytes",
        side_effect=lambda name, period_days=None: _get_consumed(name, period_days),
    )
    patcher.start()
    yield session, node, svc, notify_service, consumed_by_client, sent_events
    patcher.stop()
    session.close()


def test_block_notification_on_first_exceed(notify_env):
    session, node, svc, notify_service, consumed, sent = notify_env
    consumed["notify-user"] = 2000
    svc.wg_set_traffic_limit("notify-user", 1000, actor="admin")
    sent.clear()

    notify_service.process_client(
        session,
        node=node,
        protocol_scope="wg",
        client_name="notify-user",
        access_svc=svc,
    )

    assert len(sent) == 1
    assert sent[0]["event_type"] == "traffic_limit_block"
    assert sent[0]["target_name"] == "notify-user"
    assert sent[0]["node_id"] == node.id


def test_block_notification_not_repeated_on_reconcile(notify_env):
    session, node, svc, notify_service, consumed, sent = notify_env
    consumed["notify-user"] = 2000
    svc.wg_set_traffic_limit("notify-user", 1000, actor="admin")
    sent.clear()

    for _ in range(3):
        notify_service.process_client(
            session,
            node=node,
            protocol_scope="wg",
            client_name="notify-user",
            access_svc=svc,
        )

    assert len(sent) == 1


def test_block_notification_after_service_restart_is_deduped(notify_env):
    session, node, svc, notify_service, consumed, sent = notify_env
    consumed["notify-user"] = 2000
    svc.wg_set_traffic_limit("notify-user", 1000, actor="admin")
    sent.clear()

    fresh_sent: list[dict] = []
    admin_notify = MagicMock()
    admin_notify.send_traffic_limit_block = lambda db, **kwargs: fresh_sent.append(
        {"event_type": "traffic_limit_block", **kwargs}
    )
    admin_notify.send_traffic_limit_unblock = lambda db, **kwargs: fresh_sent.append(
        {"event_type": "traffic_limit_unblock", **kwargs}
    )
    fresh_service = TrafficLimitNotifyService(admin_notify=admin_notify)

    for _ in range(2):
        fresh_service.process_client(
            session,
            node=node,
            protocol_scope="wg",
            client_name="notify-user",
            access_svc=svc,
        )

    assert len(fresh_sent) == 1
    assert fresh_sent[0]["event_type"] == "traffic_limit_block"


def test_auto_unblock_notification_on_new_period(notify_env):
    session, node, svc, notify_service, consumed, sent = notify_env
    consumed[("period-user", 1)] = 2000
    svc.wg_set_traffic_limit("period-user", 1000, period_days=1, actor="admin")
    notify_service.process_client(
        session,
        node=node,
        protocol_scope="wg",
        client_name="period-user",
        access_svc=svc,
    )
    assert len(sent) == 1
    assert sent[0]["event_type"] == "traffic_limit_block"
    sent.clear()

    consumed[("period-user", 1)] = 0
    with notify_service._lock:
        cached = notify_service._client_state[(node.id, "wg", "period-user")]
        cached["last_period_start"] = "2000-01-01T00:00:00+00:00"

    notify_service.process_client(
        session,
        node=node,
        protocol_scope="wg",
        client_name="period-user",
        access_svc=svc,
    )

    assert len(sent) == 1
    assert sent[0]["event_type"] == "traffic_limit_unblock"


def test_no_unblock_notification_when_limit_increased_same_period(notify_env):
    session, node, svc, notify_service, consumed, sent = notify_env
    consumed["notify-user"] = 2000
    svc.wg_set_traffic_limit("notify-user", 1000, actor="admin")
    notify_service.process_client(
        session,
        node=node,
        protocol_scope="wg",
        client_name="notify-user",
        access_svc=svc,
    )
    sent.clear()
    svc.wg_set_traffic_limit("notify-user", 3000, actor="admin")
    notify_service.process_client(
        session,
        node=node,
        protocol_scope="wg",
        client_name="notify-user",
        access_svc=svc,
    )

    unblock_events = [e for e in sent if e["event_type"] == "traffic_limit_unblock"]
    assert unblock_events == []
