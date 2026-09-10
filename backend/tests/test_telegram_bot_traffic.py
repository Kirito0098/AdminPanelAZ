"""Unit tests for Telegram /traffic aggregation and period window."""

from types import SimpleNamespace

from app.services.telegram_bot_handlers import traffic as tg_traffic


def test_aggregate_clients_sums_traffic_period_only():
    rows = [
        SimpleNamespace(
            common_name="Alice",
            traffic_period=1_000,
            total_received=10,
            total_sent=20,
            is_active=True,
        ),
        SimpleNamespace(
            common_name="alice",
            traffic_period=2_000,
            total_received=5,
            total_sent=5,
            is_active=False,
        ),
    ]
    clients = tg_traffic._aggregate_clients(rows)
    assert len(clients) == 1
    assert clients[0]["name"] == "Alice"
    assert clients[0]["traffic_1d"] == 3_000
    assert clients[0]["total_bytes"] == 40
    assert clients[0]["is_active"] is True


def test_aggregate_clients_ignores_row_traffic_1d_attribute():
    row = SimpleNamespace(
        common_name="Bob",
        traffic_period=500,
        traffic_1d=9_999_999,
        total_received=0,
        total_sent=0,
        is_active=False,
    )
    clients = tg_traffic._aggregate_clients([row])
    assert clients[0]["traffic_1d"] == 500
