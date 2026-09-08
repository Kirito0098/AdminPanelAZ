"""Telegram file uploads use shared sync httpx client."""

from __future__ import annotations

import httpx
import pytest

from app.services import telegram_api as api
from app.services.telegram import send_tg_document_result, send_tg_photo


@pytest.fixture(autouse=True)
def _reset_sync_bot_api_client():
    api.reset_bot_api_sync_client_for_tests()
    yield
    api.reset_bot_api_sync_client_for_tests()


def test_two_calls_reuse_one_sync_client(monkeypatch):
    api.reset_bot_api_sync_client_for_tests()

    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"ok": True, "result": True})
    )
    builds = {"n": 0}

    def fake_build():
        builds["n"] += 1
        return httpx.Client(transport=transport, timeout=api._TIMEOUT)

    monkeypatch.setattr(api, "_build_bot_api_sync_client", fake_build)
    api.reset_bot_api_sync_client_for_tests()

    client1 = api._get_bot_api_sync_client()
    client2 = api._get_bot_api_sync_client()

    assert client1 is client2
    assert builds["n"] == 1


def test_send_tg_document_result_uses_httpx_client_not_urllib(tmp_path, monkeypatch):
    api.reset_bot_api_sync_client_for_tests()

    path = tmp_path / "client.ovpn"
    path.write_text("client\n", encoding="utf-8")

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "result": True})

    transport = httpx.MockTransport(handler)

    def fake_build():
        return httpx.Client(transport=transport, timeout=api._TIMEOUT)

    monkeypatch.setattr(api, "_build_bot_api_sync_client", fake_build)
    api.reset_bot_api_sync_client_for_tests()

    urllib_calls = {"n": 0}

    def fail_urlopen(*args, **kwargs):
        urllib_calls["n"] += 1
        raise AssertionError("urllib.request.urlopen should not be used")

    monkeypatch.setattr("app.services.telegram._outbound_enabled", lambda: True)
    monkeypatch.setattr("app.services.telegram.urllib.request.urlopen", fail_urlopen)

    ok, error = send_tg_document_result(
        "tok",
        "123",
        str(path),
        caption="hello",
        filename="client.ovpn",
        content_type="application/octet-stream",
        run_async=False,
    )

    assert ok is True
    assert error is None
    assert urllib_calls["n"] == 0
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url == "https://api.telegram.org/bottok/sendDocument"


def test_send_tg_document_result_surfaces_timeout_from_sync_client(tmp_path, monkeypatch):
    path = tmp_path / "client.ovpn"
    path.write_text("client\n", encoding="utf-8")

    class TimeoutClient:
        def post(self, *args, **kwargs):
            raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr("app.services.telegram._outbound_enabled", lambda: True)
    monkeypatch.setattr("app.services.telegram_api._get_bot_api_sync_client", lambda: TimeoutClient())

    ok, error = send_tg_document_result(
        "tok",
        "1",
        str(path),
        run_async=False,
        content_type="application/octet-stream",
    )

    assert ok is False
    assert error is not None
    assert "api.telegram.org" in error
    assert "истекло время ожидания" in error


def test_send_tg_photo_uses_httpx_client(tmp_path, monkeypatch):
    path = tmp_path / "report.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "result": True})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, timeout=api._TIMEOUT)

    monkeypatch.setattr("app.services.telegram._outbound_enabled", lambda: True)
    monkeypatch.setattr("app.services.telegram_api._get_bot_api_sync_client", lambda: client)
    monkeypatch.setattr(
        "app.services.telegram.urllib.request.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("urllib.request.urlopen should not be used")
        ),
    )

    ok = send_tg_photo("tok", "1", str(path), caption="plot", run_async=False)

    assert ok is True
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url == "https://api.telegram.org/bottok/sendPhoto"
