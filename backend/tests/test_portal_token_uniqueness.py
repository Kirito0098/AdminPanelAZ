"""Active portal token uniqueness per (node_id, client_name)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import ClientPortalToken, Node


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    # create_all may skip sqlite_where on some dialects — ensure partial unique index.
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_client_portal_tokens_active_node_client
                ON client_portal_tokens (node_id, client_name)
                WHERE revoked_at IS NULL
                """
            )
        )
    Session = sessionmaker(bind=engine)
    session = Session()
    node = Node(name="local", host="127.0.0.1", is_local=True)
    session.add(node)
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_cannot_insert_two_active_tokens_same_client(db_session):
    node_id = db_session.query(Node).one().id
    db_session.add(
        ClientPortalToken(token="tok-a", node_id=node_id, client_name="alice")
    )
    db_session.commit()
    db_session.add(
        ClientPortalToken(token="tok-b", node_id=node_id, client_name="alice")
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_revoked_token_allows_new_active(db_session):
    node_id = db_session.query(Node).one().id
    old = ClientPortalToken(token="tok-old", node_id=node_id, client_name="bob")
    db_session.add(old)
    db_session.commit()
    old.revoked_at = old.created_at
    db_session.commit()
    db_session.add(ClientPortalToken(token="tok-new", node_id=node_id, client_name="bob"))
    db_session.commit()
    active = (
        db_session.query(ClientPortalToken)
        .filter(
            ClientPortalToken.client_name == "bob",
            ClientPortalToken.revoked_at.is_(None),
        )
        .all()
    )
    assert len(active) == 1
    assert active[0].token == "tok-new"
