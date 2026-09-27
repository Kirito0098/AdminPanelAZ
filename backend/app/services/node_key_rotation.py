"""Automatic and manual NODE_AGENT_API_KEY rotation."""

from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import Node
from app.services.action_log import log_action
from app.services.node_manager import (
    NODE_KIND_VPN,
    get_adapter_for_node,
    get_api_key_plain,
    is_vpn_node,
    store_api_key,
)
from app.services.background_gate import run_background_step

logger = logging.getLogger(__name__)


def generate_api_key() -> str:
    return secrets.token_hex(32)


def rotate_node_api_key(db: Session, node: Node, *, actor_username: str | None = None) -> str:
    if node.is_local:
        raise ValueError("Локальный узел не поддерживает ротацию API-ключа")
    if not is_vpn_node(node):
        raise ValueError("Прокси-узел не поддерживает ротацию API-ключа")

    old_key = get_api_key_plain(node)
    if not old_key:
        raise ValueError("API-ключ узла недоступен")

    new_key = generate_api_key()
    get_adapter_for_node(node).rotate_api_key(new_key)

    key_hash, key_encrypted = store_api_key("", new_key)
    node.api_key_hash = key_hash
    node.api_key_encrypted = key_encrypted
    node.api_key_rotated_at = datetime.utcnow()
    node.updated_at = node.api_key_rotated_at
    db.add(node)
    db.commit()
    db.refresh(node)

    settings = get_settings()
    if settings.audit_log_enabled:
        log_action(
            db,
            action="node_api_key_rotate",
            username=actor_username,
            details=f"name={node.name}, id={node.id}",
        )
    return new_key


def _nodes_due_for_rotation(db: Session) -> list[Node]:
    settings = get_settings()
    if settings.node_api_key_rotation_days <= 0:
        return []
    cutoff = datetime.utcnow() - timedelta(days=settings.node_api_key_rotation_days)
    return (
        db.query(Node)
        .filter(
            Node.is_local.is_(False),
            func.coalesce(Node.node_kind, NODE_KIND_VPN) == NODE_KIND_VPN,
            func.coalesce(Node.api_key_rotated_at, Node.created_at) <= cutoff,
        )
        .all()
    )


def _is_key_rotation_enabled() -> bool:
    """Runtime gate — FEATURE_KEY_ROTATION_ENABLED can flip without restart."""
    from app.services.feature_guards import get_feature_service

    settings = get_settings()
    return bool(settings.node_api_key_rotation_days > 0) and get_feature_service().is_enabled("key_rotation")


def _rotate_due_nodes_once() -> None:
    db = SessionLocal()
    try:
        for node in _nodes_due_for_rotation(db):
            try:
                rotate_node_api_key(db, node, actor_username="system")
                logger.info("Rotated API key for node %s (id=%s)", node.name, node.id)
            except Exception as exc:
                db.rollback()
                logger.warning("Failed to rotate API key for node %s: %s", node.name, exc)
    finally:
        db.close()


async def run_node_key_rotation_loop() -> None:
    """Key rotation loop — re-checks FEATURE_KEY_ROTATION_ENABLED and settings each tick."""
    while True:
        settings = get_settings()
        interval = max(3600, int(settings.node_api_key_rotation_check_hours or 24) * 3600)
        await asyncio.sleep(interval)
        try:
            if not _is_key_rotation_enabled():
                logger.debug("node_key_rotation skipped — FEATURE_KEY_ROTATION_ENABLED disabled or rotation days off")
                continue
            # Agent calls are blocking HTTP with a 30 s timeout per node.
            await run_background_step(_rotate_due_nodes_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("node_key_rotation iteration failed")
