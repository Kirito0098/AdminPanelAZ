"""DNS-выбор резолверов AntiZapret: патч kresd.conf не трогает остальной файл и откатывается при провале kresd."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services import kresd_dns_choice as choice
from app.services.antizapret import AntiZapretService

KRESD_CONF = """\
-- Knot DNS Resolver configuration in -*- lua -*-

local min_ttl = 300 -- Minimum TTL in seconds
local antizapret_dns = 1 -- AntiZapret VPN DNS
local vpn_dns = 2 -- Full VPN DNS
local proxy_dns = vpn_dns -- Proxy DNS
"""

SETUP = """\
SETUP_DATE=2026-10-01T00:00:00+00:00
ANTIZAPRET_DNS=1
VPN_DNS=2
ROUTE_ALL=n
"""


def test_patch_changes_only_two_lines():
    updated = choice.with_dns_choice(KRESD_CONF, antizapret=3, vpn=1)
    assert "local antizapret_dns = 3 -- AntiZapret VPN DNS" in updated
    # VPN_DNS=1 подставляет резолвер AntiZapret (как setup.sh), ссылка proxy_dns не патчится.
    assert "local vpn_dns = 3 -- Full VPN DNS" in updated
    assert "local proxy_dns = vpn_dns -- Proxy DNS" in updated
    assert updated.count("local vpn_dns") == 1
    assert updated.replace("local antizapret_dns = 3", "local antizapret_dns = 1").replace(
        "local vpn_dns = 3", "local vpn_dns = 2"
    ) == KRESD_CONF


def test_vpn_dns_one_uses_antizapret_resolver():
    assert choice.effective_vpn_dns(3, 1) == 3
    # setup.sh не переписывает строку, когда AntiZapret DNS = 1: остаётся 2 (Cloudflare/Quad9).
    assert choice.effective_vpn_dns(1, 1) == 2
    assert choice.effective_vpn_dns(5, 2) == 2


def test_missing_lines_are_reported():
    with pytest.raises(choice.KresdDnsChoiceError):
        choice.with_dns_choice("local min_ttl = 300\n", antizapret=2, vpn=1)


def test_setup_keys_are_rewritten_and_appended():
    updated = choice.with_setup_dns_keys(SETUP, antizapret=4, vpn=1)
    assert "ANTIZAPRET_DNS=4\n" in updated
    assert "VPN_DNS=1\n" in updated

    appended = choice.with_setup_dns_keys("ROUTE_ALL=n\n", antizapret=7, vpn=2)
    assert appended == "ROUTE_ALL=n\nANTIZAPRET_DNS=7\nVPN_DNS=2\n"


UPSTREAM_NEW = """\
local function upstream(dns)
	if dns == 1 then
		return russia_dns
	elseif dns == 2 then
		return world_dns
	elseif dns == 3 then
		return yandex_dns
	elseif dns == 4 then
		return google_dns
	elseif dns == 5 then
		return adguard_dns
	elseif dns == 6 then
		return geohide_dns
	else
		panic('Invalid dns value')
	end
end
"""

UPSTREAM_OLD = UPSTREAM_NEW.replace(
    "\telseif dns == 6 then\n\t\treturn geohide_dns\n",
    "\telseif dns == 6 then\n\t\treturn comss_dns\n\telseif dns == 7 then\n\t\treturn geohide_dns\n",
)


def test_options_follow_installed_kresd_conf():
    new = choice.antizapret_dns_options(KRESD_CONF + UPSTREAM_NEW)
    assert [value for value, _label in new] == ["1", "2", "3", "4", "5", "6"]
    assert dict(new)["6"].startswith("GeoHide")

    old = choice.antizapret_dns_options(KRESD_CONF + UPSTREAM_OLD)
    assert [value for value, _label in old] == ["1", "2", "3", "4", "5", "6", "7"]
    assert dict(old)["6"].startswith("Comss")
    assert dict(old)["7"].startswith("GeoHide")


def test_new_base_rejects_removed_comss_number():
    conf = KRESD_CONF + UPSTREAM_NEW
    with pytest.raises(choice.KresdDnsChoiceError):
        choice.with_dns_choice(conf, antizapret=7, vpn=2)
    assert "local antizapret_dns = 6" in choice.with_dns_choice(conf, antizapret=6, vpn=2)


def test_get_dns_servers_uses_installed_options(tmp_path: Path):
    knot = tmp_path / "knot-resolver"
    knot.mkdir()
    (knot / "kresd.conf").write_text(KRESD_CONF + UPSTREAM_NEW, encoding="utf-8")
    base = tmp_path / "antizapret"
    base.mkdir()
    (base / "setup").write_text(SETUP.replace("ANTIZAPRET_DNS=1", "ANTIZAPRET_DNS=7"), encoding="utf-8")
    svc = AntiZapretService(base_path=base)
    svc.knot_resolver_dir = knot

    result = svc.get_dns_servers()

    assert [option["value"] for option in result["antizapret_options"]] == ["1", "2", "3", "4", "5", "6"]
    assert any("ANTIZAPRET_DNS=7" in warning for warning in result["warnings"])


@pytest.fixture
def service(tmp_path: Path, monkeypatch):
    knot = tmp_path / "knot-resolver"
    knot.mkdir()
    (knot / "kresd.conf").write_text(KRESD_CONF, encoding="utf-8")
    base = tmp_path / "antizapret"
    base.mkdir()
    (base / "setup").write_text(SETUP, encoding="utf-8")
    svc = AntiZapretService(base_path=base)
    svc.knot_resolver_dir = knot
    monkeypatch.setattr(svc, "_restart_kresd", lambda unit: None)
    monkeypatch.setattr(svc, "_restart_antizapret", lambda: None)
    return svc


def test_apply_writes_conf_and_setup(service):
    result = service.apply_dns_servers(antizapret=3, vpn=1)

    conf = (service.knot_resolver_dir / "kresd.conf").read_text(encoding="utf-8")
    assert "local antizapret_dns = 3" in conf
    assert "local vpn_dns = 3" in conf
    setup = (service.base_path / "setup").read_text(encoding="utf-8")
    assert "ANTIZAPRET_DNS=3\n" in setup
    assert "VPN_DNS=1\n" in setup
    assert result["antizapret"] == "3" and result["vpn"] == "1"
    # vpn_dns изменился → kresd@2; VPN_DNS изменился → antizapret (DNAT/DoT в up.sh).
    assert result["restarted"] == ["kresd@1", "kresd@2", "antizapret"]
    assert result["warnings"] == []


def test_apply_restarts_only_resolver_for_antizapret_dns(service):
    result = service.apply_dns_servers(antizapret=4, vpn=2)

    conf = (service.knot_resolver_dir / "kresd.conf").read_text(encoding="utf-8")
    assert "local antizapret_dns = 4" in conf
    assert "local vpn_dns = 2" in conf
    assert result["restarted"] == ["kresd@1"]


def test_apply_rolls_back_when_kresd_fails(service, monkeypatch):
    monkeypatch.setattr(service, "_restart_kresd", lambda unit: f"Unit {unit} failed")

    with pytest.raises(HTTPException) as exc:
        service.apply_dns_servers(antizapret=5, vpn=1)

    assert exc.value.status_code == 400
    assert (service.knot_resolver_dir / "kresd.conf").read_text(encoding="utf-8") == KRESD_CONF
    assert (service.base_path / "setup").read_text(encoding="utf-8") == SETUP
