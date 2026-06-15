"""Tests for OpenVPN route budget metadata."""

from app.services.cidr.cidr_tasks import create_cidr_task, enable_memory_backend_for_tests, update_cidr_task
from app.services.cidr.route_budget import build_route_budget_payload


def test_route_budget_from_last_estimate():
    enable_memory_backend_for_tests(True)
    try:
        task_id = create_cidr_task("cidr_estimate_from_db", "estimate")
        update_cidr_task(
            task_id,
            status="completed",
            finished_at="2026-01-01T12:00:00+00:00",
            result={
                "success": True,
                "global_route_optimization": {
                    "limit": 100,
                    "compressed_total_cidr_count": 72,
                    "original_total_cidr_count": 120,
                    "strategy": "global_total_route_limit",
                },
            },
        )
        payload = build_route_budget_payload()
        assert payload["available"] is True
        assert payload["limit"] == 100
        assert payload["used"] == 72
        assert payload["remaining"] == 28
    finally:
        enable_memory_backend_for_tests(False)
