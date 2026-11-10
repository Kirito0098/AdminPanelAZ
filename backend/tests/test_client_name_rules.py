"""Правило имени VPN-клиента задано один раз для всех путей создания."""

from __future__ import annotations

from app.services import antizapret, awg2, client_names, profile_download_name


def test_creation_paths_share_one_regex() -> None:
    assert antizapret.CLIENT_NAME_RE is client_names.CLIENT_NAME_RE
    assert awg2.CLIENT_NAME_RE is client_names.CLIENT_NAME_RE
    assert profile_download_name.CLIENT_NAME_RE is client_names.CLIENT_NAME_RE


def test_client_name_regex_accepts_and_rejects() -> None:
    assert client_names.CLIENT_NAME_RE.match("client_01-a")
    assert client_names.CLIENT_NAME_RE.match("x" * 32)
    assert not client_names.CLIENT_NAME_RE.match("x" * 33)
    assert not client_names.CLIENT_NAME_RE.match("имя")
    assert not client_names.CLIENT_NAME_RE.match("")
