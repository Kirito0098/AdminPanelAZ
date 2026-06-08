import ipaddress
import json
import socket
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_password_hash, verify_password
from app.config import get_settings
from app.models import AppSetting, Node, NodeStatus
from app.services.crypto import decrypt_secret, encrypt_secret
from app.services.antizapret import AntiZapretService
from app.services.node_adapter import LocalNodeAdapter, NodeAdapter, RemoteNodeAdapter
from app.services.node_health import HEALTH_METADATA_KEYS

settings = get_settings()
ACTIVE_NODE_KEY = "active_node_id"


def _get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else default


def _set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


def validate_node_host(host: str) -> str:
    host = host.strip()
    if not host:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Хост не может быть пустым")
    if len(host) > 255:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Слишком длинный хост")

    forbidden_schemes = ("http://", "https://", "ftp://", "file://")
    if host.lower().startswith(forbidden_schemes):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите хост без схемы URL")

    try:
        parsed = urlparse(f"//{host}" if "://" not in host else host)
        if parsed.scheme and parsed.scheme not in ("http", "https"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимая схема URL")
        hostname = parsed.hostname or host.split(":")[0]
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный хост") from exc

    if not settings.allow_internal_nodes:
        try:
            addr = ipaddress.ip_address(socket.gethostbyname(hostname))
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Внутренние IP-адреса запрещены (ALLOW_INTERNAL_NODES=true для разрешения)",
                )
        except socket.gaierror:
            if hostname in ("localhost", "127.0.0.1", "::1"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="localhost запрещён для удалённых узлов",
                )
    return hostname


def hash_api_key(api_key: str) -> str:
    return get_password_hash(api_key)


def store_api_key(db_key_hash: str, api_key: str) -> tuple[str, str]:
    return hash_api_key(api_key), encrypt_secret(api_key, settings.secret_key)


def get_api_key_plain(node: Node) -> str | None:
    if node.is_local or not node.api_key_encrypted:
        return None
    try:
        return decrypt_secret(node.api_key_encrypted, settings.secret_key)
    except Exception:
        return None


def node_metadata_dict(node: Node) -> dict:
    try:
        return json.loads(node.node_metadata or "{}")
    except json.JSONDecodeError:
        return {}


def get_active_node_id(db: Session) -> int | None:
    raw = _get_setting(db, ACTIVE_NODE_KEY)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def set_active_node_id(db: Session, node_id: int) -> None:
    _set_setting(db, ACTIVE_NODE_KEY, str(node_id))


def get_active_node(db: Session) -> Node:
    node_id = get_active_node_id(db)
    if node_id:
        node = db.query(Node).filter(Node.id == node_id).first()
        if node:
            return node
    local = db.query(Node).filter(Node.is_local.is_(True)).first()
    if local:
        set_active_node_id(db, local.id)
        db.commit()
        return local
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Активный узел не настроен")


def get_adapter_for_node(node: Node) -> NodeAdapter:
    if node.is_local:
        meta = node_metadata_dict(node)
        raw_path = meta.get("antizapret_path")
        base_path = Path(str(raw_path)) if raw_path else settings.antizapret_path
        return LocalNodeAdapter(AntiZapretService(base_path=base_path))
    api_key = get_api_key_plain(node)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"API-ключ узла '{node.name}' недоступен",
        )
    return RemoteNodeAdapter(host=node.host, port=node.port, api_key=api_key)


def get_active_adapter(db: Session) -> NodeAdapter:
    return get_adapter_for_node(get_active_node(db))


def get_node_antizapret_path(db: Session) -> Path:
    node = get_active_node(db)
    meta = node_metadata_dict(node)
    raw = meta.get("antizapret_path")
    if raw:
        return Path(str(raw))
    return settings.antizapret_path


def ensure_local_node(db: Session) -> Node:
    local = db.query(Node).filter(Node.is_local.is_(True)).first()
    if local:
        return local

    hostname = socket.gethostname()
    local = Node(
        name="Локальный сервер",
        host="127.0.0.1",
        port=9100,
        api_key_hash="",
        api_key_encrypted="",
        is_local=True,
        status=NodeStatus.unknown,
        node_metadata=json.dumps({"hostname": hostname, "antizapret_path": str(settings.antizapret_path)}),
    )
    db.add(local)
    db.commit()
    db.refresh(local)

    if not get_active_node_id(db):
        set_active_node_id(db, local.id)
        db.commit()
    return local


def check_node_health(node: Node, api_key_override: str | None = None) -> dict:
    try:
        if node.is_local:
            adapter = LocalNodeAdapter()
        else:
            api_key = api_key_override or get_api_key_plain(node)
            if not api_key:
                return {"status": "offline", "error": "API-ключ не задан"}
            adapter = RemoteNodeAdapter(host=node.host, port=node.port, api_key=api_key)
        health = adapter.health_check()
        health["status"] = "online"
        return health
    except HTTPException as exc:
        return {"status": "offline", "error": str(exc.detail)}
    except Exception as exc:
        return {"status": "offline", "error": str(exc)}


def update_node_from_health(node: Node, health: dict, db: Session) -> None:
    status_str = health.get("status", "offline")
    node.status = NodeStatus.online if status_str == "online" else NodeStatus.offline
    if status_str == "online":
        node.last_seen_at = datetime.utcnow()
        meta = node_metadata_dict(node)
        for key in HEALTH_METADATA_KEYS:
            if key in health and health[key] is not None:
                meta[key] = health[key]
        if health.get("error"):
            meta["last_error"] = health["error"]
        elif "last_error" in meta:
            meta.pop("last_error", None)
        node.node_metadata = json.dumps(meta)
    elif health.get("error"):
        meta = node_metadata_dict(node)
        meta["last_error"] = health["error"]
        node.node_metadata = json.dumps(meta)
    node.updated_at = datetime.utcnow()
    db.add(node)
    db.commit()
    db.refresh(node)


def verify_node_api_key(node: Node, api_key: str) -> bool:
    if not node.api_key_hash:
        return False
    return verify_password(api_key, node.api_key_hash)
