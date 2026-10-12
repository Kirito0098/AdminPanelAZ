from app.services.openvpn_ban_hook import MIRROR_FILENAME, ensure_openvpn_ban_check


def test_unreadable_source_keeps_existing_mirror(tmp_path):
    az = tmp_path / "antizapret"
    (az / "config" / "banned_clients").mkdir(parents=True)
    server_dir = tmp_path / "server"
    script = server_dir / "scripts" / "client-connect.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    mirror = server_dir / MIRROR_FILENAME
    mirror.write_text("alice\n", encoding="utf-8")

    result = ensure_openvpn_ban_check(az, client_connect_paths=(script,))

    assert result["success"] is False
    assert mirror.read_text(encoding="utf-8") == "alice\n"
