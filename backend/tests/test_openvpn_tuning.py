"""OpenVPN server conf: duplicate-cn / логи включаются построчно, при провале рестарта конфиги откатываются."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services import openvpn_tuning as tuning
from app.services.antizapret import AntiZapretService

CONF = """\
mode server
proto udp4
port 50443
duplicate-cn
#verb 4
#log-append logs/antizapret-udp.log
#status logs/antizapret-udp-status.log 30
tun-mtu 1420
data-ciphers "AES-128-GCM:AES-256-GCM:CHACHA20-POLY1305"
"""


def test_state_is_read_from_conf():
    assert tuning.duplicate_cn_enabled(CONF) is True
    assert tuning.logs_enabled(CONF) is False
    assert tuning.tun_mtu(CONF) == 1420
    assert tuning.dco_mode(CONF) == "on"


def test_duplicate_cn_toggle_keeps_other_lines():
    updated = tuning.with_duplicate_cn(CONF, False)

    assert tuning.duplicate_cn_enabled(updated) is False
    assert updated.replace("#duplicate-cn", "duplicate-cn") == CONF


def test_logs_toggle_round_trip():
    enabled = tuning.with_logs(CONF, True)
    assert tuning.logs_enabled(enabled) is True
    assert "#verb" not in enabled
    assert tuning.with_logs(enabled, False) == CONF


def test_dco_modes():
    assert tuning.dco_mode("disable-dco\n") == "off"
    assert tuning.dco_mode('data-ciphers "AES-128-GCM:AES-128-CBC"\n') == "off"
    assert tuning.dco_mode("mode server\n") == "unknown"


def test_missing_lines_are_reported():
    with pytest.raises(tuning.OpenVpnTuningError):
        tuning.with_duplicate_cn("mode server\n", False)
    with pytest.raises(tuning.OpenVpnTuningError):
        tuning.with_logs("mode server\n", True)


def test_wireguard_mtu():
    assert tuning.wireguard_mtu("[Interface]\nMTU = 1420\n") == 1420


def test_mtu_patch_and_validation():
    assert "tun-mtu 1380" in tuning.with_tun_mtu(CONF, 1380)
    assert "MTU = 1380" in tuning.with_wireguard_mtu("[Interface]\nMTU = 1420\n", 1380)

    with pytest.raises(tuning.OpenVpnTuningError):
        tuning.with_tun_mtu(CONF, 1200)
    with pytest.raises(tuning.OpenVpnTuningError):
        tuning.with_wireguard_mtu("no mtu here\n", 1420)


def test_dco_toggle_matches_openvpn_script():
    off = tuning.with_dco(CONF, False)
    assert 'data-ciphers "AES-128-GCM:AES-256-GCM:CHACHA20-POLY1305:AES-128-CBC:AES-192-CBC:AES-256-CBC"' in off
    assert "disable-dco" in off
    assert tuning.dco_mode(off) == "off"

    back_on = tuning.with_dco(off, True)
    assert "disable-dco" not in back_on
    assert tuning.dco_mode(back_on) == "on"
    # Дублей data-ciphers не появляется.
    assert back_on.count("data-ciphers") == 1


@pytest.fixture
def service(tmp_path: Path, monkeypatch):
    svc = AntiZapretService(base_path=tmp_path)
    files = {"antizapret-udp.conf": CONF}
    monkeypatch.setattr(svc, "list_openvpn_server_confs", lambda: list(files))
    monkeypatch.setattr(svc, "read_openvpn_server_conf", lambda name: files[name])
    monkeypatch.setattr(svc, "write_openvpn_server_conf", lambda name, content: files.__setitem__(name, content))
    monkeypatch.setattr(svc, "_unit_enabled", staticmethod(lambda unit: True))
    monkeypatch.setattr(svc, "_openvpn_binary_state", staticmethod(lambda: {"custom_binary": False, "unit_exec": "/usr/sbin/openvpn", "in_use": False}))
    return svc, files


def test_apply_writes_conf_and_restarts(service, monkeypatch):
    svc, files = service
    monkeypatch.setattr(svc, "restart_service", lambda unit: "ok")

    result = svc.apply_openvpn_tuning(duplicate=False, logs=True)

    assert tuning.duplicate_cn_enabled(files["antizapret-udp.conf"]) is False
    assert tuning.logs_enabled(files["antizapret-udp.conf"]) is True
    assert result["restarted"] == ["openvpn-server@antizapret-udp"]


def test_apply_rolls_back_when_restart_fails(service, monkeypatch):
    svc, files = service

    def _fail(unit: str) -> str:
        raise HTTPException(status_code=500, detail="restart failed")

    monkeypatch.setattr(svc, "restart_service", _fail)

    with pytest.raises(HTTPException) as exc:
        svc.apply_openvpn_tuning(duplicate=False, logs=True)

    assert exc.value.status_code == 400
    assert files["antizapret-udp.conf"] == CONF


def test_apply_mtu_patches_server_conf_and_wg_template(service, monkeypatch, tmp_path):
    svc, files = service
    templates = tmp_path / "templates"
    templates.mkdir()
    server_wg = templates / "antizapret.conf"
    server_wg.write_text("[Interface]\nMTU = 1420\n", encoding="utf-8")
    client_wg = templates / "antizapret-client-wg.conf"
    client_wg.write_text("[Interface]\nPrivateKey = x\n", encoding="utf-8")
    live = tmp_path / "live"
    live.mkdir()
    live_wg = live / "antizapret.conf"
    live_wg.write_text("[Interface]\nMTU = 1420\n", encoding="utf-8")
    monkeypatch.setattr("app.services.antizapret.WIREGUARD_TEMPLATES_DIR", templates)
    monkeypatch.setattr("app.services.antizapret.WIREGUARD_SERVER_CONFIG_DIR", live)
    monkeypatch.setattr(svc, "restart_service", lambda unit: "ok")

    result = svc.apply_mtu(openvpn_mtu=1380, wireguard_mtu=1280)

    assert "tun-mtu 1380" in files["antizapret-udp.conf"]
    assert server_wg.read_text(encoding="utf-8").endswith("MTU = 1280\n")
    # Живой server conf рендерится из шаблона — правим и его, иначе wg-quick поднимет старый MTU.
    assert live_wg.read_text(encoding="utf-8").endswith("MTU = 1280\n")
    # Клиентский шаблон без MTU не трогаем.
    assert client_wg.read_text(encoding="utf-8") == "[Interface]\nPrivateKey = x\n"
    assert "openvpn-server@antizapret-udp" in result["restarted"]
    assert "wg-quick@antizapret" in result["restarted"]


def _wg_paths(monkeypatch, tmp_path):
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "antizapret.conf").write_text("[Interface]\nMTU = 1420\n", encoding="utf-8")
    live = tmp_path / "live"
    live.mkdir()
    live_conf = live / "antizapret.conf"
    live_conf.write_text("[Interface]\nMTU = 1420\n", encoding="utf-8")
    monkeypatch.setattr("app.services.antizapret.WIREGUARD_TEMPLATES_DIR", templates)
    monkeypatch.setattr("app.services.antizapret.WIREGUARD_SERVER_CONFIG_DIR", live)
    return templates / "antizapret.conf", live_conf


def test_apply_mtu_openvpn_only_keeps_wireguard(service, monkeypatch, tmp_path):
    svc, files = service
    template_wg, live_wg = _wg_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(svc, "restart_service", lambda unit: "ok")

    result = svc.apply_mtu(openvpn_mtu=1380)

    assert "tun-mtu 1380" in files["antizapret-udp.conf"]
    assert template_wg.read_text(encoding="utf-8").endswith("MTU = 1420\n")
    assert live_wg.read_text(encoding="utf-8").endswith("MTU = 1420\n")
    assert result["restarted"] == ["openvpn-server@antizapret-udp"]


def test_apply_mtu_wireguard_only_keeps_openvpn(service, monkeypatch, tmp_path):
    svc, files = service
    template_wg, live_wg = _wg_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(svc, "restart_service", lambda unit: "ok")

    result = svc.apply_mtu(wireguard_mtu=1280)

    assert files["antizapret-udp.conf"] == CONF
    assert template_wg.read_text(encoding="utf-8").endswith("MTU = 1280\n")
    assert live_wg.read_text(encoding="utf-8").endswith("MTU = 1280\n")
    assert result["restarted"] == ["wg-quick@antizapret", "wg-quick@vpn"]


def test_apply_mtu_requires_a_value(service):
    svc, _files = service

    with pytest.raises(HTTPException) as exc:
        svc.apply_mtu()

    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as bad:
        svc.apply_mtu(openvpn_mtu=1200)

    assert bad.value.status_code == 409


def test_apply_dco_writes_ciphers(service, monkeypatch):
    svc, files = service
    monkeypatch.setattr(svc, "restart_service", lambda unit: "ok")

    result = svc.apply_dco(False)

    assert "disable-dco" in files["antizapret-udp.conf"]
    assert result["dco"] == "off"

    svc.apply_dco(True)
    assert "disable-dco" not in files["antizapret-udp.conf"]
    assert result["restarted"] == ["openvpn-server@antizapret-udp"]
