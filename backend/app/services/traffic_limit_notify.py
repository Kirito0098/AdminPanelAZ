"""Telegram notifications for automatic traffic-limit blocks and unblocks."""

from __future__ import annotations

import logging
import threading

from sqlalchemy.orm import Session

from app.models import Node, OpenVpnAccessPolicy, WgAccessPolicy
from app.services.access_policy import AccessPolicyService, is_node_default_policy_client
from app.services.admin_notify import admin_notify_service
from app.services.traffic_limit import (
    TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED,
    get_traffic_limit_period_start,
)

logger = logging.getLogger(__name__)


class TrafficLimitNotifyService:
    def __init__(self, *, admin_notify=None, logger_instance: logging.Logger | None = None):
        self.admin_notify_service = admin_notify or admin_notify_service
        self.logger = logger_instance or logger
        self._lock = threading.Lock()
        self._client_state: dict[tuple[int, str, str], dict] = {}

    def process_node(
        self,
        db: Session,
        node: Node,
        access_svc: AccessPolicyService,
    ) -> None:
        wg_clients = [
            row.client_name
            for row in db.query(WgAccessPolicy)
            .filter_by(node_id=node.id)
            .filter(WgAccessPolicy.traffic_limit_bytes.isnot(None))
            .all()
            if not is_node_default_policy_client(row.client_name)
        ]
        ovpn_clients = [
            row.client_name
            for row in db.query(OpenVpnAccessPolicy)
            .filter_by(node_id=node.id)
            .filter(OpenVpnAccessPolicy.traffic_limit_bytes.isnot(None))
            .all()
            if not is_node_default_policy_client(row.client_name)
        ]
        for client_name in wg_clients:
            try:
                self.process_client(
                    db,
                    node=node,
                    protocol_scope="wg",
                    client_name=client_name,
                    access_svc=access_svc,
                )
            except Exception as exc:
                self.logger.warning(
                    "Traffic limit notify error for node=%s wg/%s: %s",
                    node.id,
                    client_name,
                    exc,
                )
        for client_name in ovpn_clients:
            try:
                self.process_client(
                    db,
                    node=node,
                    protocol_scope="openvpn",
                    client_name=client_name,
                    access_svc=access_svc,
                )
            except Exception as exc:
                self.logger.warning(
                    "Traffic limit notify error for node=%s openvpn/%s: %s",
                    node.id,
                    client_name,
                    exc,
                )

    def process_client(
        self,
        db: Session,
        *,
        node: Node,
        protocol_scope: str,
        client_name: str,
        access_svc: AccessPolicyService,
    ) -> None:
        normalized = (client_name or "").strip().lower()
        if not normalized:
            return

        if protocol_scope == "wg":
            state = access_svc.get_wg_policy(normalized)
        elif protocol_scope == "openvpn":
            state = access_svc.get_openvpn_policy(normalized)
        else:
            return

        if not state.get("traffic_limit_bytes"):
            self._forget_client(node.id, protocol_scope, normalized)
            return

        period_days = state.get("traffic_limit_period_days")
        period_start = self._period_start_key(period_days)
        traffic_blocked = bool(
            state.get("traffic_limit_exceeded")
            and state.get("block_mode") == "traffic_limit"
        )
        cache_key = (node.id, protocol_scope, normalized)
        target_type = "openvpn" if protocol_scope == "openvpn" else "wireguard"

        with self._lock:
            cached = self._client_state.get(cache_key)
            prev_blocked = bool(cached.get("traffic_blocked")) if cached else False
            prev_period_start = cached.get("last_period_start") if cached else None

            if not prev_blocked and traffic_blocked:
                if not cached or cached.get("notified_block_period") != period_start:
                    self._send_block_notification(
                        db,
                        node=node,
                        target_type=target_type,
                        client_name=normalized,
                        state=state,
                    )
                    if cached is None:
                        cached = {}
                        self._client_state[cache_key] = cached
                    cached["notified_block_period"] = period_start
            elif prev_blocked and not traffic_blocked:
                if (
                    period_days in TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED
                    and prev_period_start
                    and period_start != prev_period_start
                    and cached.get("notified_unblock_period") != period_start
                ):
                    self._send_unblock_notification(
                        db,
                        node=node,
                        target_type=target_type,
                        client_name=normalized,
                        state=state,
                    )
                    cached["notified_unblock_period"] = period_start

            if cached is None:
                cached = {}
                self._client_state[cache_key] = cached
            cached["traffic_blocked"] = traffic_blocked
            cached["last_period_start"] = period_start

    def _forget_client(self, node_id: int, protocol_scope: str, normalized: str) -> None:
        with self._lock:
            self._client_state.pop((node_id, protocol_scope, normalized), None)

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
