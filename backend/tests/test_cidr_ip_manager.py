"""Provider enable/disable/sync between controller list files and AntiZapret config.

``IpManager`` is the file boundary: node-side ``AP-*-include-ips.txt`` files must be
created from the controller list, legacy names removed, and unknown names rejected
before any path is built.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services.cidr.ip_manager import IpManager, masked_include_name, provider_prefix
from app.services.cidr.service import CidrRoutingService

PROVIDER_A = "cloudflare-ips.txt"
PROVIDER_B = "google-ips.txt"


@pytest.fixture
def manager(tmp_path):
    list_dir = tmp_path / "list"
    config_dir = tmp_path / "antizapret" / "config"
    list_dir.mkdir()
    config_dir.mkdir(parents=True)
    return IpManager(list_dir, config_dir)


@pytest.fixture
def service(tmp_path):
    return CidrRoutingService(antizapret_path=tmp_path / "antizapret", list_dir=tmp_path / "list")


def _write(path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_provider_prefix_and_masked_name():
    assert provider_prefix(PROVIDER_A) == "cloudflare"
    assert provider_prefix("custom.txt") == "custom"
    assert masked_include_name(PROVIDER_A) == "AP-cloudflare-include-ips.txt"


def test_enable_file_creates_ap_include_from_list(manager):
    _write(manager.list_dir / PROVIDER_A, "1.1.1.0/24\n# comment\n2.2.2.0/24\n")

    count = manager.enable_file(PROVIDER_A)

    target = manager.config_dir / "AP-cloudflare-include-ips.txt"
    assert count == 2
    assert target.read_text(encoding="utf-8") == "1.1.1.0/24\n# comment\n2.2.2.0/24\n"
    assert manager.get_file_states()[PROVIDER_A] is True


def test_enable_file_drops_stale_legacy_include(manager):
    _write(manager.list_dir / PROVIDER_A, "1.1.1.0/24\n")
    legacy = _write(manager.config_dir / "cloudflare-include-ips.txt", "9.9.9.0/24\n")

    manager.enable_file(PROVIDER_A)

    assert not legacy.exists()
    assert (manager.config_dir / "AP-cloudflare-include-ips.txt").exists()


def test_enable_file_without_list_source_raises(manager):
    with pytest.raises(FileNotFoundError):
        manager.enable_file(PROVIDER_A)

    assert list(manager.config_dir.iterdir()) == []


def test_disable_file_removes_ap_and_legacy(manager):
    ap = _write(manager.config_dir / "AP-cloudflare-include-ips.txt", "1.1.1.0/24\n2.2.2.0/24\n")
    legacy = _write(manager.config_dir / "cloudflare-include-ips.txt", "9.9.9.0/24\n")

    removed = manager.disable_file(PROVIDER_A)

    assert removed == 2
    assert not ap.exists()
    assert not legacy.exists()
    assert manager.get_file_states()[PROVIDER_A] is False


def test_disable_file_counts_legacy_when_ap_missing(manager):
    legacy = _write(manager.config_dir / "cloudflare-include-ips.txt", "9.9.9.0/24\n")

    assert manager.disable_file(PROVIDER_A) == 1
    assert not legacy.exists()


def test_disable_file_is_a_noop_when_nothing_enabled(manager):
    assert manager.disable_file(PROVIDER_A) == 0


def test_sync_updates_only_changed_files(manager):
    _write(manager.list_dir / PROVIDER_A, "1.1.1.0/24\n")
    _write(manager.list_dir / PROVIDER_B, "8.8.8.0/24\n")
    manager.enable_file(PROVIDER_A)
    manager.enable_file(PROVIDER_B)
    _write(manager.list_dir / PROVIDER_A, "1.1.1.0/24\n2.2.2.0/24\n")
    _write(manager.list_dir / PROVIDER_B, "8.8.8.0/24\n")

    result = manager.sync_enabled_from_list()

    assert result == {"synced_files": 2, "updated_files": 1, "missing_sources": []}
    assert (manager.config_dir / "AP-cloudflare-include-ips.txt").read_text(encoding="utf-8") == (
        "1.1.1.0/24\n2.2.2.0/24\n"
    )


def test_sync_reports_missing_sources_and_skips_disabled(manager):
    ap = _write(manager.config_dir / "AP-cloudflare-include-ips.txt", "1.1.1.0/24\n")
    _write(manager.list_dir / PROVIDER_B, "8.8.8.0/24\n")

    result = manager.sync_enabled_from_list()

    assert result["synced_files"] == 0
    assert result["updated_files"] == 0
    assert result["missing_sources"] == [PROVIDER_A]
    assert ap.exists()


def test_sync_removes_legacy_include_for_enabled_provider(manager):
    _write(manager.list_dir / PROVIDER_A, "1.1.1.0/24\n")
    legacy = _write(manager.config_dir / "cloudflare-include-ips.txt", "1.1.1.0/24\n")

    result = manager.sync_enabled_from_list()

    assert result["synced_files"] == 1
    assert not legacy.exists()
    assert (manager.config_dir / "AP-cloudflare-include-ips.txt").exists()


def test_restore_source_from_config_restores_missing_list(manager):
    _write(manager.config_dir / "AP-cloudflare-include-ips.txt", "1.1.1.0/24\n")
    _write(manager.list_dir / PROVIDER_B, "8.8.8.0/24\n")

    restored = manager.restore_source_from_config()

    assert restored == {PROVIDER_A: True}
    assert (manager.list_dir / PROVIDER_A).read_text(encoding="utf-8") == "1.1.1.0/24\n"
    assert (manager.list_dir / PROVIDER_B).read_text(encoding="utf-8") == "8.8.8.0/24\n"


def test_restore_source_from_config_is_a_noop_when_list_exists(manager):
    _write(manager.list_dir / PROVIDER_A, "3.3.3.0/24\n")
    _write(manager.config_dir / "AP-cloudflare-include-ips.txt", "1.1.1.0/24\n")

    assert manager.restore_source_from_config() == {}
    assert (manager.list_dir / PROVIDER_A).read_text(encoding="utf-8") == "3.3.3.0/24\n"


@pytest.mark.parametrize("name", ["../../etc/passwd", "/etc/passwd", "../cloudflare-ips.txt", "unknown-ips.txt"])
def test_service_rejects_unknown_and_traversal_provider_names(service, name):
    for call in (
        lambda: service.get_provider_content(name),
        lambda: service.save_provider_content(name, "1.1.1.0/24\n"),
        lambda: service.set_provider_enabled(name, True),
    ):
        with pytest.raises(HTTPException) as excinfo:
            call()
        assert excinfo.value.status_code == 400

    assert not (service.list_dir / "passwd").exists()


def test_service_returns_404_when_list_file_is_missing(service):
    with pytest.raises(HTTPException) as excinfo:
        service.set_provider_enabled(PROVIDER_A, True)

    assert excinfo.value.status_code == 404
    assert PROVIDER_A in str(excinfo.value.detail)


def test_service_sync_providers_reports_restore_and_sync(service):
    _write(service.config_dir / "AP-cloudflare-include-ips.txt", "1.1.1.0/24\n")

    result = service.sync_providers()

    assert result["restored"] == {PROVIDER_A: True}
    assert result["sync"]["synced_files"] == 1
    assert result["sync"]["updated_files"] == 0
    assert result["sync"]["missing_sources"] == []
