"""Panel-side orchestration: enable / disable mTLS for remote nodes."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Node, User
from app.services.action_log import log_action
from app.services.node_adapter import RemoteNodeAdapter
from app.services.node_manager import (
    check_node_health,
    get_api_key_plain,
    node_metadata_dict,
    update_node_from_health,
)
from app.services.node_mtls_certs import (
    ensure_panel_mtls_materials,
    generate_agent_cert_for_node,
    read_agent_bundle_for_node,
)


def enable_mtls(db: Session, node: Node, actor: User) -> Node:
    if node.is_local:
        raise ValueError("Локальный узел не поддерживает mTLS")
    if node.mtls_enabled:
        raise ValueError("mTLS уже включён для этого узла")

    api_key = get_api_key_plain(node)
    if not api_key:
        raise ValueError("API-ключ узла недоступен")

    pre_health = check_node_health(node, api_key_override=api_key)
    if pre_health.get("status") != "online":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=pre_health.get("error")
            or "Узел недоступен — включение mTLS требует доступного node agent по HTTP",
        )

    ensure_panel_mtls_materials()
    generate_agent_cert_for_node(node.id, node.name)
    bundle = read_agent_bundle_for_node(node.id)

    adapter = RemoteNodeAdapter(
        host=node.host,
        port=node.port,
        api_key=api_key,
        mtls_enabled=False,
    )
    try:
        result = adapter.provision_mtls(bundle)
    finally:
        adapter.close()

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.get("message", "Ошибка provision mTLS на узле"),
        )

    meta = node_metadata_dict(node)
    meta["mtls_provisioned_at"] = datetime.utcnow().isoformat() + "Z"
    node.node_metadata = json.dumps(meta)
    node.mtls_enabled = True
    node.updated_at = datetime.utcnow()
    db.add(node)
    db.commit()
    db.refresh(node)

    post_health = check_node_health(node)
    if post_health.get("status") != "online":
        node.mtls_enabled = False
        node.updated_at = datetime.utcnow()
        db.add(node)
        db.commit()
        db.refresh(node)
        error = post_health.get("error") or "Узел не ответил по HTTPS после включения mTLS"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Сертификаты отправлены, но проверка по HTTPS не прошла: {error}. "
                "Флаг mTLS в панели сброшен — повторите попытку или проверьте node agent."
            ),
        )

    update_node_from_health(node, post_health, db)

    settings = get_settings()
    if settings.audit_log_enabled:
        log_action(
            db,
            action="node_mtls_enable",
            user_id=actor.id,
            username=actor.username,
            details=f"name={node.name}, id={node.id}",
        )
    return node


def disable_mtls(db: Session, node: Node) -> Node:
    if node.is_local:
        raise ValueError("Локальный узел не поддерживает mTLS")

    node.mtls_enabled = False
    node.updated_at = datetime.utcnow()
    db.add(node)
    db.commit()
    db.refresh(node)
    return node
