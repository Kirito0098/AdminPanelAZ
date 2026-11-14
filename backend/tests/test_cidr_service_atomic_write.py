"""Atomic writes, backups and content validation for CIDR list files."""

from __future__ import annotations

import errno
import os

import pytest
from fastapi import HTTPException

from app.services.cidr.service import CidrRoutingService


@pytest.fixture
def service(tmp_path):
    return CidrRoutingService(antizapret_path=tmp_path, list_dir=tmp_path / "list")


def _leftover_temps(directory):
    return [path.name for path in directory.iterdir() if path.name.endswith(".tmp")]


def test_save_provider_content_writes_and_keeps_backup(service):
    provider = "custom-ips.txt"
    path = service.list_dir / provider
    path.write_text("10.0.0.0/8\n", encoding="utf-8")

    result = service.save_provider_content(provider, "192.168.0.0/16\n!192.168.1.0/24\n")

    assert result == {"filename": provider, "cidr_count": 2}
    assert path.read_text(encoding="utf-8") == "192.168.0.0/16\n!192.168.1.0/24\n"
    assert path.with_name(provider + ".bak").read_text(encoding="utf-8") == "10.0.0.0/8\n"
    assert _leftover_temps(service.list_dir) == []


def test_save_provider_content_skips_backup_for_identical_content(service):
    provider = "custom-ips.txt"
    path = service.list_dir / provider
    path.write_text("10.0.0.0/8\n", encoding="utf-8")

    service.save_provider_content(provider, "10.0.0.0/8\n")

    assert not path.with_name(provider + ".bak").exists()


def test_save_provider_content_preserves_existing_mode(service):
    provider = "custom-ips.txt"
    path = service.list_dir / provider
    path.write_text("10.0.0.0/8\n", encoding="utf-8")
    path.chmod(0o640)

    service.save_provider_content(provider, "10.1.0.0/16\n")

    assert path.stat().st_mode & 0o777 == 0o640


def test_failed_replace_keeps_original_and_drops_temp(service, monkeypatch):
    provider = "custom-ips.txt"
    path = service.list_dir / provider
    path.write_text("10.0.0.0/8\n", encoding="utf-8")
    real_replace = os.replace

    def replace_then_fail_on_target(src, dst):
        if str(dst).endswith(".bak"):
            return real_replace(src, dst)
        raise OSError(errno.EIO, "simulated disk error")

    monkeypatch.setattr("app.services.cidr.service.os.replace", replace_then_fail_on_target)

    with pytest.raises(OSError):
        service.save_provider_content(provider, "192.168.0.0/16\n")

    assert path.read_text(encoding="utf-8") == "10.0.0.0/8\n"
    assert path.with_name(provider + ".bak").read_text(encoding="utf-8") == "10.0.0.0/8\n"
    assert _leftover_temps(service.list_dir) == []


def test_failed_write_route_file_leaves_no_file_and_no_temp(service, monkeypatch):
    def fail_replace(src, dst):
        raise OSError(errno.EIO, "simulated disk error")

    monkeypatch.setattr("app.services.cidr.service.os.replace", fail_replace)

    with pytest.raises(OSError):
        service.write_route_file("include_ips", "10.0.0.0/8\n")

    assert not (service.config_dir / "include-ips.txt").exists()
    assert _leftover_temps(service.config_dir) == []


@pytest.mark.parametrize(
    "content",
    [
        "10.0.0.0/8\n",
        "!10.0.0.0/8\n",
        "AS12345\n",
        "!AS12345\n",
        "as12345\n",
        "10.0.0.1/32\n10.0.0.1/8\n",
        "# Auto-generated CIDR list for custom-ips.txt\n# Source: db:ripe-as20940-geo\n\n10.0.0.0/8\n\n",
        "  # indented comment\n\n",
        "",
    ],
)
def test_validate_accepts_supported_lines(service, content):
    result = service.save_provider_content("custom-ips.txt", content)
    assert (service.list_dir / "custom-ips.txt").read_text(encoding="utf-8") == content
    assert result["cidr_count"] == len(
        [line for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]
    )


@pytest.mark.parametrize(
    "content",
    [
        "не-cidr\n",
        "10.0.0.999/8\n",
        "10.0.0.0/33\n",
        "AS\n",
        "AS12345/24\n",
        "!\n",
        "10.0.0.0/8 junk\n",
    ],
)
def test_validate_rejects_broken_lines(service, content):
    with pytest.raises(HTTPException) as exc:
        service.save_provider_content("custom-ips.txt", content)

    assert exc.value.status_code == 400
    assert "некорректная строка 1" in exc.value.detail
    assert not (service.list_dir / "custom-ips.txt").exists()


def test_validate_reports_first_ten_errors(service):
    content = "".join(f"bad-{i}\n" for i in range(15))

    with pytest.raises(HTTPException) as exc:
        service.save_provider_content("custom-ips.txt", content)

    assert exc.value.status_code == 400
    assert exc.value.detail.count("некорректная строка") == 10
    assert "bad-9" in exc.value.detail


def test_validate_rejects_oversized_content(service):
    content = "x" * (8 * 1024 * 1024 + 1)

    with pytest.raises(HTTPException) as exc:
        service.save_provider_content("custom-ips.txt", content)

    assert exc.value.status_code == 400
    assert "Слишком большой файл" in exc.value.detail
    assert not (service.list_dir / "custom-ips.txt").exists()


def test_write_route_file_validates_and_writes(service):
    path = service.config_dir / "include-ips.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# old\n10.0.0.0/8\n", encoding="utf-8")

    result = service.write_route_file("include_ips", "# new\n192.168.0.0/16\n")

    assert result["line_count"] == 1
    assert path.read_text(encoding="utf-8") == "# new\n192.168.0.0/16\n"
    assert path.with_name("include-ips.txt.bak").read_text(encoding="utf-8") == "# old\n10.0.0.0/8\n"

    with pytest.raises(HTTPException) as exc:
        service.write_route_file("include_ips", "не-cidr\n")
    assert exc.value.status_code == 400
    assert path.read_text(encoding="utf-8") == "# new\n192.168.0.0/16\n"
