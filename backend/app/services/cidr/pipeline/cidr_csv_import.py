"""CSV staging and native SQLite bulk import for provider CIDR ingest."""

from __future__ import annotations

import csv
import logging
import os
import re
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.cidr_database import resolve_cidr_db_path
from app.database import apply_sqlite_connection_pragmas
from app.config import get_settings
from app.paths import BACKEND_ROOT, resolve_backend_path

logger = logging.getLogger(__name__)

INSERT_SQL = """
INSERT INTO provider_cidr (provider_key, cidr, region_scope, country_codes, refreshed_at)
VALUES (?, ?, ?, ?, ?)
"""

ProgressCallback = Callable[[int, str], None] | None


def get_sqlite_db_path() -> Path:
    return resolve_cidr_db_path()


def get_staging_dir() -> Path:
    settings = get_settings()
    staging = resolve_backend_path(settings.cidr_db_staging_dir)
    staging.mkdir(parents=True, exist_ok=True)
    return staging


def _safe_staging_name(provider_key: str) -> str:
    safe = re.sub(r"[^\w.\-]+", "_", str(provider_key or "").strip())
    return safe or "provider"


def staging_csv_path(provider_key: str) -> Path:
    return get_staging_dir() / f"{_safe_staging_name(provider_key)}.csv"


def staging_csv_tmp_path(provider_key: str) -> Path:
    return get_staging_dir() / f"{_safe_staging_name(provider_key)}.csv.tmp"


def _dedupe_cidr_items(cidr_items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for item in cidr_items:
        cidr = str(item.get("cidr") or "").strip()
        if cidr and cidr not in seen:
            seen[cidr] = item
    return seen


def write_provider_cidr_csv(
    provider_key: str,
    cidr_items: list[dict[str, Any]],
    *,
    refreshed_at: datetime | None = None,
) -> tuple[Path, int]:
    """Write deduplicated CIDR rows to staging CSV atomically. Returns (path, row_count)."""
    when = refreshed_at or datetime.now(timezone.utc)
    refreshed_iso = when.isoformat()
    seen = _dedupe_cidr_items(cidr_items)
    tmp_path = staging_csv_tmp_path(provider_key)
    final_path = staging_csv_path(provider_key)
    tmp_path.parent.mkdir(parents=True, exist_ok=True)

    with tmp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        for item in seen.values():
            countries = item.get("countries")
            country_codes = ",".join(countries) if countries else ""
            region = item.get("region")
            writer.writerow([
                provider_key,
                item["cidr"],
                region if region else "",
                country_codes,
                refreshed_iso,
            ])

    os.replace(tmp_path, final_path)
    return final_path, len(seen)


def _sqlite_connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    apply_sqlite_connection_pragmas(conn.cursor())
    return conn


def _commit_with_retry(conn: sqlite3.Connection) -> None:
    for attempt in range(5):
        try:
            conn.commit()
            return
        except sqlite3.OperationalError as exc:
            if "database is locked" not in str(exc).lower() or attempt == 4:
                raise
            time.sleep(0.1 * (attempt + 1))


def import_provider_cidr_csv(
    db_path: Path,
    provider_key: str,
    csv_path: Path,
    *,
    total_rows: int | None = None,
    progress_callback: ProgressCallback = None,
    keep_csv: bool | None = None,
) -> int:
    """Replace provider CIDR rows via native SQLite bulk import from CSV."""
    settings = get_settings()
    batch_size = max(1, int(settings.cidr_db_csv_import_batch))
    chunk_rows = max(0, int(settings.cidr_db_csv_import_chunk_rows))
    keep = settings.cidr_db_keep_staging_csv if keep_csv is None else keep_csv

    if not csv_path.is_file():
        raise FileNotFoundError(f"Staging CSV not found: {csv_path}")

    def _emit(rel_pct: int, stage: str) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(max(0, min(100, int(rel_pct))), stage)
        except Exception:
            pass

    label = provider_key
    imported = 0
    rows_since_commit = 0
    use_chunk_commits = chunk_rows > 0 and (total_rows or 0) > chunk_rows

    conn = _sqlite_connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM provider_cidr WHERE provider_key = ?", (provider_key,))

        batch: list[tuple[str, ...]] = []
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            for row in reader:
                if len(row) < 5:
                    continue
                batch.append(tuple(row[:5]))
                if len(batch) < batch_size:
                    continue
                conn.executemany(INSERT_SQL, batch)
                imported += len(batch)
                rows_since_commit += len(batch)
                batch = []

                if total_rows:
                    rel_pct = 40 + int((imported / total_rows) * 58)
                    _emit(rel_pct, f"{label}: импорт в БД ({imported}/{total_rows})…")

                if use_chunk_commits and rows_since_commit >= chunk_rows:
                    _commit_with_retry(conn)
                    conn.execute("BEGIN IMMEDIATE")
                    rows_since_commit = 0

            if batch:
                conn.executemany(INSERT_SQL, batch)
                imported += len(batch)

        _commit_with_retry(conn)
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()

    if total_rows:
        _emit(98, f"{label}: импорт в БД ({imported}/{total_rows})…")
    else:
        _emit(98, f"{label}: импорт в БД ({imported} CIDR)…")

    if not keep:
        try:
            csv_path.unlink(missing_ok=True)
            staging_csv_tmp_path(provider_key).unlink(missing_ok=True)
        except OSError as exc:
            logger.debug("Failed to remove staging CSV for %s: %s", provider_key, exc)

    return imported


def cleanup_staging_csv(provider_key: str | None = None) -> None:
    """Remove stale staging files (.tmp always; .csv when provider_key set or full cleanup)."""
    staging = get_staging_dir()
    if not staging.is_dir():
        return

    if provider_key is not None:
        staging_csv_path(provider_key).unlink(missing_ok=True)
        staging_csv_tmp_path(provider_key).unlink(missing_ok=True)
        return

    for path in staging.glob("*.csv.tmp"):
        try:
            path.unlink()
        except OSError:
            pass
