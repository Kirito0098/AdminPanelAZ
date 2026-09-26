"""AWG2 profile writes are limited to client profile files, like OpenVPN/WireGuard profiles."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services import awg2
from app.services.awg2 import Awg2Service


@pytest.fixture()
def clients(tmp_path, monkeypatch):
    root = tmp_path / "antizapret-awg" / "clients"
    for tunnel in awg2.AWG2_TUNNELS:
        (root / tunnel).mkdir(parents=True)
    (root / "expiry.tsv").write_text("bob\t2030-01-01\n")
    monkeypatch.setattr(awg2, "AWG2_CLIENT_DIR", root)
    return root


@pytest.mark.parametrize(
    "relative",
    ["antizapret/antizapret-bob-am.conf", "vpn/vpn-bob.vpn", "vpn/vpn-bob-vpnuri.txt"],
)
def test_profile_files_can_be_written(clients, relative):
    target = clients / relative

    Awg2Service().write_profile_file(str(target), "profile")

    assert target.read_text() == "profile"


@pytest.mark.parametrize(
    "relative",
    [
        "expiry.tsv",
        "antizapret/hook.sh",
        "antizapret/antizapret-bob-vpn.png",
        "antizapret/antizapret-bob-am.conf.bak.20260920133736",
        "other/other-bob-am.conf",
        "antizapret/nested/antizapret-bob-am.conf",
    ],
)
def test_other_files_in_the_client_dir_are_refused(clients, relative):
    target = clients / relative
    before = target.read_text() if target.exists() else None

    with pytest.raises(HTTPException) as exc:
        Awg2Service().write_profile_file(str(target), "pwned")

    assert exc.value.status_code == 403
    assert (target.read_text() if target.exists() else None) == before


def test_paths_outside_the_client_dir_are_still_refused(clients):
    outside = clients.parent / "vpn-bob-am.conf"

    with pytest.raises(HTTPException) as exc:
        Awg2Service().write_profile_file(str(outside), "pwned")

    assert exc.value.status_code == 403
    assert not outside.exists()


def test_reading_is_not_narrowed(clients):
    qr = clients / "antizapret" / "antizapret-bob-vpn.png"
    qr.write_text("png")

    assert Awg2Service().read_profile_file(str(qr)) == "png"
