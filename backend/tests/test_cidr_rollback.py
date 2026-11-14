"""Rollback from runtime_backups: restore, refusal, traversal and retention.

``backup_stamp`` and ``selected_files`` come straight from the HTTP payload, so the
rollback is a trust boundary: a path outside the backup root must never be read and
a failed rollback must leave the current list files byte-for-byte intact.
"""

from __future__ import annotations

import os

import pytest

from app.services.cidr.pipeline import constants, file_pipeline

PROVIDER_A = "cloudflare-ips.txt"
PROVIDER_B = "google-ips.txt"


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    list_dir = tmp_path / "list"
    backup_root = tmp_path / "runtime_backups"
    list_dir.mkdir()
    backup_root.mkdir()
    monkeypatch.setattr(constants, "LIST_DIR", str(list_dir))
    monkeypatch.setattr(constants, "RUNTIME_BACKUP_ROOT", str(backup_root))
    return list_dir, backup_root


def _make_stamp(backup_root, stamp: str, files: dict[str, str]):
    path = backup_root / stamp
    path.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (path / name).write_text(content, encoding="utf-8")
    return path


def test_rollback_restores_list_files_from_stamp(dirs):
    list_dir, backup_root = dirs
    _make_stamp(backup_root, "20260101T000000Z", {PROVIDER_A: "1.1.1.0/24\n"})
    (list_dir / PROVIDER_A).write_text("9.9.9.0/24\n", encoding="utf-8")

    result = file_pipeline.rollback_from_runtime_backup("20260101T000000Z")

    assert result["success"] is True
    assert result["restored"] == [PROVIDER_A]
    assert result["missing"] == []
    assert (list_dir / PROVIDER_A).read_text(encoding="utf-8") == "1.1.1.0/24\n"


def test_selected_files_restore_only_the_requested_provider(dirs):
    list_dir, backup_root = dirs
    _make_stamp(
        backup_root,
        "20260102T000000Z",
        {PROVIDER_A: "1.1.1.0/24\n", PROVIDER_B: "8.8.8.0/24\n"},
    )
    (list_dir / PROVIDER_A).write_text("new-a\n", encoding="utf-8")
    (list_dir / PROVIDER_B).write_text("new-b\n", encoding="utf-8")

    result = file_pipeline.rollback_from_runtime_backup(
        "20260102T000000Z",
        selected_files=[PROVIDER_B],
    )

    assert result["restored"] == [PROVIDER_B]
    assert (list_dir / PROVIDER_B).read_text(encoding="utf-8") == "8.8.8.0/24\n"
    assert (list_dir / PROVIDER_A).read_text(encoding="utf-8") == "new-a\n"


def test_missing_stamp_reports_error_and_keeps_current_files(dirs):
    list_dir, _ = dirs
    (list_dir / PROVIDER_A).write_text("9.9.9.0/24\n", encoding="utf-8")

    result = file_pipeline.rollback_from_runtime_backup("20250101T000000Z")

    assert result["success"] is False
    assert "не найдена" in result["message"]
    assert result["restored"] == []
    assert (list_dir / PROVIDER_A).read_text(encoding="utf-8") == "9.9.9.0/24\n"


@pytest.mark.parametrize("stamp", ["", "   ", None])
def test_empty_stamp_is_rejected(dirs, stamp):
    list_dir, _ = dirs
    (list_dir / PROVIDER_A).write_text("9.9.9.0/24\n", encoding="utf-8")

    result = file_pipeline.rollback_from_runtime_backup(stamp)

    assert result["success"] is False
    assert "Не указан stamp" in result["message"]
    assert (list_dir / PROVIDER_A).read_text(encoding="utf-8") == "9.9.9.0/24\n"


def test_stamp_traversal_cannot_read_outside_backup_root(dirs, tmp_path):
    list_dir, backup_root = dirs
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / PROVIDER_A).write_text("6.6.6.0/24\n", encoding="utf-8")
    (list_dir / PROVIDER_A).write_text("9.9.9.0/24\n", encoding="utf-8")

    result = file_pipeline.rollback_from_runtime_backup("../outside")

    assert result["success"] is False
    assert result["restored"] == []
    assert (list_dir / PROVIDER_A).read_text(encoding="utf-8") == "9.9.9.0/24\n"


@pytest.mark.parametrize(
    "name",
    ["../../etc/passwd", "/etc/passwd", "foo/../../bar-ips.txt", "../cloudflare-ips.txt"],
)
def test_selected_files_traversal_is_filtered_out(dirs, name):
    list_dir, backup_root = dirs
    _make_stamp(backup_root, "20260103T000000Z", {PROVIDER_A: "1.1.1.0/24\n"})
    (list_dir / PROVIDER_A).write_text("9.9.9.0/24\n", encoding="utf-8")

    result = file_pipeline.rollback_from_runtime_backup(
        "20260103T000000Z",
        selected_files=[name],
    )

    # Unknown names never reach the filesystem; the stamp's own provider is restored.
    assert result["restored"] == [PROVIDER_A]
    assert not (list_dir / "passwd").exists()
    assert not (list_dir / "bar-ips.txt").exists()
    assert os.listdir(list_dir) == [PROVIDER_A]


def test_selected_files_traversal_is_skipped_next_to_a_valid_name(dirs):
    list_dir, backup_root = dirs
    _make_stamp(backup_root, "20260104T000000Z", {PROVIDER_A: "1.1.1.0/24\n"})
    (list_dir / PROVIDER_A).write_text("9.9.9.0/24\n", encoding="utf-8")

    result = file_pipeline.rollback_from_runtime_backup(
        "20260104T000000Z",
        selected_files=["../../etc/passwd", PROVIDER_A],
    )

    assert result["restored"] == [PROVIDER_A]
    assert os.listdir(list_dir) == [PROVIDER_A]


def test_stamp_without_provider_files_reports_error(dirs):
    list_dir, backup_root = dirs
    _make_stamp(backup_root, "20260105T000000Z", {"notes.txt": "hello\n"})
    (list_dir / PROVIDER_A).write_text("9.9.9.0/24\n", encoding="utf-8")

    result = file_pipeline.rollback_from_runtime_backup("20260105T000000Z")

    assert result["success"] is False
    assert "нет CIDR-файлов" in result["message"]
    assert (list_dir / PROVIDER_A).read_text(encoding="utf-8") == "9.9.9.0/24\n"


def test_list_runtime_backups_skips_empty_stamps_and_sorts_newest_first(dirs):
    _, backup_root = dirs
    old = _make_stamp(backup_root, "20260101T000000Z", {PROVIDER_A: "1.1.1.0/24\n"})
    fresh = _make_stamp(
        backup_root,
        "20260102T000000Z",
        {PROVIDER_A: "1.1.1.0/24\n", PROVIDER_B: "8.8.8.0/24\n"},
    )
    (backup_root / "20260103T000000Z").mkdir()
    (backup_root / "20260103T000000Z" / "notes.txt").write_text("x\n", encoding="utf-8")
    os.utime(old, (1_767_225_600, 1_767_225_600))
    os.utime(fresh, (1_767_312_000, 1_767_312_000))

    backups = file_pipeline.list_runtime_backups()

    assert [item["stamp"] for item in backups] == ["20260102T000000Z", "20260101T000000Z"]
    assert backups[0]["files"] == [PROVIDER_A, PROVIDER_B]
    assert backups[0]["file_count"] == 2


def test_prune_removes_stamps_older_than_retention(dirs):
    _, backup_root = dirs
    stale = _make_stamp(backup_root, "20260101T000000Z", {PROVIDER_A: "1.1.1.0/24\n"})
    fresh = _make_stamp(backup_root, "20260102T000000Z", {PROVIDER_A: "1.1.1.0/24\n"})
    now_ts = 1_767_312_000.0
    os.utime(stale, (now_ts - 13 * 3600, now_ts - 13 * 3600))
    os.utime(fresh, (now_ts - 3600, now_ts - 3600))

    removed = file_pipeline._prune_runtime_backups(now_ts=now_ts, retention_seconds=12 * 3600)

    assert removed == ["20260101T000000Z"]
    assert not stale.exists()
    assert fresh.exists()


def test_prune_is_disabled_by_zero_retention(dirs):
    _, backup_root = dirs
    old = _make_stamp(backup_root, "20260101T000000Z", {PROVIDER_A: "1.1.1.0/24\n"})
    os.utime(old, (1, 1))

    assert file_pipeline._prune_runtime_backups(now_ts=1_767_312_000.0, retention_seconds=0) == []
    assert old.exists()


def test_prune_keeps_plain_files_in_backup_root(dirs):
    _, backup_root = dirs
    marker = backup_root / "README"
    marker.write_text("not a stamp\n", encoding="utf-8")
    os.utime(marker, (1, 1))

    removed = file_pipeline._prune_runtime_backups(now_ts=1_767_312_000.0, retention_seconds=60)

    assert removed == []
    assert marker.exists()
