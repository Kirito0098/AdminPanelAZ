from pathlib import Path
from unittest.mock import patch

from app.services import awg2_runtime


def _write_awg2_tree(tmp_path: Path, conf_body: str, *, services_env: str | None = None) -> dict[str, Path]:
    amnezia = tmp_path / "amneziawg"
    amnezia.mkdir(parents=True)
    (amnezia / "services.env").write_text(
        services_env or "AZ_IFACE=antizapret-awg\nVPN_IFACE=vpn-awg\n",
        encoding="utf-8",
    )
    for iface in ("antizapret-awg", "vpn-awg"):
        (amnezia / f"{iface}.conf").write_text(conf_body, encoding="utf-8")
    return awg2_runtime._build_config_files(amnezia)


def test_block_removes_peer_via_mocked_awg(tmp_path: Path):
    config_files = _write_awg2_tree(
        tmp_path,
        """[Interface]
PrivateKey = server

# Client = ivan
[Peer]
PublicKey = pub-ivan
AllowedIPs = 10.8.0.2/32
""",
    )
    calls: list[list[str]] = []

    def fake_run(args, timeout=awg2_runtime.COMMAND_TIMEOUT_SECONDS):
        calls.append(list(args))

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    with patch("app.services.awg2_runtime._run", side_effect=fake_run):
        result = awg2_runtime.block_client_runtime("ivan", config_files=config_files)

    assert result["success"] is True
    assert result["removed_count"] == 2
    assert result["blocked"] == 2
    assert result["error_count"] == 0
    assert calls == [
        ["awg", "set", "antizapret-awg", "peer", "pub-ivan", "remove"],
        ["awg", "set", "vpn-awg", "peer", "pub-ivan", "remove"],
    ]


def test_unblock_restores_from_ondisk_conf(tmp_path: Path):
    config_files = _write_awg2_tree(
        tmp_path,
        """[Interface]
PrivateKey = server

# Client = ivan
[Peer]
PublicKey = pub-ivan
PresharedKey = psk-ivan
AllowedIPs = 10.8.0.2/32
""",
    )
    calls: list[list[str]] = []

    def fake_run(args, timeout=awg2_runtime.COMMAND_TIMEOUT_SECONDS):
        calls.append(list(args))

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    with patch("app.services.awg2_runtime._run", side_effect=fake_run):
        blocked = awg2_runtime.block_client_runtime("ivan", config_files=config_files)
        restored = awg2_runtime.unblock_client_runtime("ivan", config_files=config_files)

    assert blocked["success"] is True
    assert restored["success"] is True
    assert restored["synced_count"] == 2
    assert restored["restored"] == 2
    restore_calls = [call for call in calls if call[:5] == ["awg", "set", "antizapret-awg", "peer", "pub-ivan"]]
    restore_calls += [call for call in calls if call[:5] == ["awg", "set", "vpn-awg", "peer", "pub-ivan"]]
    assert len(restore_calls) == 4
    assert any(call[-2:] == ["pub-ivan", "remove"] for call in calls)
    assert sum("allowed-ips" in call for call in restore_calls) == 2
    assert sum("preshared-key" in call for call in restore_calls) == 2
    assert "PublicKey = pub-ivan" in (tmp_path / "amneziawg" / "antizapret-awg.conf").read_text(encoding="utf-8")


def test_collect_peers_reads_bare_hash_name_comment(tmp_path: Path):
    config_files = _write_awg2_tree(
        tmp_path,
        """[Interface]
PrivateKey = server

# ivan
[Peer]
PublicKey = pub-ivan
AllowedIPs = 10.8.0.2/32
""",
    )

    peers = awg2_runtime._collect_client_peers("ivan", config_files=config_files)

    assert peers == [
        ("antizapret-awg", "pub-ivan"),
        ("vpn-awg", "pub-ivan"),
    ]


def test_block_missing_peer_returns_error(tmp_path: Path):
    config_files = _write_awg2_tree(
        tmp_path,
        """[Interface]
PrivateKey = server
""",
    )

    result = awg2_runtime.block_client_runtime("ivan", config_files=config_files)

    assert result == {
        "success": False,
        "removed_count": 0,
        "blocked": 0,
        "error_count": 1,
        "errors": [{"interface": None, "stderr": "Пиры клиента не найдены"}],
    }
