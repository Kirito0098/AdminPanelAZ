"""Ссылки на приложения в портале: вход валидируется на границе (Fider #41)."""

from app.services.portal_app_links import normalize_app_links


def test_normalize_keeps_known_cells_and_trims():
    links, warnings = normalize_app_links(
        {
            "openvpn": {"android": "  https://files.example.com/ovpn.apk  "},
            "amneziawg2": {"windows": "http://mirror.local/awg.exe"},
        }
    )

    assert links == {
        "openvpn": {"android": "https://files.example.com/ovpn.apk"},
        "amneziawg2": {"windows": "http://mirror.local/awg.exe"},
    }
    assert warnings == []


def test_normalize_drops_foreign_scheme_and_unknown_keys():
    links, warnings = normalize_app_links(
        {
            "openvpn": {"android": "ftp://files.example.com/app.apk", "symbian": "https://x"},
            "unknown": {"ios": "https://x"},
            "wireguard": {"ios": ""},
        }
    )

    assert links == {}
    assert any("http:// или https://" in w for w in warnings)
    assert any("symbian" in w for w in warnings)
    assert any("unknown" in w for w in warnings)


def test_normalize_ignores_broken_payload_shape():
    assert normalize_app_links(["https://x"]) == ({}, [])
    assert normalize_app_links({"openvpn": "https://x"})[0] == {}
