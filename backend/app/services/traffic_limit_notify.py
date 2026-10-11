"""Telegram notifications for automatic traffic-limit blocks and unblocks."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import (
    AmneziaWg2AccessPolicy,
    Node,
    OpenVpnAccessPolicy,
    TrafficLimitNotifyState,
    WgAccessPolicy,
)
from app.services.access_policy import AccessPolicyService, is_node_default_policy_client
from app.services.admin_notify import admin_notify_service
from app.services.traffic_limit import (
    TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED,
    get_traffic_limit_period_start,
)

logger = logging.getLogger(__name__)

_POLICY_MODELS = (
    ("openvpn", OpenVpnAccessPolicy),
    ("wg", WgAccessPolicy),
    ("awg2", AmneziaWg2AccessPolicy),
)
_TARGET_TYPES = {"openvpn": "openvpn", "wg": "wireguard", "awg2": "amneziawg2"}


def _state_client_name(protocol_scope: str, client_name: str | None) -> str:
    name = (client_name or "").strip()
    # OpenVPN policy names are case-sensitive; WireGuard and AWG2 rows are stored lowercased.
    return name if protocol_scope == "openvpn" else name.lower()


class TrafficLimitNotifyService:
    def __init__(self, *, admin_notify=None, logger_instance: logging.Logger | None = None):
        self.admin_notify_service = admin_notify or admin_notify_service
        self.logger = logger_instance or logger

    def process_node(
        self,
        db: Session,
        node: Node,
        access_svc: AccessPolicyService,
    ) -> None:
        node_id = node.id
        limited: set[tuple[str, str]] = set()
        for protocol_scope, model in _POLICY_MODELS:
            client_names = [
                row.client_name
                for row in db.query(model)
                .filter_by(node_id=node_id)
                .filter(model.traffic_limit_bytes.isnot(None))
                .all()
                if not is_node_default_policy_client(row.client_name)
            ]
            for client_name in client_names:
                limited.add((protocol_scope, _state_client_name(protocol_scope, client_name)))
                try:
                    self.process_client(
                        db,
                        node=node,
                        protocol_scope=protocol_scope,
                        client_name=client_name,
                        access_svc=access_svc,
                    )
                except Exception as exc:
                    db.rollback()
                    self.logger.warning(
                        "Traffic limit notify error for node=%s %s/%s: %s",
                        node_id,
                        protocol_scope,
                        client_name,
                        exc,
                    )
        self._drop_stale_states(db, node_id, limited)

    def process_client(
        self,
        db: Session,
        *,
        node: Node,
        protocol_scope: str,
        client_name: str,
        access_svc: AccessPolicyService,
    ) -> None:
        name = _state_client_name(protocol_scope, client_name)
        if not name:
            return

        if protocol_scope == "openvpn":
            state = access_svc.get_openvpn_policy(name)
        elif protocol_scope == "wg":
            state = access_svc.get_wg_policy(name)
        elif protocol_scope == "awg2":
            state = access_svc.get_awg2_policy(name)
        else:
            return

        row = (
            db.query(TrafficLimitNotifyState)
            .filter_by(node_id=node.id, protocol=protocol_scope, client_name=name)
            .first()
        )
        if not state.get("traffic_limit_bytes"):
            if row is not None:
                db.delete(row)
                db.commit()
            return

        period_days = state.get("traffic_limit_period_days")
        period_start = self._period_start_key(period_days)
        traffic_blocked = bool(
            state.get("traffic_limit_exceeded")
            and state.get("block_mode") == "traffic_limit"
        )
        target_type = _TARGET_TYPES[protocol_scope]
        prev_blocked = bool(row is not None and row.traffic_blocked)
        if row is None:
            row = TrafficLimitNotifyState(node_id=node.id, protocol=protocol_scope, client_name=name)
            db.add(row)

        if not prev_blocked and traffic_blocked:
            if row.notified_block_period != period_start:
                self._send_block_notification(
                    db,
                    node=node,
                    target_type=target_type,
                    client_name=name,
                    state=state,
                )
                row.notified_block_period = period_start
        elif prev_blocked and not traffic_blocked:
            if (
                period_days in TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED
                and row.last_period_start
                and period_start != row.last_period_start
                and row.notified_unblock_period != period_start
            ):
                self._send_unblock_notification(
                    db,
                    node=node,
                    target_type=target_type,
                    client_name=name,
                    state=state,
                )
                row.notified_unblock_period = period_start

        row.traffic_blocked = traffic_blocked
        row.last_period_start = period_start
        db.commit()

    def _drop_stale_states(self, db: Session, node_id: int, limited: set[tuple[str, str]]) -> None:
        stale = [
            row
            for row in db.query(TrafficLimitNotifyState).filter_by(node_id=node_id).all()
            if (row.protocol, row.client_name) not in limited
        ]
        for row in stale:
            db.delete(row)
        if stale:
            db.commit()

    def _period_start_key(self, period_days) -> str:
        if period_days in TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED:
            period_start = get_traffic_limit_period_start(period_days)
            if period_start is not None:
                return period_start.isoformat()
        return "all-time"

    def _build_details(self, state: dict) -> str:
        parts = [
            f"limit_bytes={int(state.get('traffic_limit_bytes') or 0)}",
            f"consumed_bytes={int(state.get('traffic_consumed_bytes') or 0)}",
        ]
        period_days = state.get("traffic_limit_period_days")
        if period_days is not None:
            parts.append(f"period_days={period_days}")
        unblock_at = (state.get("traffic_limit_unblock_at") or "").strip()
        if unblock_at:
            parts.append(f"unblock_at={unblock_at}")
        return " ".join(parts)

    def _send_block_notification(
        self,
        db: Session,
        *,
        node: Node,
        target_type: str,
        client_name: str,
        state: dict,
    ) -> None:
        self.admin_notify_service.send_traffic_limit_block(
            db,
            target_name=client_name,
            target_type=target_type,
            details=self._build_details(state),
            node_id=node.id,
            node_name=node.name,
        )

    def _send_unblock_notification(
        self,
        db: Session,
        *,
        node: Node,
        target_type: str,
        client_name: str,
        state: dict,
    ) -> None:
        self.admin_notify_service.send_traffic_limit_unblock(
            db,
            target_name=client_name,
            target_type=target_type,
            details=self._build_details(state),
            node_id=node.id,
            node_name=node.name,
        )


traffic_limit_notify_service = TrafficLimitNotifyService()
