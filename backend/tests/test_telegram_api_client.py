"""Shared httpx AsyncClient + call_bot_api_result."""

from __future__ import annotations

import asyncio

import httpx

from app.services import telegram_api as api


def test_two_calls_reuse_one_async_client(monkeypatch):
    api.reset_bot_api_client_for_tests()

    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"ok": True, "result": {"x": 1}})
    )
    builds = {"n": 0}

    def fake_build():
        builds["n"] += 1
        return httpx.AsyncClient(transport=transport, timeout=api._TIMEOUT)

    monkeypatch.setattr(api, "_build_bot_api_client", fake_build)
    api.reset_bot_api_client_for_tests()

    async def run():
        r1 = await api.call_bot_api_result("tok", "getMe")
        r2 = await api.call_bot_api_result("tok", "getMe")
        return r1, r2

    r1, r2 = asyncio.run(run())
    assert r1.ok and r2.ok
    assert builds["n"] == 1


def test_call_bot_api_result_maps_ok_false(monkeypatch):
    api.reset_bot_api_client_for_tests()

    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200,
            json={"ok": False, "description": "Bad Request: invalid token"},
        )
    )

    def fake_build():
        return httpx.AsyncClient(transport=transport, timeout=api._TIMEOUT)

    monkeypatch.setattr(api, "_build_bot_api_client", fake_build)
    api.reset_bot_api_client_for_tests()

    async def run():
        return await api.call_bot_api_result("tok", "getMe")

    result = asyncio.run(run())
    assert result.ok is False
    assert result.result is None
    assert result.error
    assert "invalid token" in result.error.lower() or "Bad Request" in result.error


def test_call_bot_api_result_empty_token():
    api.reset_bot_api_client_for_tests()

    async def run():
        return await api.call_bot_api_result("", "getMe")

    result = asyncio.run(run())
    assert result.ok is False
    assert result.error == "Токен бота не задан"


def test_call_bot_api_still_returns_none_on_failure(monkeypatch):
    api.reset_bot_api_client_for_tests()

    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200,
            json={"ok": False, "description": "Unauthorized"},
        )
    )

    def fake_build():
        return httpx.AsyncClient(transport=transport, timeout=api._TIMEOUT)

    monkeypatch.setattr(api, "_build_bot_api_client", fake_build)
    api.reset_bot_api_client_for_tests()

    async def run():
        return await api.call_bot_api("tok", "getMe")

    assert asyncio.run(run()) is None


def test_call_bot_api_still_returns_result_on_success(monkeypatch):
    api.reset_bot_api_client_for_tests()

    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"ok": True, "result": {"id": 42}})
    )

    def fake_build():
        return httpx.AsyncClient(transport=transport, timeout=api._TIMEOUT)

    monkeypatch.setattr(api, "_build_bot_api_client", fake_build)
    api.reset_bot_api_client_for_tests()

    async def run():
        return await api.call_bot_api("tok", "getMe")

    assert asyncio.run(run()) == {"id": 42}
