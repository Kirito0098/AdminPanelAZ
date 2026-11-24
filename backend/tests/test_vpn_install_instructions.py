"""Ссылка «Скачать» в инструкции бота (Fider #41, продолжение)."""

import html

from app.services.vpn_install_instructions import build_install_instruction_message


def test_download_line_goes_right_under_the_profile_line():
    message = build_install_instruction_message(
        protocol="openvpn",
        platform="android",
        client_name="ivan",
        app_url="https://files.example.com/app.apk?a=1&b=2",
    )

    assert message is not None
    lines = message.splitlines()
    assert lines[0].startswith("<b>")
    assert lines[1] == "Профиль: <code>ivan</code>"
    assert lines[2] == f"Скачать: {html.escape('https://files.example.com/app.apk?a=1&b=2')}"
    assert lines[3] == ""


def test_without_link_message_is_unchanged():
    message = build_install_instruction_message(
        protocol="wireguard",
        platform="ios",
        client_name="ivan",
    )

    assert message is not None
    assert "Скачать:" not in message
