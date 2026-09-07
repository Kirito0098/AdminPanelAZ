"""get_service_status should probe expected units in one systemctl call."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.services.antizapret import AntiZapretService


def test_get_service_status_coalesces_systemctl_is_active(tmp_path: Path, monkeypatch):
    setup = tmp_path / "setup"
    setup.write_text(
        "OPENVPN_UDP_ENABLE=y\nOPENVPN_TCP_ENABLE=y\nWIREGUARD_ENABLE=y\n",
        encoding="utf-8",
    )
    service = AntiZapretService(base_path=tmp_path)

    runs: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        runs.append(list(cmd))
        # One status line per requested unit.
        units = cmd[2:]
        stdout = "\n".join("active" if "udp" in u or u.endswith("@vpn") else "inactive" for u in units)
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("app.services.antizapret.subprocess.run", fake_run)
    monkeypatch.setattr(
        "app.services.antizapret_settings.read_protocol_enable_flags",
        lambda _path: {
            "OPENVPN_UDP_ENABLE": "y",
            "OPENVPN_TCP_ENABLE": "y",
            "WIREGUARD_ENABLE": "y",
        },
    )
    monkeypatch.setattr(
        "app.services.antizapret_settings.is_vpn_monitor_service_expected",
        lambda svc, _flags: True,
    )

    result = service.get_service_status()

    assert len(runs) == 1
    assert runs[0][:2] == ["systemctl", "is-active"]
    assert len(runs[0]) > 3
    assert len(result) == len(runs[0]) - 2
    assert all(hasattr(item, "name") and hasattr(item, "active") for item in result)
