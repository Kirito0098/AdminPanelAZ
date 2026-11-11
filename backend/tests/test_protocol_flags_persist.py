"""Флаги протоколов в setup: карточка OpenVPN меняет systemd, но не должна расходиться с setup.

Мониторинг и авто-перезапуск читают ``OPENVPN_UDP_ENABLE`` / ``OPENVPN_TCP_ENABLE`` /
``WIREGUARD_ENABLE`` из setup. Если их не обновлять, выключенный протокол показывается как
упавший, а включённый на реплике — как отсутствующий.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.services.antizapret import AntiZapretService
from app.services.antizapret_settings import read_protocol_enable_flags, write_protocol_enable_flags


def test_write_protocol_flags_replaces_and_appends(tmp_path: Path):
    setup = tmp_path / "setup"
    setup.write_text("ROUTE_ALL=n\nOPENVPN_UDP_ENABLE=y\nOPENVPN_TCP_ENABLE=n\n", encoding="utf-8")

    write_protocol_enable_flags(
        setup,
        {"OPENVPN_UDP_ENABLE": "n", "OPENVPN_TCP_ENABLE": "y", "WIREGUARD_ENABLE": "y"},
    )

    content = setup.read_text(encoding="utf-8")
    assert "ROUTE_ALL=n\n" in content
    assert "OPENVPN_UDP_ENABLE=n\n" in content
    assert "OPENVPN_TCP_ENABLE=y\n" in content
    assert "WIREGUARD_ENABLE=y\n" in content
    assert read_protocol_enable_flags(setup) == {
        "OPENVPN_UDP_ENABLE": "n",
        "OPENVPN_TCP_ENABLE": "y",
        "WIREGUARD_ENABLE": "y",
    }


def test_apply_protocols_persists_setup_flags(tmp_path: Path, monkeypatch):
    base = tmp_path / "antizapret"
    base.mkdir()
    (base / "setup").write_text(
        "OPENVPN_UDP_ENABLE=y\nOPENVPN_TCP_ENABLE=n\nWIREGUARD_ENABLE=y\n",
        encoding="utf-8",
    )
    svc = AntiZapretService(base_path=base)
    monkeypatch.setattr(svc, "get_openvpn_tuning", lambda: {})
    monkeypatch.setattr(
        "app.services.antizapret.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )

    states = {
        "openvpn-server@antizapret-udp": True,
        "openvpn-server@vpn-udp": True,
        "openvpn-server@antizapret-tcp": False,
        "openvpn-server@vpn-tcp": False,
        "wg-quick@antizapret": True,
        "wg-quick@vpn": True,
    }
    monkeypatch.setattr(AntiZapretService, "_unit_enabled", staticmethod(lambda unit: states.get(unit)))

    svc.apply_protocols(
        {"openvpn-server@antizapret-tcp": False, "openvpn-server@vpn-tcp": False}
    )

    assert read_protocol_enable_flags(base / "setup") == {
        "OPENVPN_UDP_ENABLE": "y",
        "OPENVPN_TCP_ENABLE": "n",
        "WIREGUARD_ENABLE": "y",
    }


def test_mixed_protocol_state_keeps_gate_open(tmp_path: Path, monkeypatch):
    base = tmp_path / "antizapret"
    base.mkdir()
    (base / "setup").write_text("", encoding="utf-8")
    svc = AntiZapretService(base_path=base)
    monkeypatch.setattr(svc, "get_openvpn_tuning", lambda: {})
    monkeypatch.setattr(
        "app.services.antizapret.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    monkeypatch.setattr(
        AntiZapretService,
        "_unit_enabled",
        staticmethod(lambda unit: unit == "openvpn-server@antizapret-udp"),
    )

    svc.apply_protocols({"openvpn-server@antizapret-udp": True})

    # Один из двух UDP-юнитов включён — не скрываем возможно упавший второй из мониторинга.
    assert read_protocol_enable_flags(base / "setup")["OPENVPN_UDP_ENABLE"] == "y"
    assert read_protocol_enable_flags(base / "setup")["OPENVPN_TCP_ENABLE"] == "n"
