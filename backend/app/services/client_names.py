"""Rules for names of newly created VPN clients, shared by every creation path."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import VpnConfig

RESERVED_CLIENT_NAME_PREFIXES = ("vpn-", "antizapret-")


def validate_new_client_name(db: Session, *, node_id: int, client_name: str) -> None:
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
