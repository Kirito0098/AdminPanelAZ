"""Sending configs to Telegram must respect the requester's VPN profile visibility policy."""

from __future__ import annotations

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models import User, UserRole, VpnConfig, VpnType
from app.services.telegram_config_send import send_config_for_user

MOD = "app.services.telegram_config_send"

WG_VPN = {"path": "/az/client/wireguard/vpn/ivan-wg.conf", "protocol": "wireguard", "variant": "vpn"}
AM_AZ = {"path": "/az/client/amneziawg/antizapret/ivan-am.conf", "protocol": "amneziawg", "variant": "antizapret"}
WG_AZ = {"path": "/az/client/wireguard/antizapret/ivan-wg.conf", "protocol": "wireguard", "variant": "antizapret"}

ONLY_WG_AZ = {"routes": ["az"], "protocols": ["wireguard"], "openvpn_groups": []}


def _user() -> User:
    return User(id=7, username="ivan", password_hash="x", role=UserRole.user, telegram_id="555")


def _config() -> VpnConfig:
    return VpnConfig(id=3, node_id=1, client_name="ivan", vpn_type=VpnType.wireguard, owner_id=7)


def _send(files: list[dict], **kwargs):
    adapter = MagicMock()
    adapter.get_profile_files.return_value = [dict(item) for item in files]
    send_doc = MagicMock(return_value=(True, None))
    read = MagicMock(return_value="conf")
    with ExitStack() as stack:
        stack.enter_context(patch(f"{MOD}.get_active_adapter", return_value=adapter))
        stack.enter_context(patch(f"{MOD}.load_node_remote_hosts", return_value=[]))
        stack.enter_context(patch(f"{MOD}.read_profile_file_for_delivery", new=read))
        stack.enter_context(patch(f"{MOD}.send_tg_document_result", new=send_doc))
        stack.enter_context(patch(f"{MOD}.resolve_effective_visible_vpn_profiles", return_value=ONLY_WG_AZ))
        sent, error = send_config_for_user(
            MagicMock(),
            _config(),
            _user(),
            bot_token="token",
            run_async=False,
            **kwargs,
        )
    return SimpleNamespace(sent=sent, error=error, send_doc=send_doc, read=read)


def _read_paths(result) -> list[str]:
    return [c.args[1] for c in result.read.call_args_list]


def test_explicit_hidden_path_is_refused():
    result = _send([WG_VPN, AM_AZ, WG_AZ], path=WG_VPN["path"])

    assert result.sent == 0
    assert result.error
    result.read.assert_not_called()
    result.send_doc.assert_not_called()


def test_default_file_is_first_visible_not_first_on_disk():
    result = _send([WG_VPN, AM_AZ, WG_AZ])

    assert result.sent == 1
    assert _read_paths(result) == [WG_AZ["path"]]


def test_all_files_hidden_sends_nothing():
    result = _send([WG_VPN, AM_AZ])

    assert result.sent == 0
    assert result.error
    result.send_doc.assert_not_called()


def test_send_all_skips_hidden_files():
    result = _send([WG_VPN, AM_AZ, WG_AZ], send_all=True)

    assert result.sent == 1
    assert _read_paths(result) == [WG_AZ["path"]]
