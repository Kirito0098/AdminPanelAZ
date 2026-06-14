from pathlib import Path

import pytest

from app.models import VpnType
from app.services.antizapret import AntiZapretService
from app.services.profile_files import (
    extract_client_from_profile_filename,
    iter_client_profile_paths,
    profile_filename_matches_client,
    profile_files_batch_key,
)


@pytest.mark.parametrize(
    ("filename", "client_name", "expected"),
    [
        ("vpn-Alex-(vpn.claymore-it.ru)-wg.conf", "Alex", True),
        ("vpn-Andrew-2-(vpn.claymore-it.ru)-wg.conf", "Andrew-2", True),
        ("vpn-Andrew_TV-(vpn.claymore-it.ru)-am.conf", "Andrew_TV", False),
        ("vpn-Test-(vpn.claymore-it.ru)-wg.conf", "Test", True),
        ("vpn-Test111111122-(vpn.claymore-it.ru)-wg.conf", "Test", False),
        ("vpn-Test111111122-(vpn.claymore-it.ru)-wg.conf", "Test111111122", True),
        ("vpn-Andrew-Main-(vpn.claymore-it.ru)-wg.conf", "Andrew", False),
    ],
)
def test_profile_filename_matches_client(filename: str, client_name: str, expected: bool) -> None:
    assert profile_filename_matches_client(filename, client_name, suffix="-wg.conf") is expected


def test_extract_client_from_profile_filename() -> None:
    assert extract_client_from_profile_filename("vpn-Andrew_TV-(vpn.claymore-it.ru)-am.conf") == "Andrew_TV"


def test_profile_files_batch_key_distinguishes_vpn_type() -> None:
    assert profile_files_batch_key("Alex", VpnType.openvpn) != profile_files_batch_key("Alex", VpnType.wireguard)


def test_get_profile_files_finds_wg_and_am_for_all_clients(tmp_path: Path) -> None:
    base = tmp_path / "client"
    clients = [
        "Alex",
        "Andrew-2",
        "Andrew_TV",
        "Test",
        "Test111111122",
    ]
    for proto, suffix in [("wireguard", "-wg.conf"), ("amneziawg", "-am.conf")]:
        directory = base / proto / "vpn"
        directory.mkdir(parents=True)
        for client in clients:
            name = f"vpn-{client}-(vpn.claymore-it.ru){suffix}"
            (directory / name).write_text("cfg", encoding="utf-8")

    service = AntiZapretService(base_path=tmp_path)
    for client in clients:
        files = service.get_profile_files(client, VpnType.wireguard)
        protocols = {item["protocol"] for item in files if item["variant"] == "vpn"}
        assert protocols == {"wireguard", "amneziawg"}, client


def test_iter_client_profile_paths(tmp_path: Path) -> None:
    directory = tmp_path / "wireguard" / "vpn"
    directory.mkdir(parents=True)
    (directory / "vpn-Andrew_TV-(vpn.claymore-it.ru)-wg.conf").write_text("x", encoding="utf-8")
    (directory / "vpn-Andrew-2-(vpn.claymore-it.ru)-wg.conf").write_text("x", encoding="utf-8")

    assert len(iter_client_profile_paths(directory, "Andrew_TV", "-wg.conf")) == 1
    assert len(iter_client_profile_paths(directory, "Andrew-2", "-wg.conf")) == 1
