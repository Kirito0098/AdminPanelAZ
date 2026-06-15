import logging

from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings
from app.paths import BACKEND_ROOT

logger = logging.getLogger(__name__)
settings = get_settings()
_is_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False, "timeout": 30} if _is_sqlite else {}
engine = create_engine(settings.database_url, connect_args=connect_args)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    if not _is_sqlite:
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def resolve_main_db_path() -> Path:
    db_url = get_settings().database_url
    if db_url.startswith("sqlite:///"):
        db_path = Path(db_url.replace("sqlite:///", ""))
        if not db_path.is_absolute():
            db_path = BACKEND_ROOT / db_path
        return db_path.resolve()
    return (BACKEND_ROOT / "data" / "adminpanel.db").resolve()


def _migrate_vpn_configs_node_scope() -> None:
    """Recreate vpn_configs with per-node scope (node_id + unique per node)."""
    inspector = inspect(engine)
    if "vpn_configs" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("vpn_configs")}
    if "node_id" in cols:
        return

    from app.models import Node, VpnType
    from app.services.node_adapter import LocalNodeAdapter, RemoteNodeAdapter
    from app.services.node_manager import get_active_node_id, get_api_key_plain

    db = SessionLocal()
    try:
        local = db.query(Node).filter(Node.is_local.is_(True)).first()
        if not local:
            logger.warning("DB migration: skip vpn_configs node scope — local node missing")
            return

        active_id = get_active_node_id(db) or local.id
        node_clients: dict[int, tuple[set[str], set[str]]] = {}

        local_adapter = LocalNodeAdapter()
        node_clients[local.id] = (
            set(local_adapter.list_openvpn_clients()),
            set(local_adapter.list_wireguard_clients()),
        )
        for node in db.query(Node).filter(Node.is_local.is_(False)).all():
            api_key = get_api_key_plain(node)
            if not api_key:
                continue
            try:
                adapter = RemoteNodeAdapter(
                    host=node.host,
                    port=node.port,
                    api_key=api_key,
                    mtls_enabled=bool(node.mtls_enabled),
                )
                node_clients[node.id] = (
                    set(adapter.list_openvpn_clients()),
                    set(adapter.list_wireguard_clients()),
                )
            except Exception:
                logger.debug("DB migration: skip node %s client scan", node.id, exc_info=True)

        def resolve_node_id(client_name: str, vpn_type: str) -> int:
            for node_id, (ovpn, wg) in node_clients.items():
                if vpn_type == VpnType.openvpn.value and client_name in ovpn:
                    return node_id
                if vpn_type == VpnType.wireguard.value and client_name in wg:
                    return node_id
            return active_id

        old_rows = db.execute(
            text(
                "SELECT id, client_name, vpn_type, owner_id, cert_expire_days, description, "
                "created_at, updated_at FROM vpn_configs"
            )
        ).mappings().all()

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE vpn_configs_new (
                        id INTEGER NOT NULL PRIMARY KEY,
                        node_id INTEGER NOT NULL,
                        client_name VARCHAR(32) NOT NULL,
                        vpn_type VARCHAR(16) NOT NULL,
                        owner_id INTEGER NOT NULL,
                        cert_expire_days INTEGER,
                        description VARCHAR(255),
                        created_at DATETIME,
                        updated_at DATETIME,
                        FOREIGN KEY(node_id) REFERENCES nodes (id),
                        FOREIGN KEY(owner_id) REFERENCES users (id),
                        UNIQUE (node_id, client_name, vpn_type)
                    )
                    """
                )
            )
            for row in old_rows:
                node_id = resolve_node_id(row["client_name"], row["vpn_type"])
                conn.execute(
                    text(
                        """
                        INSERT INTO vpn_configs_new (
                            id, node_id, client_name, vpn_type, owner_id,
                            cert_expire_days, description, created_at, updated_at
                        ) VALUES (
                            :id, :node_id, :client_name, :vpn_type, :owner_id,
                            :cert_expire_days, :description, :created_at, :updated_at
                        )
                        """
                    ),
                    {**dict(row), "node_id": node_id},
                )
            conn.execute(text("DROP TABLE vpn_configs"))
            conn.execute(text("ALTER TABLE vpn_configs_new RENAME TO vpn_configs"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_vpn_configs_node_id ON vpn_configs (node_id)"))
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_vpn_configs_client_name ON vpn_configs (client_name)")
            )
        logger.info("DB migration: vpn_configs scoped by node_id (%d rows)", len(old_rows))
    finally:
        db.close()


def _migrate_access_policy_node_scope() -> None:
    """Add node_id to openvpn/wg access policy tables (per-node client policies)."""
    inspector = inspect(engine)
    tables = ("openvpn_access_policy", "wg_access_policy")
    if not all(t in inspector.get_table_names() for t in tables):
        return
    ovpn_cols = {col["name"] for col in inspector.get_columns("openvpn_access_policy")}
    if "node_id" in ovpn_cols:
        return

    from app.models import Node

    db = SessionLocal()
    try:
        local = db.query(Node).filter(Node.is_local.is_(True)).first()
        if not local:
            local = db.query(Node).order_by(Node.id).first()
        if not local:
            logger.warning("DB migration: skip access policy node scope — no nodes")
            return
        default_node_id = local.id

        def _recreate_policy_table(table: str, columns: str) -> None:
            old_rows = db.execute(text(f"SELECT {columns} FROM {table}")).mappings().all()
            with engine.begin() as conn:
                conn.execute(
                    text(
                        f"""
                        CREATE TABLE {table}_new (
                            id INTEGER NOT NULL PRIMARY KEY,
                            node_id INTEGER NOT NULL,
                            client_name VARCHAR(64) NOT NULL,
                            expires_at DATETIME,
                            is_temp_blocked BOOLEAN,
                            is_permanent_blocked BOOLEAN,
                            block_reason VARCHAR(32),
                            block_started_at DATETIME,
                            block_days INTEGER,
                            block_until DATETIME,
                            traffic_limit_bytes BIGINT,
                            traffic_limit_period_days INTEGER,
                            updated_by VARCHAR(64),
                            updated_at DATETIME,
                            FOREIGN KEY(node_id) REFERENCES nodes (id),
                            UNIQUE (node_id, client_name)
                        )
                        """
                        if table == "wg_access_policy"
                        else f"""
                        CREATE TABLE {table}_new (
                            id INTEGER NOT NULL PRIMARY KEY,
                            node_id INTEGER NOT NULL,
                            client_name VARCHAR(64) NOT NULL,
                            is_temp_blocked BOOLEAN,
                            is_permanent_blocked BOOLEAN,
                            block_reason VARCHAR(32),
                            block_started_at DATETIME,
                            block_days INTEGER,
                            block_until DATETIME,
                            traffic_limit_bytes BIGINT,
                            traffic_limit_period_days INTEGER,
                            updated_by VARCHAR(64),
                            updated_at DATETIME,
                            FOREIGN KEY(node_id) REFERENCES nodes (id),
                            UNIQUE (node_id, client_name)
                        )
                        """
                    )
                )
                for row in old_rows:
                    conn.execute(
                        text(
                            f"""
                            INSERT INTO {table}_new (
                                id, node_id, client_name, is_temp_blocked, is_permanent_blocked,
                                block_reason, block_started_at, block_days, block_until,
                                traffic_limit_bytes, traffic_limit_period_days, updated_by, updated_at
                                {", expires_at" if table == "wg_access_policy" else ""}
                            ) VALUES (
                                :id, :node_id, :client_name, :is_temp_blocked, :is_permanent_blocked,
                                :block_reason, :block_started_at, :block_days, :block_until,
                                :traffic_limit_bytes, :traffic_limit_period_days, :updated_by, :updated_at
                                {", :expires_at" if table == "wg_access_policy" else ""}
                            )
                            """
                        ),
                        {**dict(row), "node_id": default_node_id},
                    )
                conn.execute(text(f"DROP TABLE {table}"))
                conn.execute(text(f"ALTER TABLE {table}_new RENAME TO {table}"))
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_node_id ON {table} (node_id)"))
                conn.execute(
                    text(f"CREATE INDEX IF NOT EXISTS ix_{table}_client_name ON {table} (client_name)")
                )
            logger.info("DB migration: %s scoped by node_id (%d rows)", table, len(old_rows))

        _recreate_policy_table(
            "openvpn_access_policy",
            "id, client_name, is_temp_blocked, is_permanent_blocked, block_reason, "
            "block_started_at, block_days, block_until, traffic_limit_bytes, "
            "traffic_limit_period_days, updated_by, updated_at",
        )
        _recreate_policy_table(
            "wg_access_policy",
            "id, client_name, expires_at, is_temp_blocked, is_permanent_blocked, block_reason, "
            "block_started_at, block_days, block_until, traffic_limit_bytes, "
            "traffic_limit_period_days, updated_by, updated_at",
        )
    finally:
        db.close()


def _migrate_node_resource_sample_table() -> None:
    inspector = inspect(engine)
    if "node_resource_sample" in inspector.get_table_names():
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE node_resource_sample (
                    id INTEGER NOT NULL PRIMARY KEY,
                    node_id INTEGER NOT NULL,
                    cpu_percent FLOAT DEFAULT 0,
                    memory_percent FLOAT DEFAULT 0,
                    memory_used_mb INTEGER DEFAULT 0,
                    memory_total_mb INTEGER DEFAULT 0,
                    disk_percent FLOAT DEFAULT 0,
                    load_1 FLOAT,
                    load_5 FLOAT,
                    load_15 FLOAT,
                    created_at DATETIME,
                    FOREIGN KEY(node_id) REFERENCES nodes (id)
                )
                """
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_node_resource_sample_node_id ON node_resource_sample (node_id)")
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_node_resource_sample_created_at ON node_resource_sample (created_at)")
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_node_resource_sample_node_created "
                "ON node_resource_sample (node_id, created_at)"
            )
        )
    logger.info("DB migration: created node_resource_sample table")


def _migrate_active_web_session_table() -> None:
    inspector = inspect(engine)
    if "active_web_session" in inspector.get_table_names():
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE active_web_session (
                    id INTEGER NOT NULL PRIMARY KEY,
                    session_id VARCHAR(64) NOT NULL,
                    username VARCHAR(80) NOT NULL,
                    remote_addr VARCHAR(64),
                    user_agent VARCHAR(255),
                    created_at DATETIME,
                    last_seen_at DATETIME,
                    UNIQUE (session_id)
                )
                """
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_active_web_session_session_id ON active_web_session (session_id)")
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_active_web_session_username ON active_web_session (username)")
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_active_web_session_last_seen_at ON active_web_session (last_seen_at)")
        )
    logger.info("DB migration: created active_web_session table")


def _migrate_panel_resource_sample_table() -> None:
    inspector = inspect(engine)
    if "panel_resource_sample" in inspector.get_table_names():
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE panel_resource_sample (
                    id INTEGER NOT NULL PRIMARY KEY,
                    backend_cpu_percent FLOAT DEFAULT 0,
                    backend_memory_mb INTEGER DEFAULT 0,
                    backend_workers INTEGER DEFAULT 0,
                    nginx_memory_mb INTEGER,
                    total_panel_memory_mb INTEGER DEFAULT 0,
                    created_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_panel_resource_sample_created_at "
                "ON panel_resource_sample (created_at)"
            )
        )
    logger.info("DB migration: created panel_resource_sample table")


def run_db_migrations() -> None:
    """Lightweight SQLite migrations for columns added after initial deploy."""
    _migrate_vpn_configs_node_scope()
    _migrate_access_policy_node_scope()
    _migrate_node_resource_sample_table()
    _migrate_panel_resource_sample_table()
    _migrate_active_web_session_table()
    inspector = inspect(engine)
    migrations = {
        "wg_access_policy": [
            ("traffic_limit_bytes", "BIGINT"),
            ("traffic_limit_period_days", "INTEGER"),
        ],
        "openvpn_access_policy": [
            ("traffic_limit_bytes", "BIGINT"),
            ("traffic_limit_period_days", "INTEGER"),
        ],
        "panel_resource_sample": [
            ("watchdog_memory_mb", "INTEGER"),
            ("frontend_dev_memory_mb", "INTEGER"),
            ("host_cpu_percent", "FLOAT DEFAULT 0"),
            ("host_memory_percent", "FLOAT DEFAULT 0"),
            ("host_memory_used_mb", "INTEGER DEFAULT 0"),
            ("host_memory_total_mb", "INTEGER DEFAULT 0"),
            ("host_disk_percent", "FLOAT DEFAULT 0"),
            ("host_load_1", "FLOAT"),
        ],
        "users": [
            ("totp_secret_encrypted", "VARCHAR(512)"),
            ("totp_enabled", "INTEGER DEFAULT 0"),
            ("totp_backup_codes_encrypted", "VARCHAR(1024)"),
            ("telegram_id", "VARCHAR(32)"),
            ("tg_notify_events", "TEXT"),
        ],
    }
    with engine.begin() as conn:
        for table, columns in migrations.items():
            if table not in inspector.get_table_names():
                continue
            existing = {col["name"] for col in inspector.get_columns(table)}
            for name, col_type in columns:
                if name in existing:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}"))
                logger.info("DB migration: added %s.%s", table, name)

    _migrate_user_telegram_backfill()
    _migrate_nodes_mtls_enabled()


def _migrate_nodes_mtls_enabled() -> None:
    """Add per-node mTLS flag and backfill from deprecated global NODE_AGENT_MTLS_ENABLED."""
    inspector = inspect(engine)
    if "nodes" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("nodes")}
    with engine.begin() as conn:
        if "mtls_enabled" not in cols:
            conn.execute(text("ALTER TABLE nodes ADD COLUMN mtls_enabled INTEGER DEFAULT 0"))
            logger.info("DB migration: added nodes.mtls_enabled")
        if get_settings().node_agent_mtls_enabled:
            conn.execute(
                text("UPDATE nodes SET mtls_enabled = 1 WHERE is_local = 0")
            )
            logger.info("DB migration: backfilled nodes.mtls_enabled for remote nodes")


def _migrate_user_telegram_backfill() -> None:
    """Backfill telegram_id from tg_* usernames for existing Telegram-login users."""
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("users")}
    if "telegram_id" not in cols:
        return
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id, username, telegram_id FROM users WHERE username LIKE 'tg_%'")
        ).mappings().all()
        for row in rows:
            if row["telegram_id"]:
                continue
            username = str(row["username"] or "")
            if not username.startswith("tg_"):
                continue
            tg_id = username[3:].strip()
            if not tg_id:
                continue
            conn.execute(
                text("UPDATE users SET telegram_id = :tg_id WHERE id = :id"),
                {"tg_id": tg_id, "id": row["id"]},
            )
            logger.info("DB migration: backfilled telegram_id for user id=%s", row["id"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
