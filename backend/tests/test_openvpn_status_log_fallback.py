"""OpenVPN status snapshots written by systemd must be readable as a fallback source."""

from __future__ import annotations

from pathlib import Path

from app.services.openvpn_management import openvpn_management_service as service

STATUS_V2 = (
    "TITLE,OpenVPN 2.7.6 x86_64-pc-linux-gnu [SSL (OpenSSL)] [COMP_STUB] [EPOLL] [MH/PKTINFO] [AEAD] [DCO]\n"
    "TIME,2026-10-27 18:42:21,1793115741\n"
    "HEADER,CLIENT_LIST,Common Name,Real Address,Virtual Address,Virtual IPv6 Address,"
    "Bytes Received,Bytes Sent,Connected Since,Connected Since (time_t),Username,Client ID,"
    "Peer ID,Data Channel Cipher\n"
    "CLIENT_LIST,Andrew_2,udp4:185.211.159.178:38683,172.28.0.2,,521369,6790348,"
    "2026-10-27 18:36:46,1793115406,UNDEF,1041,0,AES-128-GCM\n"
    "CLIENT_LIST,test10,udp4:203.0.113.7:1194,172.28.0.9,,1024,2048,"
    "2026-10-27 18:40:00,1793115600,UNDEF,1042,1,AES-128-GCM\n"
    "HEADER,ROUTING_TABLE,Virtual Address,Common Name,Real Address,Last Ref,Last Ref (time_t)\n"
    "ROUTING_TABLE,172.28.0.2,Andrew_2,udp4:185.211.159.178:38683,2026-10-27 18:36:46,1793115406\n"
    "GLOBAL_STATS,Max bcast/mcast queue length,0\n"
    "END\n"
)


def _write(tmp_path: Path, name: str, content: str = STATUS_V2) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_status_snapshot_columns_are_read_by_header(tmp_path):
    path = _write(tmp_path, "status-vpn-udp.log")

    clients = service.parse_clients_from_status_log_file(path, "vpn-udp")

    assert [client.common_name for client in clients] == ["Andrew_2", "test10"]
    first = clients[0]
    assert first.bytes_received == 521369
    assert first.bytes_sent == 6790348
    assert first.connected_since == "2026-10-27 18:36:46"
    assert first.connected_since_ts == 1793115406
    assert first.virtual_address == "172.28.0.2"
    assert first.data_source == "status_log"


def test_collect_clients_falls_back_to_the_systemd_snapshot_name(tmp_path, monkeypatch):
    _write(tmp_path, "status-antizapret-udp.log")
    monkeypatch.setattr(
        service,
        "read_status_source",
        lambda _profile: {"raw": "", "exists": False, "source_name": "x", "updated_at_ts": 0},
    )

    clients, source = service.collect_clients(tmp_path)

    assert source == "status_log"
    assert [client.common_name for client in clients] == ["Andrew_2", "test10"]
    assert clients[0].profile == "antizapret-udp"


def test_collect_clients_still_reads_the_legacy_snapshot_name(tmp_path, monkeypatch):
    _write(tmp_path, "vpn-udp-status.log")
    monkeypatch.setattr(
        service,
        "read_status_source",
        lambda _profile: {"raw": "", "exists": False, "source_name": "x", "updated_at_ts": 0},
    )

    clients, source = service.collect_clients(tmp_path)

    assert source == "status_log"
    assert [client.common_name for client in clients] == ["Andrew_2", "test10"]
