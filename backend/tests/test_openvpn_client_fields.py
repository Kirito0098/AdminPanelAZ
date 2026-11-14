"""OpenVPN status rows carry per-session identity and cipher (2.6+ / 2.7+)."""

from __future__ import annotations

from app.services.openvpn_management import openvpn_management_service as service

COMMA_RAW = (
    "CLIENT_LIST,Andrew_2,udp4:185.211.159.178:38683,172.28.0.2,,521369,6790348,"
    "2026-10-27 18:36:46,1793115406,UNDEF,1041,0,AES-128-GCM\n"
)
TAB_RAW = (
    "CLIENT_LIST\tAndrew_2\tudp4:185.211.159.178:38683\t172.28.0.2\t\t521369\t6790348\t"
    "2026-10-27 18:36:46\t1793115406\tUNDEF\t1041\t0\tAES-128-GCM\n"
)


def test_comma_status_rows_expose_client_id_peer_id_and_cipher():
    clients = service.parse_clients_from_status_raw(COMMA_RAW, "vpn-udp")

    assert len(clients) == 1
    client = clients[0]
    assert (client.common_name, client.client_id) == ("Andrew_2", "1041")
    assert client.peer_id == "0"
    assert client.cipher == "AES-128-GCM"
    assert (client.bytes_received, client.bytes_sent) == (521369, 6790348)


def test_tab_status_rows_expose_client_id_peer_id_and_cipher():
    clients = service.parse_clients_from_status_raw(TAB_RAW, "vpn-udp")

    assert len(clients) == 1
    client = clients[0]
    assert client.client_id == "1041"
    assert client.peer_id == "0"
    assert client.cipher == "AES-128-GCM"


def test_status_snapshot_file_exposes_client_id_peer_id_and_cipher(tmp_path):
    path = tmp_path / "status-vpn-udp.log"
    path.write_text(
        "TITLE,OpenVPN 2.7.6\n"
        "TIME,2026-10-27 18:42:21,1793115741\n"
        "HEADER,CLIENT_LIST,Common Name,Real Address,Virtual Address,Virtual IPv6 Address,"
        "Bytes Received,Bytes Sent,Connected Since,Connected Since (time_t),Username,Client ID,"
        "Peer ID,Data Channel Cipher\n"
        "CLIENT_LIST,Andrew_2,udp4:185.211.159.178:38683,172.28.0.2,,521369,6790348,"
        "2026-10-27 18:36:46,1793115406,UNDEF,1041,0,AES-128-GCM\n"
        "END\n",
        encoding="utf-8",
    )

    clients = service.parse_clients_from_status_log_file(path, "vpn-udp")

    assert clients[0].client_id == "1041"
    assert clients[0].peer_id == "0"
    assert clients[0].cipher == "AES-128-GCM"
