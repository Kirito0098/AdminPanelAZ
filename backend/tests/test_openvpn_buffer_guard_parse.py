from app.services.openvpn_buffer_guard_parse import parse_enobufs_line, summarize_enobufs


def test_parse_client_write_line():
    line = (
        "Beketova_Julija/udp4:109.124.227.213:59106 write UDPv4 []: "
        "No buffer space available (fd=6,code=105)"
    )
    hit = parse_enobufs_line(line)
    assert hit is not None
    assert hit.common_name == "Beketova_Julija"
    assert hit.real_address == "109.124.227.213:59106"


def test_parse_connection_attempt_line_no_cn():
    line = "Connection Attempt write UDPv4 []: No buffer space available (fd=6,code=105)"
    hit = parse_enobufs_line(line)
    assert hit is not None
    assert hit.common_name is None


def test_summarize_picks_top_cn():
    text = "\n".join(
        [
            "A/udp4:1.1.1.1:1 write UDPv4 []: No buffer space available (fd=6,code=105)",
            "B/udp4:2.2.2.2:2 write UDPv4 []: No buffer space available (fd=6,code=105)",
            "B/udp4:2.2.2.2:2 write UDPv4 []: No buffer space available (fd=6,code=105)",
            "ok line",
        ]
    )
    s = summarize_enobufs(text)
    assert s["total"] == 3
    assert s["top_cn"] == "B"
    assert s["top_real_address"] == "2.2.2.2:2"
