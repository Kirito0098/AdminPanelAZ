"""Smoke tests for AdminPanelAZ backend."""

import pytest


def test_import_app():
    from app.main import app

    assert app.title


def test_health_route_exists():
    from app.main import app

    paths = [getattr(r, "path", "") for r in app.routes]
    assert "/api/health" in paths
