import fcntl
import json
import logging
import os
import threading

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Connection, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import SingletonThreadPool, StaticPool

from app.config import get_settings
from app.paths import BACKEND_ROOT

logger = logging.getLogger(__name__)
settings = get_settings()
_is_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False, "timeout": 30} if _is_sqlite else {}
engine = create_engine(settings.database_url, connect_args=connect_args)


def apply_sqlite_connection_pragmas(cursor) -> None:
    """Apply standard SQLite pragmas for panel databases (WAL, busy timeout, FK enforcement)."""
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA foreign_keys=ON")


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    if not _is_sqlite:
        return
    cursor = dbapi_connection.cursor()
    apply_sqlite_connection_pragmas(cursor)
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


@contextmanager
def _migration_transaction() -> Iterator[Connection]:
    """One real transaction per migration step, DDL included.

    pysqlite never emits BEGIN before DDL, so under ``engine.begin()`` a CREATE TABLE commits
    on its own and a crash mid table-rebuild leaves ``<table>_new`` behind for the next start.
    """
    # Shared-connection pools (in-memory SQLite) would roll the transaction back as soon as
    # a nested inspect(engine) returns that same connection.
    if engine.dialect.name != "sqlite" or isinstance(engine.pool, (SingletonThreadPool, StaticPool)):
        with engine.begin() as conn:
            yield conn
        return
    with engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            if conn.connection.dbapi_connection.in_transaction:
                conn.exec_driver_sql("ROLLBACK")
            raise
        conn.exec_driver_sql("COMMIT")


def _table_columns(conn: Connection, table: str) -> set[str]:
    return {row[1] for row in conn.exec_driver_sql(f'PRAGMA table_info("{table}")')}


_migrations_lock_guard = threading.RLock()
_migrations_lock_depth = 0


@contextmanager
def migrations_lock() -> Iterator[None]:
    """Serialize startup schema work across uvicorn workers sharing one SQLite file.

    Re-entrant within a process: flock on a second descriptor of the same file would block on itself.
    """
    global _migrations_lock_depth
    with _migrations_lock_guard:
        if _migrations_lock_depth:
            _migrations_lock_depth += 1
            try:
                yield
            finally:
                _migrations_lock_depth -= 1
            return
        db_file = engine.url.database if engine.dialect.name == "sqlite" else None
        if not db_file or db_file == ":memory:" or db_file.startswith("file:"):
            yield
            return
        lock_path = Path(f"{db_file}.migrate.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            os.fchmod(fd, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                logger.info("DB migration: waiting for another worker to finish migrations (%s)", lock_path)
                fcntl.flock(fd, fcntl.LOCK_EX)
            _migrations_lock_depth = 1
            try:
                yield
            finally:
                _migrations_lock_depth = 0
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


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
    from app.services.node_transport import node_uses_tls

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
                    mtls_enabled=node_uses_tls(node),
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

        with _migration_transaction() as conn:
            if "node_id" in _table_columns(conn, "vpn_configs"):
                return
            old_rows = conn.execute(
                text(
                    "SELECT id, client_name, vpn_type, owner_id, cert_expire_days, description, "
                    "created_at, updated_at FROM vpn_configs"
                )
            ).mappings().all()
            conn.execute(text("DROP TABLE IF EXISTS vpn_configs_new"))
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
    if all("node_id" in {col["name"] for col in inspector.get_columns(t)} for t in tables):
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
            with _migration_transaction() as conn:
                if "node_id" in _table_columns(conn, table):
                    return
                old_rows = conn.execute(text(f"SELECT {columns} FROM {table}")).mappings().all()
                conn.execute(text(f"DROP TABLE IF EXISTS {table}_new"))
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


def _migrate_awg2_access_policy_table() -> None:
    inspector = inspect(engine)
    if "amneziawg2_access_policies" in inspector.get_table_names():
        cols = {col["name"] for col in inspector.get_columns("amneziawg2_access_policies")}
        if "access_until" not in cols:
            with _migration_transaction() as conn:
                conn.execute(text("ALTER TABLE amneziawg2_access_policies ADD COLUMN access_until DATETIME"))
            logger.info("DB migration: added amneziawg2_access_policies.access_until")
        return
    with _migration_transaction() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE amneziawg2_access_policies (
                    id INTEGER NOT NULL PRIMARY KEY,
                    node_id INTEGER NOT NULL,
                    client_name VARCHAR(64) NOT NULL,
                    access_until DATETIME,
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
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_amneziawg2_access_policies_node_id "
                "ON amneziawg2_access_policies (node_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_amneziawg2_access_policies_client_name "
                "ON amneziawg2_access_policies (client_name)"
            )
        )
    logger.info("DB migration: created amneziawg2_access_policies table")


def _migrate_unlock_codes_tables() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if "unlock_codes" not in tables:
        with _migration_transaction() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE unlock_codes (
                        id INTEGER NOT NULL PRIMARY KEY,
                        code VARCHAR(32) NOT NULL,
                        grant_days INTEGER NOT NULL,
                        protocols TEXT NOT NULL DEFAULT '[]',
                        mode VARCHAR(8) NOT NULL,
                        max_redemptions INTEGER NOT NULL,
                        redemption_count INTEGER NOT NULL DEFAULT 0,
                        allowed_client_names TEXT NOT NULL DEFAULT '[]',
                        code_expires_at DATETIME,
                        created_by_user_id INTEGER,
                        created_at DATETIME,
                        revoked_at DATETIME,
                        CONSTRAINT uq_unlock_codes_code UNIQUE (code),
                        CONSTRAINT ck_unlock_codes_code_len CHECK (length(code) BETWEEN 8 AND 32),
                        CONSTRAINT ck_unlock_codes_mode CHECK (mode IN ('single', 'multi')),
                        FOREIGN KEY(created_by_user_id) REFERENCES users (id)
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_unlock_codes_code ON unlock_codes (code)"))
        logger.info("DB migration: created unlock_codes table")
    else:
        unlock_cols = {col["name"] for col in inspector.get_columns("unlock_codes")}
        if "redemption_count" not in unlock_cols:
            with _migration_transaction() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE unlock_codes "
                        "ADD COLUMN redemption_count INTEGER NOT NULL DEFAULT 0"
                    )
                )
                if "unlock_code_redemptions" in tables:
                    conn.execute(
                        text(
                            """
                            UPDATE unlock_codes
                            SET redemption_count = (
                                SELECT COUNT(*)
                                FROM unlock_code_redemptions
                                WHERE unlock_code_redemptions.code_id = unlock_codes.id
                            )
                            """
                        )
                    )
            logger.info("DB migration: added unlock_codes.redemption_count")

        inspector = inspect(engine)
        unlock_cols = {col["name"] for col in inspector.get_columns("unlock_codes")}
        if "allowed_client_names" not in unlock_cols:
            with _migration_transaction() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE unlock_codes "
                        "ADD COLUMN allowed_client_names TEXT NOT NULL DEFAULT '[]'"
                    )
                )
            logger.info("DB migration: added unlock_codes.allowed_client_names")

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if "unlock_code_redemptions" not in tables:
        with _migration_transaction() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE unlock_code_redemptions (
                        id INTEGER NOT NULL PRIMARY KEY,
                        code_id INTEGER NOT NULL,
                        user_id INTEGER,
                        client_name VARCHAR(64) NOT NULL,
                        node_id INTEGER NOT NULL,
                        redeemed_at DATETIME,
                        FOREIGN KEY(code_id) REFERENCES unlock_codes (id) ON DELETE CASCADE,
                        FOREIGN KEY(user_id) REFERENCES users (id),
                        FOREIGN KEY(node_id) REFERENCES nodes (id)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_unlock_code_redemptions_code_id "
                    "ON unlock_code_redemptions (code_id)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_unlock_code_redemptions_user_id "
                    "ON unlock_code_redemptions (user_id)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_unlock_code_redemptions_client_name "
                    "ON unlock_code_redemptions (client_name)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_unlock_code_redemptions_node_id "
                    "ON unlock_code_redemptions (node_id)"
                )
            )
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_unlock_code_redemptions_code_user "
                    "ON unlock_code_redemptions (code_id, user_id) "
                    "WHERE user_id IS NOT NULL"
                )
            )
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "uq_unlock_code_redemptions_code_client_node_orphan "
                    "ON unlock_code_redemptions (code_id, client_name, node_id) "
                    "WHERE user_id IS NULL"
                )
            )
        logger.info("DB migration: created unlock_code_redemptions table")
    else:
        _migrate_unlock_redemptions_user_scope()


def _unlock_redemptions_user_scope_ready(inspector) -> bool:
    cols = {col["name"] for col in inspector.get_columns("unlock_code_redemptions")}
    if "user_id" not in cols:
        return False
    index_names = {index.get("name") for index in inspector.get_indexes("unlock_code_redemptions")}
    if not {
        "uq_unlock_code_redemptions_code_user",
        "uq_unlock_code_redemptions_code_client_node_orphan",
    }.issubset(index_names):
        return False
    for constraint in inspector.get_unique_constraints("unlock_code_redemptions"):
        cols = set(constraint.get("column_names") or [])
        if cols == {"code_id", "client_name", "node_id"}:
            return False
        if constraint.get("name") == "uq_unlock_code_redemptions_code_client_node":
            return False
    return True


def _migrate_unlock_redemptions_user_scope() -> None:
    """Add user-scoped redemption audit and mixed uniqueness rules."""
    inspector = inspect(engine)
    if "unlock_code_redemptions" not in inspector.get_table_names():
        return
    if _unlock_redemptions_user_scope_ready(inspector):
        return

    from app.models import Node

    db = SessionLocal()
    try:
        fallback_node = db.query(Node).filter(Node.is_local.is_(True)).first()
        if fallback_node is None:
            fallback_node = db.query(Node).order_by(Node.id).first()
        fallback_node_id = fallback_node.id if fallback_node is not None else None
    finally:
        db.close()

    with _migration_transaction() as conn:
        if _unlock_redemptions_user_scope_ready(inspect(conn)):
            return
        cols = _table_columns(conn, "unlock_code_redemptions")
        conn.execute(text("DROP TABLE IF EXISTS unlock_code_redemptions_new"))
        if fallback_node_id is not None:
            conn.execute(
                text(
                    """
                    UPDATE unlock_code_redemptions
                    SET node_id = :node_id
                    WHERE node_id IS NULL
                    """
                ),
                {"node_id": fallback_node_id},
            )
        # Drop rows that still cannot satisfy NOT NULL node_id.
        conn.execute(text("DELETE FROM unlock_code_redemptions WHERE node_id IS NULL"))
        if "user_id" in cols:
            # Keep one row per (code_id, user_id) for user-scoped redeems and one per
            # (code_id, client_name, node_id) for orphan client redeems.
            conn.execute(
                text(
                    """
                    DELETE FROM unlock_code_redemptions
                    WHERE id NOT IN (
                        SELECT MIN(id)
                        FROM unlock_code_redemptions
                        WHERE user_id IS NOT NULL
                        GROUP BY code_id, user_id
                        UNION
                        SELECT MIN(id)
                        FROM unlock_code_redemptions
                        WHERE user_id IS NULL
                        GROUP BY code_id, client_name, node_id
                    )
                    """
                )
            )
        else:
            conn.execute(
                text(
                    """
                    DELETE FROM unlock_code_redemptions
                    WHERE id NOT IN (
                        SELECT MIN(id)
                        FROM unlock_code_redemptions
                        GROUP BY code_id, client_name, node_id
                    )
                    """
                )
            )
        conn.execute(
            text(
                """
                CREATE TABLE unlock_code_redemptions_new (
                    id INTEGER NOT NULL PRIMARY KEY,
                    code_id INTEGER NOT NULL,
                    user_id INTEGER,
                    client_name VARCHAR(64) NOT NULL,
                    node_id INTEGER NOT NULL,
                    redeemed_at DATETIME,
                    FOREIGN KEY(code_id) REFERENCES unlock_codes (id) ON DELETE CASCADE,
                    FOREIGN KEY(user_id) REFERENCES users (id),
                    FOREIGN KEY(node_id) REFERENCES nodes (id)
                )
                """
            )
        )
        if "user_id" in cols:
            conn.execute(
                text(
                    """
                    INSERT INTO unlock_code_redemptions_new (
                        id, code_id, user_id, client_name, node_id, redeemed_at
                    )
                    SELECT id, code_id, user_id, client_name, node_id, redeemed_at
                    FROM unlock_code_redemptions
                    """
                )
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO unlock_code_redemptions_new (
                        id, code_id, user_id, client_name, node_id, redeemed_at
                    )
                    SELECT id, code_id, NULL, client_name, node_id, redeemed_at
                    FROM unlock_code_redemptions
                    """
                )
            )
        conn.execute(text("DROP TABLE unlock_code_redemptions"))
        conn.execute(text("ALTER TABLE unlock_code_redemptions_new RENAME TO unlock_code_redemptions"))
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_unlock_code_redemptions_code_id "
                "ON unlock_code_redemptions (code_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_unlock_code_redemptions_user_id "
                "ON unlock_code_redemptions (user_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_unlock_code_redemptions_client_name "
                "ON unlock_code_redemptions (client_name)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_unlock_code_redemptions_node_id "
                "ON unlock_code_redemptions (node_id)"
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_unlock_code_redemptions_code_user "
                "ON unlock_code_redemptions (code_id, user_id) "
                "WHERE user_id IS NOT NULL"
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_unlock_code_redemptions_code_client_node_orphan "
                "ON unlock_code_redemptions (code_id, client_name, node_id) "
                "WHERE user_id IS NULL"
            )
        )
    logger.info("DB migration: unlock_code_redemptions user-scoped uniqueness enabled")


def _migrate_node_resource_sample_table() -> None:
    inspector = inspect(engine)
    if "node_resource_sample" in inspector.get_table_names():
        return
    with _migration_transaction() as conn:
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


def _migrate_connection_count_samples_table() -> None:
    inspector = inspect(engine)
    if "connection_count_samples" in inspector.get_table_names():
        return
    with _migration_transaction() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE connection_count_samples (
                    id INTEGER NOT NULL PRIMARY KEY,
                    node_id INTEGER NOT NULL,
                    openvpn_count INTEGER DEFAULT 0,
                    wireguard_count INTEGER DEFAULT 0,
                    amneziawg2_count INTEGER DEFAULT 0,
                    created_at DATETIME,
                    FOREIGN KEY(node_id) REFERENCES nodes (id)
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_connection_count_samples_node_id "
                "ON connection_count_samples (node_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_connection_count_samples_created_at "
                "ON connection_count_samples (created_at)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_connection_count_samples_node_created "
                "ON connection_count_samples (node_id, created_at)"
            )
        )
    logger.info("DB migration: created connection_count_samples table")


def _migrate_connection_count_samples_awg2_column() -> None:
    inspector = inspect(engine)
    if "connection_count_samples" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("connection_count_samples")}
    if "amneziawg2_count" in existing:
        return
    with _migration_transaction() as conn:
        conn.execute(text(
            "ALTER TABLE connection_count_samples ADD COLUMN amneziawg2_count INTEGER DEFAULT 0"
        ))
    logger.info("DB migration: added connection_count_samples.amneziawg2_count")


def _migrate_active_web_session_table() -> None:
    inspector = inspect(engine)
    if "active_web_session" in inspector.get_table_names():
        return
    with _migration_transaction() as conn:
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
    with _migration_transaction() as conn:
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


def _migrate_stage2_admin_productivity() -> None:
    """Stage 2: config tags, client templates, active_web_session.revoked_at."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if "config_tags" not in tables:
        with _migration_transaction() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE config_tags (
                        id INTEGER NOT NULL PRIMARY KEY,
                        node_id INTEGER NOT NULL,
                        name VARCHAR(64) NOT NULL,
                        color VARCHAR(16),
                        created_at DATETIME,
                        UNIQUE (node_id, name),
                        FOREIGN KEY(node_id) REFERENCES nodes (id)
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_config_tags_node_id ON config_tags (node_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_config_tags_name ON config_tags (name)"))
        logger.info("DB migration: created config_tags table")

    if "vpn_config_tag_links" not in tables:
        with _migration_transaction() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE vpn_config_tag_links (
                        id INTEGER NOT NULL PRIMARY KEY,
                        vpn_config_id INTEGER NOT NULL,
                        tag_id INTEGER NOT NULL,
                        UNIQUE (vpn_config_id, tag_id),
                        FOREIGN KEY(vpn_config_id) REFERENCES vpn_configs (id) ON DELETE CASCADE,
                        FOREIGN KEY(tag_id) REFERENCES config_tags (id) ON DELETE CASCADE
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_vpn_config_tag_links_vpn_config_id "
                    "ON vpn_config_tag_links (vpn_config_id)"
                )
            )
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_vpn_config_tag_links_tag_id ON vpn_config_tag_links (tag_id)")
            )
        logger.info("DB migration: created vpn_config_tag_links table")

    if "client_templates" not in tables:
        with _migration_transaction() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE client_templates (
                        id INTEGER NOT NULL PRIMARY KEY,
                        node_id INTEGER NOT NULL,
                        name VARCHAR(64) NOT NULL,
                        vpn_type VARCHAR(16) NOT NULL,
                        cert_expire_days INTEGER,
                        traffic_limit_value FLOAT,
                        traffic_limit_unit VARCHAR(8),
                        traffic_limit_period_days INTEGER,
                        description_template VARCHAR(255),
                        sort_order INTEGER DEFAULT 0,
                        is_builtin INTEGER DEFAULT 0,
                        created_at DATETIME,
                        UNIQUE (node_id, name),
                        FOREIGN KEY(node_id) REFERENCES nodes (id)
                    )
                    """
                )
            )
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_client_templates_node_id ON client_templates (node_id)")
            )
        logger.info("DB migration: created client_templates table")

    inspector = inspect(engine)
    if "active_web_session" in inspector.get_table_names():
        cols = {col["name"] for col in inspector.get_columns("active_web_session")}
        if "revoked_at" not in cols:
            with _migration_transaction() as conn:
                conn.execute(text("ALTER TABLE active_web_session ADD COLUMN revoked_at DATETIME"))
            logger.info("DB migration: added active_web_session.revoked_at")


def _migrate_user_reminder_logs_table() -> None:
    inspector = inspect(engine)
    if "user_reminder_logs" in inspector.get_table_names():
        return
    with _migration_transaction() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE user_reminder_logs (
                    id INTEGER NOT NULL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    reminder_type VARCHAR(32) NOT NULL,
                    dedup_key VARCHAR(128) NOT NULL,
                    sent_at DATETIME,
                    UNIQUE (user_id, reminder_type, dedup_key),
                    FOREIGN KEY(user_id) REFERENCES users (id)
                )
                """
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_user_reminder_logs_user_id ON user_reminder_logs (user_id)")
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_user_reminder_logs_sent_at ON user_reminder_logs (sent_at)")
        )
    logger.info("DB migration: created user_reminder_logs table")


def _seed_client_templates_for_nodes() -> None:
    from app.models import ClientTemplate, Node, VpnType

    inspector = inspect(engine)
    if "client_templates" not in inspector.get_table_names() or "nodes" not in inspector.get_table_names():
        return

    builtins = [
        {
            "name": "OVPN 3650d",
            "vpn_type": VpnType.openvpn,
            "cert_expire_days": 3650,
            "sort_order": 10,
        },
        {
            "name": "OVPN 3650d + 100 GB",
            "vpn_type": VpnType.openvpn,
            "cert_expire_days": 3650,
            "traffic_limit_value": 100.0,
            "traffic_limit_unit": "GB",
            "sort_order": 20,
        },
        {
            "name": "WireGuard базовый",
            "vpn_type": VpnType.wireguard,
            "sort_order": 30,
        },
        {
            "name": "WG + 50 GB / мес",
            "vpn_type": VpnType.wireguard,
            "traffic_limit_value": 50.0,
            "traffic_limit_unit": "GB",
            "traffic_limit_period_days": 30,
            "sort_order": 40,
        },
    ]

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        nodes = db.query(Node).all()
        for node in nodes:
            existing = db.query(ClientTemplate).filter(ClientTemplate.node_id == node.id).count()
            if existing:
                continue
            for item in builtins:
                db.add(
                    ClientTemplate(
                        node_id=node.id,
                        is_builtin=True,
                        description_template=None,
                        **item,
                    )
                )
        db.commit()
    finally:
        db.close()


def _migrate_node_sync_groups_table() -> None:
    inspector = inspect(engine)
    if "node_sync_groups" in inspector.get_table_names():
        return
    with _migration_transaction() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE node_sync_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(128) NOT NULL,
                    shared_domain VARCHAR(255) NOT NULL,
                    shared_domain_wireguard VARCHAR(255),
                    primary_node_id INTEGER NOT NULL REFERENCES nodes(id),
                    replica_node_ids TEXT NOT NULL DEFAULT '[]',
                    sync_mode VARCHAR(32) NOT NULL DEFAULT 'manual_full',
                    sync_status VARCHAR(20) NOT NULL DEFAULT 'unknown',
                    last_sync_at DATETIME,
                    last_verify_at DATETIME,
                    last_sync_task_id VARCHAR(32),
                    last_sync_error TEXT,
                    last_verify_result TEXT,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX ix_node_sync_groups_primary ON node_sync_groups(primary_node_id)"))
        logger.info("DB migration: created node_sync_groups table")


def _migrate_node_sync_groups_wireguard_domain() -> None:
    """Separate WireGuard/AmneziaWG shared domain (like AntiZapret OPENVPN_HOST / WIREGUARD_HOST)."""
    inspector = inspect(engine)
    if "node_sync_groups" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("node_sync_groups")}
    if "shared_domain_wireguard" in cols:
        return
    with _migration_transaction() as conn:
        conn.execute(text("ALTER TABLE node_sync_groups ADD COLUMN shared_domain_wireguard VARCHAR(255)"))
        # Existing groups used one domain for both protocols — keep that behaviour.
        conn.execute(
            text(
                "UPDATE node_sync_groups SET shared_domain_wireguard = shared_domain "
                "WHERE shared_domain_wireguard IS NULL OR shared_domain_wireguard = ''"
            )
        )
        logger.info("DB migration: added node_sync_groups.shared_domain_wireguard")


def _migrate_vpn_configs_ha_links() -> None:
    inspector = inspect(engine)
    if "vpn_configs" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("vpn_configs")}
    with _migration_transaction() as conn:
        if "sync_group_id" not in cols:
            conn.execute(
                text("ALTER TABLE vpn_configs ADD COLUMN sync_group_id INTEGER REFERENCES node_sync_groups(id)")
            )
            logger.info("DB migration: added vpn_configs.sync_group_id")
        if "ha_primary_config_id" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE vpn_configs ADD COLUMN ha_primary_config_id INTEGER REFERENCES vpn_configs(id)"
                )
            )
            logger.info("DB migration: added vpn_configs.ha_primary_config_id")


def _migrate_webhook_delivery_table() -> None:
    inspector = inspect(engine)
    if "webhook_delivery" in inspector.get_table_names():
        return
    with _migration_transaction() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE webhook_delivery (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_action VARCHAR(64) NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    url VARCHAR(512) NOT NULL,
                    destination_type VARCHAR(16) NOT NULL DEFAULT 'http',
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_status_code INTEGER,
                    last_error TEXT,
                    next_retry_at DATETIME,
                    created_at DATETIME NOT NULL,
                    delivered_at DATETIME
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX ix_webhook_delivery_event_action ON webhook_delivery (event_action)"))
        conn.execute(text("CREATE INDEX ix_webhook_delivery_status ON webhook_delivery (status)"))
        conn.execute(text("CREATE INDEX ix_webhook_delivery_next_retry_at ON webhook_delivery (next_retry_at)"))
        conn.execute(text("CREATE INDEX ix_webhook_delivery_created_at ON webhook_delivery (created_at)"))
        logger.info("DB migration: created webhook_delivery table")


def _migrate_webauthn_credentials_table() -> None:
    inspector = inspect(engine)
    if "webauthn_credentials" in inspector.get_table_names():
        return
    with _migration_transaction() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE webauthn_credentials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    credential_id VARCHAR(512) NOT NULL,
                    public_key TEXT NOT NULL,
                    sign_count INTEGER NOT NULL DEFAULT 0,
                    transports TEXT,
                    aaguid VARCHAR(64),
                    nickname VARCHAR(128) NOT NULL DEFAULT 'Passkey',
                    created_at DATETIME NOT NULL,
                    last_used_at DATETIME,
                    CONSTRAINT uq_webauthn_credential_id UNIQUE (credential_id)
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX ix_webauthn_credentials_user_id ON webauthn_credentials (user_id)"))
        conn.execute(
            text("CREATE INDEX ix_webauthn_credentials_credential_id ON webauthn_credentials (credential_id)")
        )
        logger.info("DB migration: created webauthn_credentials table")


def _migrate_webhook_delivery_destination_type() -> None:
    inspector = inspect(engine)
    if "webhook_delivery" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("webhook_delivery")}
    if "destination_type" in existing:
        return
    with _migration_transaction() as conn:
        conn.execute(
            text(
                "ALTER TABLE webhook_delivery ADD COLUMN destination_type VARCHAR(16) NOT NULL DEFAULT 'http'"
            )
        )
        conn.execute(text("CREATE INDEX ix_webhook_delivery_destination_type ON webhook_delivery (destination_type)"))
        logger.info("DB migration: added webhook_delivery.destination_type")


def _migrate_alert_rules_table() -> None:
    inspector = inspect(engine)
    if "alert_rules" in inspector.get_table_names():
        return
    with _migration_transaction() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE alert_rules (
                    id INTEGER NOT NULL PRIMARY KEY,
                    name VARCHAR(128) NOT NULL,
                    metric VARCHAR(64) NOT NULL,
                    operator VARCHAR(8) NOT NULL DEFAULT 'gt',
                    threshold FLOAT NOT NULL,
                    node_id INTEGER,
                    cooldown_minutes INTEGER NOT NULL DEFAULT 30,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_triggered_at DATETIME,
                    created_at DATETIME,
                    updated_at DATETIME,
                    FOREIGN KEY(node_id) REFERENCES nodes (id)
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_alert_rules_node_id ON alert_rules (node_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_alert_rules_enabled ON alert_rules (enabled)"))
    logger.info("DB migration: created alert_rules table")


def _migrate_openvpn_buffer_guard_tables() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    created: list[str] = []
    with _migration_transaction() as conn:
        if "openvpn_buffer_guard_settings" not in table_names:
            conn.execute(
                text(
                    """
                    CREATE TABLE openvpn_buffer_guard_settings (
                        id INTEGER NOT NULL PRIMARY KEY,
                        node_id INTEGER NOT NULL,
                        enabled INTEGER NOT NULL DEFAULT 0,
                        mode VARCHAR(32) NOT NULL DEFAULT 'notify',
                        threshold_count INTEGER NOT NULL DEFAULT 40,
                        window_seconds INTEGER NOT NULL DEFAULT 60,
                        escalate_after_seconds INTEGER NOT NULL DEFAULT 30,
                        cooldown_minutes INTEGER NOT NULL DEFAULT 15,
                        temp_ban_minutes INTEGER NOT NULL DEFAULT 60,
                        watch_units_json TEXT NOT NULL DEFAULT '["antizapret-udp","vpn-udp"]',
                        updated_at DATETIME,
                        UNIQUE (node_id),
                        FOREIGN KEY(node_id) REFERENCES nodes (id)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_openvpn_buffer_guard_settings_node_id "
                    "ON openvpn_buffer_guard_settings (node_id)"
                )
            )
            created.append("openvpn_buffer_guard_settings")
        if "openvpn_buffer_guard_events" not in table_names:
            conn.execute(
                text(
                    """
                    CREATE TABLE openvpn_buffer_guard_events (
                        id INTEGER NOT NULL PRIMARY KEY,
                        node_id INTEGER NOT NULL,
                        created_at DATETIME,
                        unit VARCHAR(64) NOT NULL,
                        common_name VARCHAR(128),
                        real_address VARCHAR(128),
                        error_count INTEGER NOT NULL DEFAULT 0,
                        window_seconds INTEGER NOT NULL DEFAULT 60,
                        mode VARCHAR(32) NOT NULL,
                        actions_json TEXT NOT NULL DEFAULT '[]',
                        result VARCHAR(32) NOT NULL DEFAULT 'failed',
                        detail TEXT,
                        manual INTEGER NOT NULL DEFAULT 0,
                        ban_expires_at DATETIME,
                        FOREIGN KEY(node_id) REFERENCES nodes (id)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_openvpn_buffer_guard_events_node_id "
                    "ON openvpn_buffer_guard_events (node_id)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_openvpn_buffer_guard_events_created_at "
                    "ON openvpn_buffer_guard_events (created_at)"
                )
            )
            created.append("openvpn_buffer_guard_events")
    if created:
        logger.info("DB migration: created %s", ", ".join(created))


def migrate_factory_buffer_guard_thresholds(conn) -> int:
    from app.services.openvpn_buffer_guard import recommended_threshold

    rows = conn.execute(
        text(
            "SELECT id, mode FROM openvpn_buffer_guard_settings "
            "WHERE threshold_count = 500 AND window_seconds = 60"
        )
    ).fetchall()
    updated = 0
    for row_id, mode in rows:
        new_thr = int(recommended_threshold(mode))
        conn.execute(
            text(
                "UPDATE openvpn_buffer_guard_settings "
                "SET threshold_count = :thr WHERE id = :id"
            ),
            {"thr": new_thr, "id": row_id},
        )
        updated += 1
    return updated


def _migrate_openvpn_buffer_guard_factory_thresholds() -> None:
    inspector = inspect(engine)
    if "openvpn_buffer_guard_settings" not in set(inspector.get_table_names()):
        return
    with _migration_transaction() as conn:
        updated = migrate_factory_buffer_guard_thresholds(conn)
    if updated:
        logger.info(
            "DB migration: openvpn_buffer_guard factory thresholds updated rows=%s",
            updated,
        )


def _migrate_user_traffic_sample_node_created_index() -> None:
    inspector = inspect(engine)
    if "user_traffic_sample" not in inspector.get_table_names():
        return
    existing = {idx["name"] for idx in inspector.get_indexes("user_traffic_sample")}
    if "ix_user_traffic_sample_node_created" in existing:
        return
    with _migration_transaction() as conn:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_user_traffic_sample_node_created "
                "ON user_traffic_sample (node_id, created_at)"
            )
        )
    logger.info("DB migration: created ix_user_traffic_sample_node_created index")


def _migrate_refresh_tokens_family_index() -> None:
    with _migration_transaction() as conn:
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_refresh_tokens_family_id ON refresh_tokens (family_id)")
        )


def migrate_traffic_session_state_node_scoped_key(conn) -> bool:
    """HA replicas share WireGuard peers, so session_key is unique per node, not globally."""
    conn_inspector = inspect(conn)
    if "traffic_session_state" not in conn_inspector.get_table_names():
        return False
    indexes = {idx["name"]: idx for idx in conn_inspector.get_indexes("traffic_session_state")}
    if "uq_traffic_session_state_node_session" in indexes:
        return False
    legacy = indexes.get("ix_traffic_session_state_session_key")
    if legacy and legacy.get("unique"):
        conn.execute(text("DROP INDEX ix_traffic_session_state_session_key"))
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_traffic_session_state_session_key "
            "ON traffic_session_state (session_key)"
        )
    )
    conn.execute(
        text(
            "CREATE UNIQUE INDEX uq_traffic_session_state_node_session "
            "ON traffic_session_state (node_id, session_key)"
        )
    )
    return True


def _migrate_traffic_session_state_node_scoped_key() -> None:
    with _migration_transaction() as conn:
        migrated = migrate_traffic_session_state_node_scoped_key(conn)
    if migrated:
        logger.info("DB migration: traffic_session_state session_key is now unique per node")


def _migrate_traffic_session_state_active_index() -> None:
    """Collector reads active sessions every minute; finished history must not be scanned for that."""
    with _migration_transaction() as conn:
        if "traffic_session_state" not in inspect(conn).get_table_names():
            return
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_traffic_session_state_node_active "
                "ON traffic_session_state (node_id) WHERE is_active = 1"
            )
        )


def _migrate_user_traffic_sample_name_index() -> None:
    """Traffic limit checks sum one client's samples over a period."""
    with _migration_transaction() as conn:
        if "user_traffic_sample" not in inspect(conn).get_table_names():
            return
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_user_traffic_sample_name_created "
                "ON user_traffic_sample (common_name, created_at)"
            )
        )
        conn.execute(text("DROP INDEX IF EXISTS ix_user_traffic_sample_common_name"))


def _migrate_client_portal_tokens_active_unique() -> None:
    """One active (revoked_at IS NULL) portal token per (node_id, client_name)."""
    inspector = inspect(engine)
    if "client_portal_tokens" not in inspector.get_table_names():
        return
    index_names = {idx.get("name") for idx in inspector.get_indexes("client_portal_tokens")}
    if "uq_client_portal_tokens_active_node_client" in index_names:
        return

    with _migration_transaction() as conn:
        # Keep newest active row per client; revoke older duplicates.
        conn.execute(
            text(
                """
                UPDATE client_portal_tokens
                SET revoked_at = CURRENT_TIMESTAMP
                WHERE revoked_at IS NULL
                  AND id NOT IN (
                    SELECT MAX(id)
                    FROM client_portal_tokens
                    WHERE revoked_at IS NULL
                    GROUP BY node_id, client_name
                  )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX uq_client_portal_tokens_active_node_client
                ON client_portal_tokens (node_id, client_name)
                WHERE revoked_at IS NULL
                """
            )
        )
    logger.info("DB migration: unique active client_portal_tokens per node+client")


def _migrate_user_portal_tokens_table() -> None:
    """Create user_portal_tokens and enforce one active token per user."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "user_portal_tokens" not in tables:
        with _migration_transaction() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE user_portal_tokens (
                        id INTEGER NOT NULL PRIMARY KEY,
                        token VARCHAR(64) NOT NULL,
                        user_id INTEGER NOT NULL,
                        created_by_user_id INTEGER,
                        created_at DATETIME,
                        revoked_at DATETIME,
                        CONSTRAINT uq_user_portal_token UNIQUE (token),
                        FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
                        FOREIGN KEY(created_by_user_id) REFERENCES users (id)
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_portal_tokens_token ON user_portal_tokens (token)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_portal_tokens_user_id ON user_portal_tokens (user_id)"))
            conn.execute(
                text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_user_portal_tokens_active_user
                    ON user_portal_tokens (user_id)
                    WHERE revoked_at IS NULL
                    """
                )
            )
        logger.info("DB migration: created user_portal_tokens table")
        return

    index_names = {idx.get("name") for idx in inspector.get_indexes("user_portal_tokens")}
    if "uq_user_portal_tokens_active_user" in index_names:
        return

    with _migration_transaction() as conn:
        conn.execute(
            text(
                """
                UPDATE user_portal_tokens
                SET revoked_at = CURRENT_TIMESTAMP
                WHERE revoked_at IS NULL
                  AND id NOT IN (
                    SELECT MAX(id)
                    FROM user_portal_tokens
                    WHERE revoked_at IS NULL
                    GROUP BY user_id
                  )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX uq_user_portal_tokens_active_user
                ON user_portal_tokens (user_id)
                WHERE revoked_at IS NULL
                """
            )
        )
    logger.info("DB migration: unique active user_portal_tokens per user")


def run_db_migrations() -> None:
    """Lightweight SQLite migrations for columns added after initial deploy."""
    with migrations_lock():
        _run_db_migrations()


def _migrate_nodes_columns() -> None:
    """Bring nodes up to the model: later migrations load Node via the ORM, which selects every mapped column."""
    inspector = inspect(engine)
    if "nodes" in inspector.get_table_names():
        existing = {col["name"] for col in inspector.get_columns("nodes")}
        if "api_key_rotated_at" not in existing:
            with _migration_transaction() as conn:
                conn.execute(text("ALTER TABLE nodes ADD COLUMN api_key_rotated_at DATETIME"))
            logger.info("DB migration: added nodes.api_key_rotated_at")
    _migrate_nodes_mtls_enabled()
    _migrate_nodes_transport()
    _migrate_nodes_ssh_fields()
    _migrate_nodes_openvpn_remote_hosts()
    _migrate_nodes_wireguard_use_first_remote()
    _migrate_nodes_openvpn_multihome()
    _migrate_nodes_proxy_fields()


def _run_db_migrations() -> None:
    _migrate_nodes_columns()
    _migrate_alert_rules_table()
    _migrate_openvpn_buffer_guard_tables()
    _migrate_openvpn_buffer_guard_factory_thresholds()
    _migrate_node_sync_groups_table()
    _migrate_node_sync_groups_wireguard_domain()
    _migrate_vpn_configs_ha_links()
    _migrate_vpn_configs_node_scope()
    _migrate_access_policy_node_scope()
    _migrate_awg2_access_policy_table()
    _migrate_unlock_codes_tables()
    _migrate_client_portal_tokens_active_unique()
    _migrate_user_portal_tokens_table()
    _migrate_node_resource_sample_table()
    _migrate_connection_count_samples_table()
    _migrate_connection_count_samples_awg2_column()
    _migrate_panel_resource_sample_table()
    _migrate_active_web_session_table()
    _migrate_stage2_admin_productivity()
    _migrate_user_reminder_logs_table()
    _migrate_webhook_delivery_table()
    _migrate_webauthn_credentials_table()
    _migrate_webhook_delivery_destination_type()
    _migrate_user_traffic_sample_node_created_index()
    _migrate_traffic_session_state_node_scoped_key()
    _migrate_traffic_session_state_active_index()
    _migrate_user_traffic_sample_name_index()
    inspector = inspect(engine)
    migrations = {
        "wg_access_policy": [
            ("traffic_limit_bytes", "BIGINT"),
            ("traffic_limit_period_days", "INTEGER"),
        ],
        "amneziawg2_access_policies": [
            ("access_until", "DATETIME"),
            ("traffic_limit_bytes", "BIGINT"),
            ("traffic_limit_period_days", "INTEGER"),
        ],
        "openvpn_access_policy": [
            ("access_until", "DATETIME"),
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
            ("local_node_memory_mb", "INTEGER DEFAULT 0"),
            ("total_stack_memory_mb", "INTEGER DEFAULT 0"),
            ("local_vpn_core_memory_mb", "INTEGER DEFAULT 0"),
            ("legacy_antizapret_memory_mb", "INTEGER DEFAULT 0"),
            ("node_agent_memory_mb", "INTEGER DEFAULT 0"),
            ("managed_vpn_memory_mb", "INTEGER DEFAULT 0"),
        ],
        "vpn_configs": [
            ("cert_expires_at", "DATETIME"),
            ("expires_at", "DATETIME"),
        ],
        "background_task": [
            ("owner", "VARCHAR(64)"),
        ],
        "server_reboot_requests": [
            ("owner", "VARCHAR(64)"),
        ],
        "refresh_tokens": [
            ("family_id", "VARCHAR(32)"),
            ("revoked_at", "DATETIME"),
            ("revoke_reason", "VARCHAR(16)"),
        ],
        "users": [
            ("totp_secret_encrypted", "VARCHAR(512)"),
            ("totp_enabled", "INTEGER DEFAULT 0"),
            ("totp_backup_codes_encrypted", "VARCHAR(1024)"),
            ("telegram_id", "VARCHAR(32)"),
            ("tg_notify_events", "TEXT"),
            ("config_quota", "INTEGER"),
            ("can_create_configs", "INTEGER DEFAULT 1"),
            ("visible_vpn_profiles", "TEXT"),
            ("timezone", "VARCHAR(64) DEFAULT ''"),
            ("last_client_timezone", "VARCHAR(64) DEFAULT ''"),
            ("noc_daily_time", "VARCHAR(5) DEFAULT ''"),
            ("noc_weekly_dow", "VARCHAR(1) DEFAULT ''"),
            ("noc_weekly_time", "VARCHAR(5) DEFAULT ''"),
            ("access_until", "DATETIME"),
            ("token_version", "INTEGER DEFAULT 0"),
        ],
    }
    with _migration_transaction() as conn:
        for table, columns in migrations.items():
            if table not in inspector.get_table_names():
                continue
            existing = {col["name"] for col in inspector.get_columns(table)}
            for name, col_type in columns:
                if name in existing:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}"))
                logger.info("DB migration: added %s.%s", table, name)
    if "refresh_tokens" in inspector.get_table_names():
        _migrate_refresh_tokens_family_index()

    _migrate_user_config_access_table()
    _migrate_viewer_role_to_user()
    _migrate_user_telegram_backfill()
    _migrate_user_access_until_backfill()
    _seed_client_templates_for_nodes()


def _migrate_user_config_access_table() -> None:
    """Rename viewer_config_access → user_config_access (preserve grants)."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "user_config_access" in tables:
        return
    if "viewer_config_access" not in tables:
        return
    with _migration_transaction() as conn:
        conn.execute(text("ALTER TABLE viewer_config_access RENAME TO user_config_access"))
        logger.info("DB migration: renamed viewer_config_access → user_config_access")


def _migrate_viewer_role_to_user() -> None:
    """Convert legacy role=viewer rows to user with create disabled."""
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("users")}
    with _migration_transaction() as conn:
        if "can_create_configs" in cols:
            result = conn.execute(
                text(
                    "UPDATE users SET role = 'user', can_create_configs = 0 "
                    "WHERE role = 'viewer'"
                )
            )
        else:
            result = conn.execute(text("UPDATE users SET role = 'user' WHERE role = 'viewer'"))
        if result.rowcount:
            logger.info("DB migration: converted %s viewer user(s) to user", result.rowcount)


def _migrate_nodes_mtls_enabled() -> None:
    """Add per-node mTLS flag and one-shot backfill from deprecated global NODE_AGENT_MTLS_ENABLED."""
    inspector = inspect(engine)
    if "nodes" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("nodes")}
    with _migration_transaction() as conn:
        if "mtls_enabled" not in cols:
            conn.execute(text("ALTER TABLE nodes ADD COLUMN mtls_enabled INTEGER DEFAULT 0"))
            logger.info("DB migration: added nodes.mtls_enabled")
            cols.add("mtls_enabled")
            if get_settings().node_agent_mtls_enabled:
                conn.execute(
                    text("UPDATE nodes SET mtls_enabled = 1 WHERE is_local = 0")
                )
                logger.info("DB migration: backfilled nodes.mtls_enabled for remote nodes")
        # After transport column exists, never force mtls_enabled from the deprecated global flag —
        # transport is the source of truth (see _migrate_nodes_transport / _sync_nodes_transport_flags).


def _migrate_nodes_transport() -> None:
    """Add nodes.transport and one-shot backfill from mtls_enabled."""
    inspector = inspect(engine)
    if "nodes" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("nodes")}
    if "transport" not in cols:
        with _migration_transaction() as conn:
            conn.execute(text("ALTER TABLE nodes ADD COLUMN transport VARCHAR(16) DEFAULT 'http'"))
            conn.execute(
                text(
                    "UPDATE nodes SET transport = CASE WHEN mtls_enabled = 1 THEN 'mtls' ELSE 'http' END"
                )
            )
            logger.info("DB migration: added nodes.transport and backfilled from mtls_enabled")
    _sync_nodes_transport_flags()


def _migrate_nodes_ssh_fields() -> None:
    """Add SSH transport columns for node connection settings."""
    inspector = inspect(engine)
    if "nodes" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("nodes")}
    with _migration_transaction() as conn:
        if "ssh_host" not in cols:
            conn.execute(text("ALTER TABLE nodes ADD COLUMN ssh_host VARCHAR(255)"))
            logger.info("DB migration: added nodes.ssh_host")
        if "ssh_port" not in cols:
            conn.execute(text("ALTER TABLE nodes ADD COLUMN ssh_port INTEGER NOT NULL DEFAULT 22"))
            logger.info("DB migration: added nodes.ssh_port")
        if "ssh_username" not in cols:
            conn.execute(text("ALTER TABLE nodes ADD COLUMN ssh_username VARCHAR(128)"))
            logger.info("DB migration: added nodes.ssh_username")
        if "ssh_private_key_encrypted" not in cols:
            conn.execute(
                text("ALTER TABLE nodes ADD COLUMN ssh_private_key_encrypted TEXT NOT NULL DEFAULT ''")
            )
            logger.info("DB migration: added nodes.ssh_private_key_encrypted")
        if "ssh_passphrase_encrypted" not in cols:
            conn.execute(text("ALTER TABLE nodes ADD COLUMN ssh_passphrase_encrypted TEXT NOT NULL DEFAULT ''"))
            logger.info("DB migration: added nodes.ssh_passphrase_encrypted")
        if "ssh_remote_agent_host" not in cols:
            conn.execute(
                text("ALTER TABLE nodes ADD COLUMN ssh_remote_agent_host VARCHAR(255) NOT NULL DEFAULT '127.0.0.1'")
            )
            logger.info("DB migration: added nodes.ssh_remote_agent_host")
        if "ssh_remote_agent_port" not in cols:
            conn.execute(text("ALTER TABLE nodes ADD COLUMN ssh_remote_agent_port INTEGER"))
            logger.info("DB migration: added nodes.ssh_remote_agent_port")
        if "ssh_host_key" not in cols:
            conn.execute(text("ALTER TABLE nodes ADD COLUMN ssh_host_key TEXT NOT NULL DEFAULT ''"))
            logger.info("DB migration: added nodes.ssh_host_key")
            # One-shot: lift pins previously stored in node_metadata.ssh_host_key
            try:
                rows = conn.execute(text("SELECT id, node_metadata FROM nodes")).mappings().all()
                for row in rows:
                    raw = row.get("node_metadata") or "{}"
                    try:
                        meta = json.loads(raw) if isinstance(raw, str) else {}
                    except Exception:
                        continue
                    if not isinstance(meta, dict):
                        continue
                    pinned = str(meta.get("ssh_host_key") or "").strip()
                    if not pinned:
                        continue
                    conn.execute(
                        text("UPDATE nodes SET ssh_host_key = :key WHERE id = :id"),
                        {"key": pinned, "id": row["id"]},
                    )
            except Exception:
                logger.debug("DB migration: skip ssh_host_key metadata backfill", exc_info=True)


def _sync_nodes_transport_flags() -> None:
    """Keep transport and mtls_enabled aligned; heal empty transport from legacy flag."""
    inspector = inspect(engine)
    if "nodes" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("nodes")}
    if "transport" not in cols or "mtls_enabled" not in cols:
        return
    with _migration_transaction() as conn:
        conn.execute(
            text(
                "UPDATE nodes SET transport = CASE WHEN mtls_enabled = 1 THEN 'mtls' ELSE 'http' END "
                "WHERE transport IS NULL OR TRIM(transport) = ''"
            )
        )
        conn.execute(
            text(
                "UPDATE nodes SET mtls_enabled = CASE WHEN LOWER(TRIM(transport)) = 'mtls' THEN 1 ELSE 0 END "
                "WHERE LOWER(TRIM(transport)) IN ('http', 'mtls')"
            )
        )


def _migrate_nodes_openvpn_remote_hosts() -> None:
    """Add per-node OpenVPN multi-remote hosts JSON column."""
    inspector = inspect(engine)
    if "nodes" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("nodes")}
    if "openvpn_remote_hosts" in cols:
        return
    with _migration_transaction() as conn:
        conn.execute(text("ALTER TABLE nodes ADD COLUMN openvpn_remote_hosts TEXT"))
        logger.info("DB migration: added nodes.openvpn_remote_hosts")


def _migrate_nodes_wireguard_use_first_remote() -> None:
    """Opt-in: first OpenVPN remote also becomes WIREGUARD_HOST (proxy.sh)."""
    inspector = inspect(engine)
    if "nodes" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("nodes")}
    if "wireguard_use_first_remote" in cols:
        return
    with _migration_transaction() as conn:
        conn.execute(text("ALTER TABLE nodes ADD COLUMN wireguard_use_first_remote INTEGER DEFAULT 0"))
        logger.info("DB migration: added nodes.wireguard_use_first_remote")


def _migrate_nodes_openvpn_multihome() -> None:
    """Add per-node OpenVPN multihome flag (multi-IP reply source)."""
    inspector = inspect(engine)
    if "nodes" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("nodes")}
    if "openvpn_multihome" in cols:
        return
    with _migration_transaction() as conn:
        conn.execute(text("ALTER TABLE nodes ADD COLUMN openvpn_multihome INTEGER DEFAULT 0"))
        logger.info("DB migration: added nodes.openvpn_multihome")


def _migrate_nodes_proxy_fields() -> None:
    """Add node_kind / destination_ip / linked_vpn_node_id for proxy nodes (wave 1)."""
    inspector = inspect(engine)
    if "nodes" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("nodes")}
    with _migration_transaction() as conn:
        if "node_kind" not in cols:
            conn.execute(text("ALTER TABLE nodes ADD COLUMN node_kind VARCHAR(16) DEFAULT 'vpn'"))
            conn.execute(text("UPDATE nodes SET node_kind = 'vpn' WHERE node_kind IS NULL OR node_kind = ''"))
            logger.info("DB migration: added nodes.node_kind")
        if "destination_ip" not in cols:
            conn.execute(text("ALTER TABLE nodes ADD COLUMN destination_ip VARCHAR(64)"))
            logger.info("DB migration: added nodes.destination_ip")
        if "linked_vpn_node_id" not in cols:
            conn.execute(text("ALTER TABLE nodes ADD COLUMN linked_vpn_node_id INTEGER REFERENCES nodes(id)"))
            logger.info("DB migration: added nodes.linked_vpn_node_id")


def _max_owned_client_access_until(conn, user_id: int) -> object | None:
    """Max non-null deadline across owned clients' openvpn/awg2/wg policies."""
    pairs = conn.execute(
        text(
            """
            SELECT DISTINCT node_id, client_name
            FROM vpn_configs
            WHERE owner_id = :uid AND ha_primary_config_id IS NULL
            """
        ),
        {"uid": user_id},
    ).mappings().all()
    max_deadline = None
    for pair in pairs:
        node_id = pair["node_id"]
        raw_name = (pair["client_name"] or "").strip()
        if not raw_name:
            continue
        lower_name = raw_name.lower()
        candidates = []
        ov = conn.execute(
            text(
                """
                SELECT access_until FROM openvpn_access_policy
                WHERE node_id = :nid AND client_name = :cn AND access_until IS NOT NULL
                """
            ),
            {"nid": node_id, "cn": raw_name},
        ).scalar()
        if ov is not None:
            candidates.append(ov)
        awg = conn.execute(
            text(
                """
                SELECT access_until FROM amneziawg2_access_policies
                WHERE node_id = :nid AND client_name = :cn AND access_until IS NOT NULL
                """
            ),
            {"nid": node_id, "cn": lower_name},
        ).scalar()
        if awg is not None:
            candidates.append(awg)
        wg = conn.execute(
            text(
                """
                SELECT expires_at FROM wg_access_policy
                WHERE node_id = :nid AND client_name = :cn AND expires_at IS NOT NULL
                """
            ),
            {"nid": node_id, "cn": lower_name},
        ).scalar()
        if wg is not None:
            candidates.append(wg)
        if candidates:
            pair_max = max(candidates)
            if max_deadline is None or pair_max > max_deadline:
                max_deadline = pair_max
    return max_deadline


_USER_ACCESS_UNTIL_BACKFILL_MARKER = "migration_user_access_until_backfill_done"


def _migrate_user_access_until_backfill() -> None:
    """One-shot: set users.access_until from max child policy deadline when still NULL.

    Guarded by an app_settings marker, not just `access_until IS NULL`: a client
    may legitimately hold a deadline while its owner is unlimited (confirmed
    override, ownership change), and re-running would adopt that client date as
    the owner's subscription — possibly already expired.
    """
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "users" not in tables:
        return
    user_cols = {col["name"] for col in inspector.get_columns("users")}
    if "access_until" not in user_cols:
        return
    if "vpn_configs" not in tables or "app_settings" not in tables:
        return
    with _migration_transaction() as conn:
        already_done = conn.execute(
            text("SELECT value FROM app_settings WHERE key = :key"),
            {"key": _USER_ACCESS_UNTIL_BACKFILL_MARKER},
        ).scalar()
        if already_done:
            return
        user_ids = conn.execute(
            text(
                """
                SELECT DISTINCT u.id
                FROM users u
                INNER JOIN vpn_configs vc ON vc.owner_id = u.id
                WHERE u.access_until IS NULL AND vc.ha_primary_config_id IS NULL
                """
            )
        ).scalars().all()
        for user_id in user_ids:
            max_deadline = _max_owned_client_access_until(conn, user_id)
            if max_deadline is None:
                continue
            conn.execute(
                text("UPDATE users SET access_until = :deadline WHERE id = :id AND access_until IS NULL"),
                {"deadline": max_deadline, "id": user_id},
            )
            logger.info("DB migration: backfilled users.access_until for user id=%s", user_id)
        conn.execute(
            text("INSERT INTO app_settings (key, value) VALUES (:key, '1')"),
            {"key": _USER_ACCESS_UNTIL_BACKFILL_MARKER},
        )


def _migrate_user_telegram_backfill() -> None:
    """Backfill telegram_id from tg_* usernames for existing Telegram-login users."""
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("users")}
    if "telegram_id" not in cols:
        return
    with _migration_transaction() as conn:
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
