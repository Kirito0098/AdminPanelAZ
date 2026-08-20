"""Tests for live online client name resolution used by traffic + Telegram."""

from datetime import datetime, timedelta
from types import SimpleNamespace

from app.schemas import OpenVpnClient, WireGuardPeer
from app.services.traffic import active_clients as active_mod


class _Adapter:
    def __init__(self, *, ovpn=None, wg=None):
        self._ovpn = ovpn or []
        self._wg = wg or []

    def parse_openvpn_status(self):
        return self._ovpn

    def parse_wireguard_status(self):
        return self._wg


def test_live_active_names_includes_ovpn_and_online_wg(monkeypatch):
    now = datetime.utcnow()
    node = SimpleNamespace(id=1, name="local")
    adapter = _Adapter(
        ovpn=[
            OpenVpnClient(
                common_name="Alice",
                real_address="1.1.1.1:1",
                virtual_address="10.0.0.2",
                bytes_received=1,
                bytes_sent=2,
                connected_since="now",
                connected_since_ts=1,
            )
        ],
        wg=[
            WireGuardPeer(
                interface="antizapret",
                public_key="pk",
                client_name="Bob_WG",
                latest_handshake=(now - timedelta(seconds=10)).isoformat(),
            ),
            WireGuardPeer(
                interface="vpn",
                public_key="pk2",
                client_name="Ghost",
                latest_handshake=(now - timedelta(seconds=400)).isoformat(),
            ),
        ],
    )
    monkeypatch.setattr(active_mod, "get_adapter_for_node", lambda _n: adapter)
    monkeypatch.setattr(
        "app.services.feature_toggles.is_awg2_enabled",
        lambda _db: False,
    )

    names = active_mod.live_active_names_for_node(SimpleNamespace(), node)
    assert names == {"Alice", "Bob_WG"}


def test_live_active_names_falls_back_to_db_when_probe_empty(monkeypatch):
    node = SimpleNamespace(id=7, name="local")
    adapter = _Adapter()
    monkeypatch.setattr(active_mod, "get_adapter_for_node", lambda _n: adapter)
    monkeypatch.setattr(
        "app.services.feature_toggles.is_awg2_enabled",
        lambda _db: False,
    )
    monkeypatch.setattr(
        active_mod,
        "db_active_traffic_client_names",
        lambda _db, node_id: {"FromDB"} if node_id == 7 else set(),
    )

    names = active_mod.live_active_names_for_node(SimpleNamespace(), node)
    assert names == {"FromDB"}


def test_telegram_traffic_summary_uses_active_names(monkeypatch):
    """Regression: /traffic must not pass an empty active set (always online 0)."""
    from app.services.telegram_bot_handlers import traffic as tg_traffic

    captured: dict = {}

    class _Collector:
        def __init__(self, db, node_id):
            captured["node_id"] = node_id

        def get_summary(self, active_names, stale_seconds):
            captured["active_names"] = set(active_names)
            captured["stale_seconds"] = stale_seconds
            row = SimpleNamespace(
                common_name="Claymore_OpenWRT",
                traffic_1d=15_000_000_000,
                total_received=100,
                total_sent=200,
                is_active="Claymore_OpenWRT" in active_names,
            )
            return [row], SimpleNamespace()

    node = SimpleNamespace(id=3, name="Локальный сервер")
    monkeypatch.setattr(tg_traffic, "get_active_node", lambda _db: node)
    monkeypatch.setattr(tg_traffic, "TrafficCollectorService", _Collector)
    monkeypatch.setattr(
        tg_traffic,
        "live_active_names_for_node",
        lambda _db, _node: {"Claymore_OpenWRT"},
    )
    monkeypatch.setattr(tg_traffic, "is_admin", lambda _u: True)

    sent: dict = {}

    async def _send_or_edit(ctx, text, markup=None, message_id=None):
        sent["text"] = text

    monkeypatch.setattr(tg_traffic, "send_or_edit", _send_or_edit)
    monkeypatch.setattr(tg_traffic, "nav_footer_keyboard", lambda **kwargs: {})

    import asyncio

    ctx = SimpleNamespace(db=object(), user=SimpleNamespace(), bot_token="t", chat_id=1)
    asyncio.run(tg_traffic.handle_traffic(ctx))

    assert captured["active_names"] == {"Claymore_OpenWRT"}
    assert "online <b>1</b>" in sent["text"]
