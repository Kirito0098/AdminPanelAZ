"""Rules for names of newly created VPN clients, shared by every creation path."""

import json
import re

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import User, VpnConfig

RESERVED_CLIENT_NAME_PREFIXES = ("vpn-", "antizapret-")

_TRAILING_INDEX_RE = re.compile(r"-\d+$")
_BASE_N_RE = re.compile(r"^(.+)-(\d+)$")


def assert_client_base_name_valid(name: str) -> str:
    """Validate and normalize a plan base name: 1–28 chars, no trailing ``-N``.

    Trailing ``-N`` is reserved for plan names (``ivan-2`` .. ``ivan-20``).
    """
    cleaned = (name or "").strip()
    if not cleaned or len(cleaned) > 28:
        raise ValueError("Имя конфигов: 1–28 символов")
    if _TRAILING_INDEX_RE.search(cleaned):
        raise ValueError("Имя конфигов не может заканчиваться на -число (например ivan-2)")
    return cleaned


def plan_name_for_index(base: str, index: int) -> str:
    """Plan config name for an index: 1 → base, k → base-k."""
    if index == 1:
        return base
    return f"{base}-{index}"


def names_under_base(base: str) -> set[str]:
    """Lower-cased ``base`` plus ``base-2`` … ``base-20`` (plan name namespace)."""
    cleaned = (base or "").strip()
    if not cleaned:
        return set()
    return {plan_name_for_index(cleaned, index).lower() for index in range(1, 21)}


def parse_plan_indexes(raw: str | None) -> list[int]:
    """Parse ``plan_config_indexes`` JSON column into a list of ints (empty on any error)."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    indexes: list[int] = []
    for item in data:
        try:
            indexes.append(int(item))
        except (TypeError, ValueError):
            continue
    return indexes


def assert_name_not_reserved_by_other_user(db, client_name: str, *, owner_id: int | None) -> None:
    """Block a name if another user reserved its base (``base`` .. ``base-20``).

    ``owner_id=None`` blocks every foreign base; an owner's own names stay free.
    """
    lowered = (client_name or "").lower()
    match = _BASE_N_RE.fullmatch(lowered)
    if match and 2 <= int(match.group(2)) <= 20:
        base_l = match.group(1)
    else:
        base_l = lowered
    q = db.query(User).filter(func.lower(User.client_base_name) == base_l)
    if owner_id is not None:
        q = q.filter(User.id != owner_id)
    owner = q.first()
    if owner is not None:
        raise ValueError(f"Имя занято пользователем {owner.username}")


def validate_new_client_name(
    db: Session, *, node_id: int, client_name: str, owner_id: int | None = None
) -> None:
    """Raise ``ValueError`` with a user-facing message when a new client may not take this name.

    AntiZapret ``client.sh`` strips the reserved prefixes, and WireGuard / AmneziaWG2 policies
    are keyed by the lower-cased name, so such names would collide with another client.
    """
    lowered = client_name.lower()
    for prefix in RESERVED_CLIENT_NAME_PREFIXES:
        if lowered.startswith(prefix):
            raise ValueError(f"Имя клиента не может начинаться с «{prefix}»: AntiZapret отрезает этот префикс")
    clash = (
        db.query(VpnConfig)
        .filter(
            VpnConfig.node_id == node_id,
            func.lower(VpnConfig.client_name) == lowered,
            VpnConfig.client_name != client_name,
        )
        .first()
    )
    if clash is not None:
        raise ValueError(
            f"На этом узле уже есть клиент «{clash.client_name}»: имена не должны отличаться только регистром"
        )
    # Reservation: foreign client_base_name blocks base and base-2..base-20.
    assert_name_not_reserved_by_other_user(db, client_name, owner_id=owner_id)
