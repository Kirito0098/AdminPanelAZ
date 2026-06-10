"""Unit tests for CIDR pipeline Telegram notifications."""

from unittest.mock import MagicMock, patch

from app.services.cidr.cidr_notify import (
    maybe_notify_ingest_partial,
    maybe_notify_deploy_failed,
)


def test_maybe_notify_ingest_partial_sends_on_partial():
    db = MagicMock()
    result = {
        "status": "partial",
        "providers_updated": 3,
        "providers_failed": 1,
        "per_provider": {"aws.txt": {"status": "partial"}},
        "dry_run": False,
    }
    with patch("app.services.cidr.cidr_notify.admin_notify_service") as svc:
        maybe_notify_ingest_partial(db, result, triggered_by="manual:admin")
        svc.send_cidr_ingest_partial.assert_called_once()
        kwargs = svc.send_cidr_ingest_partial.call_args.kwargs
        assert kwargs["actor_username"] == "manual:admin"
        assert "aws.txt" in kwargs["details"]


def test_maybe_notify_ingest_partial_skips_ok():
    db = MagicMock()
    with patch("app.services.cidr.cidr_notify.admin_notify_service") as svc:
        maybe_notify_ingest_partial(db, {"status": "ok", "dry_run": False})
        svc.send_cidr_ingest_partial.assert_not_called()


def test_maybe_notify_ingest_partial_skips_dry_run():
    db = MagicMock()
    with patch("app.services.cidr.cidr_notify.admin_notify_service") as svc:
        maybe_notify_ingest_partial(db, {"status": "partial", "dry_run": True})
        svc.send_cidr_ingest_partial.assert_not_called()


def test_maybe_notify_deploy_failed_skips_success():
    db = MagicMock()
    with patch("app.services.cidr.cidr_notify.admin_notify_service") as svc:
        maybe_notify_deploy_failed(db, {"success": True})
        svc.send_cidr_deploy_failed.assert_not_called()
