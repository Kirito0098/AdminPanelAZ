"""Stage 1 Task 2: base name validation and cross-user reservation."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import User, UserRole
from app.services.client_names import (
    assert_client_base_name_valid,
    assert_name_not_reserved_by_other_user,
    parse_plan_indexes,
    plan_name_for_index,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_trailing_digits_rejected():
    with pytest.raises(ValueError, match="-\\d+"):
        assert_client_base_name_valid("ivan-2")


def test_assert_client_base_name_valid_happy_path():
    assert assert_client_base_name_valid("  ivan  ") == "ivan"
    assert assert_client_base_name_valid("ivan") == "ivan"


def test_assert_client_base_name_valid_rejects_empty_and_long():
    with pytest.raises(ValueError, match="1–28 символов"):
        assert_client_base_name_valid("")
    with pytest.raises(ValueError, match="1–28 символов"):
        assert_client_base_name_valid(" " * 5)
    with pytest.raises(ValueError, match="1–28 символов"):
        assert_client_base_name_valid("a" * 29)


def test_plan_name_for_index():
    assert plan_name_for_index("ivan", 1) == "ivan"
    assert plan_name_for_index("ivan", 2) == "ivan-2"
    assert plan_name_for_index("ivan", 3) == "ivan-3"


def test_parse_plan_indexes():
    assert parse_plan_indexes(None) == []
    assert parse_plan_indexes("") == []
    assert parse_plan_indexes("[]") == []
    assert parse_plan_indexes("[1, 2, 3]") == [1, 2, 3]
    assert parse_plan_indexes("[1]") == [1]
    assert parse_plan_indexes("not json") == []
    assert parse_plan_indexes('"not a list"') == []
    assert parse_plan_indexes("{1: 2}") == []


@pytest.fixture()
def other_user_with_base_ivan(db):
    user = User(username="other", password_hash="x", role=UserRole.user, client_base_name="ivan")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_reservation_blocks_foreign_base_and_k(db, other_user_with_base_ivan):
    with pytest.raises(ValueError, match="занято"):
        assert_name_not_reserved_by_other_user(db, "ivan", owner_id=999)
    with pytest.raises(ValueError, match="занято"):
        assert_name_not_reserved_by_other_user(db, "ivan-7", owner_id=999)
    with pytest.raises(ValueError, match="занято"):
        assert_name_not_reserved_by_other_user(db, "ivan-20", owner_id=999)


def test_reservation_does_not_block_own_base(db, other_user_with_base_ivan):
    ivan = db.query(User).filter(User.client_base_name == "ivan").one()
    # Own names are free: base itself and base-k are allowed for the owner.
    assert_name_not_reserved_by_other_user(db, "ivan", owner_id=ivan.id)
    assert_name_not_reserved_by_other_user(db, "ivan-3", owner_id=ivan.id)


def test_reservation_ignores_users_without_base(db):
    assert_name_not_reserved_by_other_user(db, "ivan", owner_id=None)
    assert_name_not_reserved_by_other_user(db, "ivan-9", owner_id=None)
