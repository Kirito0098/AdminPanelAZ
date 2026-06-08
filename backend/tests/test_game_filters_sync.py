"""Tests for game filter sync via pipeline (include + exclude AZ-Game-* files)."""

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.services.cidr import cidr_list_updater
from app.services.cidr.game_filter_sync import run_sync_game_routes_filter
from tests.conftest import run_async


@pytest.fixture()
def game_config_dir(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir


class TestRunSyncGameRoutesFilter:
    def test_exclude_writes_az_exclude_files(self, game_config_dir):
        with patch(
            "app.services.cidr.pipeline.games._collect_item_cidrs",
            side_effect=lambda item, **kwargs: (["203.0.113.10/32"], True, []),
        ), patch(
            "app.services.cidr.pipeline.games._build_overlap_index",
            return_value=([], []),
        ):
            result = run_sync_game_routes_filter(
                game_config_dir,
                include_game_keys=[],
                exclude_game_keys=["lol"],
                include_game_domains=True,
            )

        assert result["success"] is True
        assert result["exclude_changed"] is True
        assert result["exclude_count"] == 1

        exclude_hosts = (game_config_dir / "AZ-Game-exclude-hosts.txt").read_text(encoding="utf-8")
        exclude_ips = (game_config_dir / "AZ-Game-exclude-ips.txt").read_text(encoding="utf-8")

        assert cidr_list_updater.GAME_FILTER_EXCLUDE_BLOCK_START in exclude_hosts
        assert "riotgames.com" in exclude_hosts
        assert cidr_list_updater.GAME_FILTER_EXCLUDE_IP_BLOCK_START in exclude_ips
        assert "203.0.113.10/32" in exclude_ips

    def test_include_and_exclude_both_sync(self, game_config_dir):
        with patch(
            "app.services.cidr.pipeline.games._collect_item_cidrs",
            side_effect=lambda item, **kwargs: (["203.0.113.10/32"], True, []),
        ), patch(
            "app.services.cidr.pipeline.games._build_overlap_index",
            return_value=([], []),
        ):
            result = run_sync_game_routes_filter(
                game_config_dir,
                include_game_keys=["steam"],
                exclude_game_keys=["lol"],
                include_game_domains=True,
            )

        assert result["success"] is True
        assert result["include_count"] >= 1
        assert result["exclude_count"] == 1
        assert (game_config_dir / "AZ-Game-include-hosts.txt").exists()
        assert (game_config_dir / "AZ-Game-exclude-hosts.txt").exists()

    def test_clear_exclude_on_empty_selection(self, game_config_dir):
        managed_block = (
            f"{cidr_list_updater.GAME_FILTER_EXCLUDE_BLOCK_START}\n"
            "# games: lol\n"
            "riotgames.com\n"
            f"{cidr_list_updater.GAME_FILTER_EXCLUDE_BLOCK_END}\n"
        )
        exclude_hosts_path = game_config_dir / "AZ-Game-exclude-hosts.txt"
        exclude_hosts_path.write_text("keep.local\n\n" + managed_block, encoding="utf-8")

        result = run_sync_game_routes_filter(
            game_config_dir,
            include_game_keys=[],
            exclude_game_keys=[],
            include_game_domains=True,
        )

        assert result["success"] is True
        content = exclude_hosts_path.read_text(encoding="utf-8")
        assert "keep.local" in content
        assert cidr_list_updater.GAME_FILTER_EXCLUDE_BLOCK_START not in content


def test_sync_router_calls_adapter_pipeline(api_test_env, monkeypatch):
    adapter = api_test_env["mock_adapter"]
    adapter.sync_game_routes_filter.return_value = {
        "success": True,
        "changed": True,
        "message": "Игровые маршруты синхронизированы",
        "include_changed": False,
        "exclude_changed": True,
        "hosts_changed": True,
        "ips_changed": True,
        "include_count": 0,
        "exclude_count": 1,
    }
    monkeypatch.setattr(
        "app.routers.game_filters.get_active_adapter",
        lambda db: adapter,
    )
    transport = ASGITransport(app=api_test_env["app"])

    async def _call():
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/api/routing/game-filters/sync",
                headers=api_test_env["admin_headers"],
                json={"modes": {"lol": "exclude"}, "include_domains": True, "run_doall": True},
            )

    response = run_async(_call())
    assert response.status_code == 200
    adapter.sync_game_routes_filter.assert_called_once_with(
        include_game_keys=[],
        exclude_game_keys=["lol"],
        include_game_domains=True,
    )
    adapter.apply_config_changes.assert_called_once()


def test_sync_router_returns_error_when_pipeline_fails(api_test_env, monkeypatch):
    adapter = api_test_env["mock_adapter"]
    adapter.sync_game_routes_filter.return_value = {
        "success": False,
        "message": "Не удалось синхронизировать AZ-Game-exclude-ips",
    }
    monkeypatch.setattr(
        "app.routers.game_filters.get_active_adapter",
        lambda db: adapter,
    )
    transport = ASGITransport(app=api_test_env["app"])

    async def _call():
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/api/routing/game-filters/sync",
                headers=api_test_env["admin_headers"],
                json={"modes": {"lol": "exclude"}},
            )

    response = run_async(_call())
    assert response.status_code == 400
