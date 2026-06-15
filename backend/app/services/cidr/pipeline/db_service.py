"""Service for downloading provider CIDRs and storing them in the database.

The nightly cron job calls refresh_all_providers() to populate ProviderCidr table.
Web UI then reads from DB when generating the final CIDR .txt files.
"""

import json
import logging
import os
import re
import threading
import time
from copy import deepcopy
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib import request
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

# Lazy import to avoid circular deps at module load time
_models = None


def _get_models():
    global _models
    if _models is None:
        from app import models as m
        _models = m
    return _models


from app.services.cidr.pipeline.download import _download_text as _download_cidr_text
from app.services.cidr.pipeline.parsers import _extract_bgp_tools_ipv4, _normalize_single_cidr

# Парсинг CIDR/ASN вынесен в db_extract.py; имена реэкспортируются для совместимости
# (db_service.ASN_TOKEN_PATTERN, db_service._extract_cidrs_with_meta и т.д.).
from app.services.cidr.pipeline.db_extract import (  # noqa: E402
    ASN_TOKEN_PATTERN,
    SOURCE_NAME_ASN_PATTERN,
    _extract_asns_from_source_name,
    _extract_asns_from_sources,
    _extract_asns_from_text,
    _extract_asns_from_url,
    _extract_cidrs_with_meta,
    _normalize_asn,
    _normalize_country_code,
)

RIPE_ANNOUNCED_PREFIXES_URL = "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS{asn}"
RIPE_GEO_BY_ASN_URL = "https://stat.ripe.net/data/maxmind-geo-lite-announced-by-as/data.json?resource=AS{asn}"
RIPE_BGP_STATE_URL = "https://stat.ripe.net/data/bgp-state/data.json?resource=AS{asn}"


def _read_positive_int_env(name, default):
    raw = os.getenv(name)
    if raw is None:
        return int(default)

    try:
        parsed = int(str(raw).strip())
    except (TypeError, ValueError):
        return int(default)

    if parsed <= 0:
        return int(default)

    return parsed


ASN_DISCOVERY_MAX_PER_PROVIDER = _read_positive_int_env(
    "CIDR_DB_ASN_DISCOVERY_MAX_PER_PROVIDER",
    256,
)
ASN_DISCOVERY_SCAN_EXTRA_LIMIT = _read_positive_int_env(
    "CIDR_DB_ASN_DISCOVERY_SCAN_EXTRA_LIMIT",
    128,
)
ASN_FETCH_WORKERS = _read_positive_int_env(
    "CIDR_DB_ASN_FETCH_WORKERS",
    4,
)
SOURCE_FETCH_WORKERS = _read_positive_int_env(
    "CIDR_DB_SOURCE_FETCH_WORKERS",
    4,
)
PROVIDER_FETCH_WORKERS = _read_positive_int_env(
    "CIDR_DB_PROVIDER_WORKERS",
    4,
)
SOURCE_CACHE_TTL_SECONDS = _read_positive_int_env(
    "CIDR_DB_SOURCE_CACHE_TTL_SECONDS",
    900,
)
ASN_FETCH_SOURCE_TIMEOUT_SECONDS = _read_positive_int_env(
    "CIDR_DB_ASN_FETCH_TIMEOUT",
    30,
)
SOURCE_FETCH_TIMEOUT_SECONDS = _read_positive_int_env(
    "CIDR_DB_SOURCE_FETCH_TIMEOUT",
    90,
)
SOURCE_FETCH_RETRIES = _read_positive_int_env(
    "CIDR_DB_SOURCE_FETCH_RETRIES",
    3,
)
CIDR_FALLBACK_DROP_RATIO_WITH_ERRORS = 0.45
CIDR_FALLBACK_MIN_CANDIDATE = _read_positive_int_env(
    "CIDR_DB_FALLBACK_MIN_CANDIDATE",
    500,
)


def _download_text_impl(url, timeout=45):
    return _download_cidr_text(url, timeout=timeout, user_agent="AdminAntizapret-CIDR-DB/1.0")


def _download_text(url, timeout=45):
    from app.services.cidr import pipeline_facade as facade

    hook = facade._download_text
    if hook is not _download_text:
        return hook(url, timeout=timeout)
    return _download_text_impl(url, timeout=timeout)


# ──────────────────────────────────────────────────────────────────────
# Service class
# ──────────────────────────────────────────────────────────────────────

class CidrDbUpdaterService:
    _source_cache = {}
    _source_cache_lock = threading.Lock()

    def __init__(self, *, db, cidr_db=None):
        self.db = db
        self._owns_cidr_db = cidr_db is None
        if cidr_db is None:
            from app.cidr_database import CidrSessionLocal

            self.cidr_db = CidrSessionLocal()
        else:
            self.cidr_db = cidr_db

    def close(self) -> None:
        if self._owns_cidr_db and self.cidr_db is not None:
            self.cidr_db.close()
            self.cidr_db = None

    @staticmethod
    def _current_asn_fetch_workers():
        return _read_positive_int_env("CIDR_DB_ASN_FETCH_WORKERS", ASN_FETCH_WORKERS)

    @staticmethod
    def _current_source_fetch_workers():
        return _read_positive_int_env("CIDR_DB_SOURCE_FETCH_WORKERS", SOURCE_FETCH_WORKERS)

    @staticmethod
    def _current_provider_fetch_workers():
        return _read_positive_int_env("CIDR_DB_PROVIDER_WORKERS", PROVIDER_FETCH_WORKERS)

    @staticmethod
    def _current_source_cache_ttl_seconds():
        ttl = _read_positive_int_env("CIDR_DB_SOURCE_CACHE_TTL_SECONDS", SOURCE_CACHE_TTL_SECONDS)
        return max(60, min(ttl, 3600))

    @staticmethod
    def _resolve_asn_fetch_workers(total_asn_rows, configured_workers=None):
        total = max(0, int(total_asn_rows or 0))
        if total <= 1:
            return total

        if configured_workers is None:
            configured_workers = CidrDbUpdaterService._current_asn_fetch_workers()

        workers = max(1, int(configured_workers or 1))
        # Keep thread count bounded to avoid oversubscription on small VPS hosts.
        workers = min(workers, 32)
        return min(workers, total)

    @staticmethod
    def _resolve_provider_fetch_workers(total_providers, configured_workers=None):
        total = max(0, int(total_providers or 0))
        if total <= 1:
            return total

        if configured_workers is None:
            configured_workers = CidrDbUpdaterService._current_provider_fetch_workers()

        workers = max(1, int(configured_workers or 1))
        workers = min(workers, 16)
        return min(workers, total)

    @staticmethod
    def _build_partial_reasons_by_source(source_details, asn_discovery_errors, asn_fetch_errors, fallback_applied):
        reasons = []
        for detail in source_details or []:
            if str(detail.get("status") or "") == "error":
                reasons.append({
                    "source": detail.get("name") or "unknown",
                    "reason": detail.get("error") or "Источник вернул ошибку",
                })
        for err in asn_discovery_errors or []:
            source, _, reason = str(err).partition(":")
            reasons.append({
                "source": source.strip() or "asn-discovery",
                "reason": reason.strip() or str(err),
            })
        for err in asn_fetch_errors or []:
            source, _, reason = str(err).partition(":")
            reasons.append({
                "source": source.strip() or "asn-fetch",
                "reason": reason.strip() or str(err),
            })
        if fallback_applied:
            reasons.append({
                "source": "fallback",
                "reason": "Сохранен предыдущий пул CIDR из БД",
            })
        return reasons

    def _process_provider_refresh_context(
        self,
        *,
        file_name,
        sources,
        prev_cidr_count,
        prev_asn_count,
        prev_active_asn_count,
        progress_callback=None,
    ):
        def _emit(rel_pct: int, stage: str) -> None:
            if progress_callback is None:
                return
            try:
                progress_callback(max(0, min(100, int(rel_pct))), stage)
            except Exception:
                pass

        _emit(5, f"{file_name}: обнаружение ASN…")
        source_hint_asns = _extract_asns_from_sources(sources)
        discovered_asns, asn_discovery_sources, asn_discovery_errors = self._discover_provider_asns(
            file_name,
            sources,
            seed_asns=set(),
            max_asns=ASN_DISCOVERY_MAX_PER_PROVIDER,
            scan_extra_limit=ASN_DISCOVERY_SCAN_EXTRA_LIMIT,
        )

        priority_asns = set(source_hint_asns)
        discovered_asn_values = [
            int(asn)
            for asn in discovered_asns
            if _normalize_asn(asn) is not None
        ]

        asn_items = []
        asn_source_names = []
        asn_fetch_errors = []
        asn_optional_errors = []
        asn_fetch_meta = {}
        total_asn_rows = len(discovered_asn_values)
        asn_fetch_results = {}
        worker_count = self._resolve_asn_fetch_workers(total_asn_rows)

        if total_asn_rows > 0:
            _emit(20, f"{file_name}: загрузка ASN-префиксов (0/{total_asn_rows})…")

        if total_asn_rows > 0 and worker_count > 1:
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                future_to_asn = {
                    executor.submit(self._download_asn_cidrs_with_meta, asn_value): asn_value
                    for asn_value in discovered_asn_values
                }
                done_asn = 0
                for future in as_completed(future_to_asn):
                    asn_value = future_to_asn[future]
                    try:
                        asn_fetch_results[asn_value] = future.result()
                    except Exception as exc:
                        asn_fetch_results[asn_value] = ([], None, str(exc))
                    done_asn += 1
                    if done_asn == total_asn_rows or done_asn % max(1, total_asn_rows // 10) == 0:
                        _emit(
                            20 + int((done_asn / total_asn_rows) * 55),
                            f"{file_name}: загрузка ASN-префиксов ({done_asn}/{total_asn_rows})…",
                        )
        else:
            for asn_index, asn_value in enumerate(discovered_asn_values, start=1):
                asn_fetch_results[asn_value] = self._download_asn_cidrs_with_meta(asn_value)
                if asn_index == total_asn_rows or asn_index % max(1, total_asn_rows // 10) == 0:
                    _emit(
                        20 + int((asn_index / max(total_asn_rows, 1)) * 55),
                        f"{file_name}: загрузка ASN-префиксов ({asn_index}/{total_asn_rows})…",
                    )

        for asn_value in discovered_asn_values:
            fetched_items, fetched_source, fetched_error = asn_fetch_results.get(
                asn_value,
                ([], None, "ASN результат не получен"),
            )
            if fetched_error:
                if asn_value in priority_asns:
                    asn_fetch_errors.append(f"AS{asn_value}: {fetched_error}")
                else:
                    asn_optional_errors.append(f"AS{asn_value}: {fetched_error}")
                asn_fetch_meta[asn_value] = {
                    "status": "error",
                    "prefix_count": 0,
                    "error": fetched_error,
                }
                continue

            asn_items.extend(fetched_items)
            if fetched_source:
                asn_source_names.append(fetched_source)
            asn_fetch_meta[asn_value] = {
                "status": "ok",
                "prefix_count": len(fetched_items),
                "error": None,
            }

        _emit(82, f"{file_name}: загрузка прямых источников…")
        direct_items, direct_source_used, source_details = self._download_cidrs_with_meta(
            sources,
            return_source_details=True,
        )
        merged_items = self._merge_cidr_items(direct_items + asn_items)
        if not merged_items:
            raise ValueError("Все источники вернули пустой результат")

        candidate_cidr_count = self._count_unique_cidrs(merged_items)
        asn_errors = asn_discovery_errors + asn_fetch_errors
        fallback_applied = self._should_preserve_previous_pool(
            previous_cidr_count=prev_cidr_count,
            candidate_cidr_count=candidate_cidr_count,
            asn_errors=asn_errors,
        )

        if fallback_applied:
            count = prev_cidr_count
            asn_count = prev_asn_count
            active_asn_count = prev_active_asn_count
        else:
            count = candidate_cidr_count
            asn_count = len(discovered_asn_values)
            active_asn_count = asn_count

        expected_asn_min = len(source_hint_asns)
        anomaly_level, anomaly_reason = self._compute_provider_anomaly(
            expected_asn_min=expected_asn_min,
            active_asn_count=active_asn_count,
            current_cidr_count=count,
            previous_cidr_count=prev_cidr_count,
            asn_discovery_errors=asn_discovery_errors,
            asn_fetch_errors=asn_fetch_errors,
        )

        if fallback_applied:
            anomaly_level, anomaly_reason = self._merge_anomaly_reason(
                level=anomaly_level,
                reason=anomaly_reason,
                extra_level="warning",
                extra_reason=(
                    f"Применен safe-fallback: сохранён предыдущий пул CIDR "
                    f"({prev_cidr_count}, новый расчёт: {candidate_cidr_count})"
                ),
            )

        source_chunks = []
        if direct_source_used:
            source_chunks.append(direct_source_used)
        if asn_source_names:
            source_chunks.append(f"ASN-pool:{len(asn_source_names)}")
        if asn_discovery_sources:
            source_chunks.append(f"ASN-discovery:{','.join(sorted(asn_discovery_sources))}")
        if fallback_applied:
            source_chunks.append("fallback:previous-db")
        source_used = "; ".join(chunk for chunk in source_chunks if chunk)
        provider_status = "partial" if (asn_discovery_errors or asn_fetch_errors or fallback_applied) else "ok"
        partial_reasons_by_source = self._build_partial_reasons_by_source(
            source_details,
            asn_discovery_errors,
            asn_fetch_errors,
            fallback_applied,
        )

        return {
            "status": provider_status,
            "cidr_count": count,
            "candidate_cidr_count": candidate_cidr_count,
            "source": source_used,
            "source_details": source_details,
            "partial_reasons_by_source": partial_reasons_by_source,
            "asn_count": asn_count,
            "active_asn_count": active_asn_count,
            "expected_asn_min": expected_asn_min,
            "anomaly_level": anomaly_level,
            "anomaly_reason": anomaly_reason,
            "asn_errors": asn_errors,
            "asn_optional_errors": asn_optional_errors,
            "asn_discovery_errors": asn_discovery_errors,
            "asn_fetch_errors": asn_fetch_errors,
            "fallback_applied": fallback_applied,
            "merged_items": merged_items,
            "discovered_asns": discovered_asn_values,
            "asn_fetch_meta": asn_fetch_meta,
            "dry_run_changes": {
                "previous_cidr_count": int(prev_cidr_count or 0),
                "candidate_cidr_count": int(candidate_cidr_count or 0),
                "final_cidr_count": int(count or 0),
                "would_insert": max(0, int(candidate_cidr_count or 0) - int(prev_cidr_count or 0)) if not fallback_applied else 0,
                "would_delete": max(0, int(prev_cidr_count or 0) - int(candidate_cidr_count or 0)) if not fallback_applied else 0,
                "fallback_applied": bool(fallback_applied),
            },
        }

    # ── Public API ────────────────────────────────────────────────────

    def refresh_all_providers(
        self,
        *,
        triggered_by="cron",
        selected_files=None,
        progress_callback=None,
        dry_run=False,
    ):
        """Download CIDRs from all providers and store/update in DB.

        Returns a summary dict with status, counts, and per-provider details.
        """
        from app.services.cidr.pipeline.provider_sources import PROVIDER_SOURCES

        m = _get_models()

        requested_files = selected_files or list(PROVIDER_SOURCES.keys())
        files_to_update = [name for name in requested_files if name in PROVIDER_SOURCES]
        providers_updated = 0
        providers_failed = 0
        providers_partial = 0
        total_cidrs = 0
        per_provider = {}

        if not files_to_update:
            return {
                "success": False,
                "status": "error",
                "providers_updated": 0,
                "providers_failed": 0,
                "total_cidrs": 0,
                "per_provider": {},
            }

        log_entry = None
        if not dry_run:
            log_entry = m.CidrDbRefreshLog(
                started_at=datetime.now(timezone.utc),
                status="running",
                triggered_by=triggered_by,
            )
            self.db.add(log_entry)
            self.db.commit()

        if not dry_run:
            from app.services.cidr.pipeline.cidr_csv_import import cleanup_staging_csv

            cleanup_staging_csv()

        previous_cidr_counts = {
            file_name: int(self.cidr_db.query(m.ProviderCidr).filter_by(provider_key=file_name).count() or 0)
            for file_name in files_to_update
        }
        previous_asn_counts = {
            file_name: int(self.db.query(m.ProviderAsn).filter_by(provider_key=file_name).count() or 0)
            for file_name in files_to_update
        }
        previous_active_asn_counts = {
            file_name: int(self.db.query(m.ProviderAsn).filter_by(provider_key=file_name, active=True).count() or 0)
            for file_name in files_to_update
        }

        total_files = max(len(files_to_update), 1)

        def _emit_progress(pct, stage):
            if progress_callback:
                try:
                    progress_callback(pct, stage)
                except Exception:
                    pass

        def _provider_progress_slot(index: int) -> tuple[int, int, int]:
            """Return (slot_base, write_base, slot_end) percents for one provider."""
            slot_base = 5 + int(((index - 1) / total_files) * 90)
            slot_end = 5 + int((index / total_files) * 90)
            slot_span = max(1, slot_end - slot_base)
            write_base = slot_base + max(1, int(slot_span * 0.25))
            return slot_base, write_base, slot_end

        def _commit_db_with_retry() -> None:
            from sqlalchemy.exc import OperationalError

            for attempt in range(5):
                try:
                    self.db.commit()
                    return
                except OperationalError as exc:
                    if "database is locked" not in str(exc).lower() or attempt == 4:
                        raise
                    time.sleep(0.1 * (attempt + 1))

        _emit_progress(3, "Подготовка обновления провайдеров")

        for index, file_name in enumerate(files_to_update, start=1):
            slot_base, write_base, slot_end = _provider_progress_slot(index)
            write_span = max(1, slot_end - write_base)
            sources = PROVIDER_SOURCES.get(file_name) or []

            if not sources:
                err_msg = "Пустой список источников"
                logger.warning("CIDR DB refresh failed for %s: %s", file_name, err_msg)
                if not dry_run:
                    try:
                        self._update_provider_meta(
                            file_name,
                            cidr_count=None,
                            source_used=None,
                            status="error",
                            error=err_msg,
                            anomaly_level="critical",
                            anomaly_reason=err_msg,
                            commit=True,
                        )
                    except Exception:
                        self.db.rollback()
                        raise
                providers_failed += 1
                per_provider[file_name] = {"status": "error", "error": err_msg}
                _emit_progress(slot_end, f"Ошибка: {file_name} ({index}/{total_files})")
                continue

            _emit_progress(slot_base, f"Провайдер {index}/{total_files}: загрузка {file_name}…")
            fetch_span = max(1, write_base - slot_base)

            def _fetch_progress(rel_pct: int, stage: str) -> None:
                abs_pct = slot_base + int((max(0, min(100, rel_pct)) / 100) * fetch_span)
                heartbeat_state["pct"] = abs_pct
                heartbeat_state["stage"] = stage
                _emit_progress(abs_pct, stage)

            heartbeat_stop = threading.Event()
            heartbeat_state = {
                "pct": slot_base,
                "stage": f"Провайдер {index}/{total_files}: загрузка {file_name}…",
                "tick": 0,
            }

            def _fetch_heartbeat_loop() -> None:
                while not heartbeat_stop.wait(3.0):
                    heartbeat_state["tick"] += 1
                    elapsed = heartbeat_state["tick"] * 3
                    _emit_progress(
                        heartbeat_state["pct"],
                        f"{heartbeat_state['stage']} ({elapsed}с)",
                    )

            heartbeat_thread = threading.Thread(target=_fetch_heartbeat_loop, daemon=True)
            heartbeat_thread.start()
            try:
                result = self._process_provider_refresh_context(
                    file_name=file_name,
                    sources=sources,
                    prev_cidr_count=previous_cidr_counts.get(file_name, 0),
                    prev_asn_count=previous_asn_counts.get(file_name, 0),
                    prev_active_asn_count=previous_active_asn_counts.get(file_name, 0),
                    progress_callback=_fetch_progress,
                )
            except Exception as exc:
                result = {"status": "error", "error": str(exc)}
            finally:
                heartbeat_stop.set()
                heartbeat_thread.join(timeout=0.5)

            if "error" in result and result.get("status") == "error":
                err_msg = str(result.get("error") or "unknown error")
                logger.warning("CIDR DB refresh failed for %s: %s", file_name, err_msg)
                if not dry_run:
                    try:
                        self._update_provider_meta(
                            file_name,
                            cidr_count=None,
                            source_used=None,
                            status="error",
                            error=err_msg,
                            anomaly_level="critical",
                            anomaly_reason=err_msg,
                            commit=True,
                        )
                    except Exception:
                        self.db.rollback()
                        raise
                providers_failed += 1
                per_provider[file_name] = {"status": "error", "error": err_msg}
                _emit_progress(slot_end, f"Ошибка: {file_name} ({index}/{total_files})")
                continue

            provider_status = str(result.get("status") or "ok")
            providers_updated += 1
            if provider_status == "partial":
                providers_partial += 1

            count = int(result.get("cidr_count") or 0)
            total_cidrs += count
            asn_rows = []

            _emit_progress(write_base, f"Провайдер {index}/{total_files}: запись {file_name}…")

            if not dry_run and not bool(result.get("fallback_applied")):
                try:

                    def _provider_write_progress(rel_pct: int, stage: str) -> None:
                        abs_pct = write_base + int((max(0, min(100, rel_pct)) / 100) * write_span)
                        _emit_progress(abs_pct, stage)

                    asn_rows = self._upsert_provider_asns(
                        file_name, result.get("discovered_asns") or [], commit=True
                    )
                    self._apply_provider_asn_runtime_meta(
                        file_name, result.get("asn_fetch_meta") or {}, commit=True
                    )
                    count = self._upsert_provider_cidrs(
                        file_name,
                        result.get("merged_items") or [],
                        commit=True,
                        progress_callback=_provider_write_progress,
                        progress_label=file_name,
                    )
                    self._update_provider_meta(
                        file_name,
                        cidr_count=count,
                        source_used=result.get("source"),
                        status=provider_status,
                        error=(
                            "; ".join((result.get("asn_errors") or [])[:6])
                            if (result.get("asn_errors") or [])
                            else None
                        ),
                        expected_asn_min=result.get("expected_asn_min"),
                        asn_count=(len(asn_rows) if asn_rows else result.get("asn_count")),
                        active_asn_count=(
                            len([row for row in asn_rows if row.active])
                            if asn_rows
                            else result.get("active_asn_count")
                        ),
                        anomaly_level=result.get("anomaly_level"),
                        anomaly_reason=result.get("anomaly_reason"),
                        commit=False,
                    )
                    if log_entry is not None and asn_rows:
                        self._write_provider_asn_snapshots(
                            log_entry.id, file_name, asn_rows, commit=False
                        )
                    _commit_db_with_retry()
                except Exception as exc:
                    self.db.rollback()
                    err_msg = str(exc)
                    logger.warning("CIDR DB persist failed for %s: %s", file_name, err_msg)
                    try:
                        m = _get_models()
                        self.cidr_db.query(m.ProviderCidr).filter_by(provider_key=file_name).delete(
                            synchronize_session=False
                        )
                        self.cidr_db.commit()
                    except Exception:
                        self.cidr_db.rollback()
                    try:
                        self._update_provider_meta(
                            file_name,
                            cidr_count=None,
                            source_used=None,
                            status="error",
                            error=err_msg,
                            anomaly_level="critical",
                            anomaly_reason=err_msg,
                            commit=True,
                        )
                    except Exception:
                        self.db.rollback()
                        raise
                    _emit_progress(slot_end, f"Ошибка записи: {file_name} ({index}/{total_files})")
                    continue
            elif not dry_run:
                try:
                    self._update_provider_meta(
                        file_name,
                        cidr_count=count,
                        source_used=result.get("source"),
                        status=provider_status,
                        error=(
                            "safe-fallback to previous CIDR pool"
                            if result.get("fallback_applied")
                            else None
                        ),
                        expected_asn_min=result.get("expected_asn_min"),
                        asn_count=result.get("asn_count"),
                        active_asn_count=result.get("active_asn_count"),
                        anomaly_level=result.get("anomaly_level"),
                        anomaly_reason=result.get("anomaly_reason"),
                        commit=True,
                    )
                except Exception:
                    self.db.rollback()
                    raise

            per_provider[file_name] = {
                "status": provider_status,
                "cidr_count": count,
                "source": result.get("source"),
                "source_details": result.get("source_details") or [],
                "partial_reasons_by_source": result.get("partial_reasons_by_source") or [],
                "asn_count": int(result.get("asn_count") or 0),
                "active_asn_count": int(result.get("active_asn_count") or 0),
                "expected_asn_min": int(result.get("expected_asn_min") or 0),
                "anomaly_level": result.get("anomaly_level"),
                "anomaly_reason": result.get("anomaly_reason"),
                "asn_errors": result.get("asn_errors") or [],
                "asn_optional_errors": result.get("asn_optional_errors") or [],
                "fallback_applied": bool(result.get("fallback_applied")),
                "candidate_cidr_count": int(result.get("candidate_cidr_count") or 0),
                "dry_run_changes": result.get("dry_run_changes") or {},
            }

            _emit_progress(
                slot_end,
                f"Провайдер {index}/{total_files}: {file_name} — {count} CIDR",
            )

        final_status = "ok"
        if providers_failed > 0 and providers_updated == 0:
            final_status = "error"
        elif providers_failed > 0 or providers_partial > 0:
            final_status = "partial"

        if log_entry is not None:
            try:
                _emit_progress(96, "Сохранение журнала обновления…")
                log_entry.finished_at = datetime.now(timezone.utc)
                log_entry.status = final_status
                log_entry.providers_updated = providers_updated
                log_entry.providers_failed = providers_failed
                log_entry.total_cidrs = total_cidrs
                log_entry.details_json = json.dumps(per_provider, ensure_ascii=False)
                _commit_db_with_retry()
            except Exception as exc:
                self.db.rollback()
                logger.warning("CIDR DB refresh failed to persist: %s", exc)
                return {
                    "success": False,
                    "status": "error",
                    "message": str(exc),
                    "providers_updated": 0,
                    "providers_failed": len(files_to_update),
                    "total_cidrs": 0,
                    "per_provider": {},
                    "dry_run": bool(dry_run),
                }

        _emit_progress(100, "Dry-run завершен" if dry_run else "Обновление CIDR БД завершено")

        return {
            "success": final_status in ("ok", "partial"),
            "status": final_status,
            "providers_updated": providers_updated,
            "providers_failed": providers_failed,
            "total_cidrs": total_cidrs,
            "per_provider": per_provider,
            "dry_run": bool(dry_run),
            "log_id": log_entry.id if log_entry is not None else None,
        }

    def get_db_status(self):
        """Return current DB status: last refresh info + per-provider CIDR counts."""
        from app.services.cidr.pipeline.provider_sources import PROVIDER_SOURCES

        m = _get_models()

        last_log = (
            self.db.query(m.CidrDbRefreshLog)
            .order_by(m.CidrDbRefreshLog.started_at.desc())
            .first()
        )
        last_details = {}
        if last_log and last_log.details_json:
            try:
                parsed = json.loads(last_log.details_json or "{}")
                if isinstance(parsed, dict):
                    last_details = parsed
            except (TypeError, ValueError):
                last_details = {}
        metas = self.db.query(m.ProviderMeta).all()
        meta_by_key = {pm.provider_key: pm for pm in metas}
        total_cidrs = sum(pm.cidr_count for pm in metas)
        asn_rows = (
            self.db.query(m.ProviderAsn)
            .filter_by(active=True)
            .order_by(m.ProviderAsn.provider_key.asc(), m.ProviderAsn.asn.asc())
            .all()
        )
        asn_map = defaultdict(list)
        for row in asn_rows:
            asn_map[row.provider_key].append(f"AS{row.asn}")

        providers_info = {}
        for provider_key in PROVIDER_SOURCES.keys():
            pm = meta_by_key.get(provider_key)
            if pm is None:
                detail = last_details.get(provider_key) if isinstance(last_details, dict) else {}
                providers_info[provider_key] = {
                    "cidr_count": 0,
                    "last_refreshed_at": None,
                    "refresh_status": "never",
                    "refresh_error": None,
                    "source_used": None,
                    "expected_asn_min": 0,
                    "asn_count": 0,
                    "active_asn_count": 0,
                    "active_asns": [],
                    "anomaly_level": "none",
                    "anomaly_reason": None,
                    "source_details": (detail.get("source_details") if isinstance(detail, dict) else []) or [],
                    "partial_reasons_by_source": (detail.get("partial_reasons_by_source") if isinstance(detail, dict) else []) or [],
                    "dry_run_changes": (detail.get("dry_run_changes") if isinstance(detail, dict) else {}) or {},
                }
                continue

            detail = last_details.get(provider_key) if isinstance(last_details, dict) else {}
            providers_info[provider_key] = {
                "cidr_count": pm.cidr_count,
                "last_refreshed_at": pm.last_refreshed_at.isoformat() if pm.last_refreshed_at else None,
                "refresh_status": pm.refresh_status,
                "refresh_error": pm.refresh_error,
                "source_used": pm.source_used,
                "expected_asn_min": int(pm.expected_asn_min or 0),
                "asn_count": int(pm.asn_count or 0),
                "active_asn_count": int(pm.active_asn_count or 0),
                "active_asns": asn_map.get(provider_key, []),
                "anomaly_level": pm.anomaly_level or "none",
                "anomaly_reason": pm.anomaly_reason,
                "source_details": (detail.get("source_details") if isinstance(detail, dict) else []) or [],
                "partial_reasons_by_source": (detail.get("partial_reasons_by_source") if isinstance(detail, dict) else []) or [],
                "dry_run_changes": (detail.get("dry_run_changes") if isinstance(detail, dict) else {}) or {},
            }

        alerts = self._build_degradation_alerts(last_log, metas)

        return {
            "last_refresh_started": last_log.started_at.isoformat() if last_log else None,
            "last_refresh_finished": last_log.finished_at.isoformat() if (last_log and last_log.finished_at) else None,
            "last_refresh_status": last_log.status if last_log else "never",
            "last_refresh_triggered_by": last_log.triggered_by if last_log else None,
            "total_cidrs": total_cidrs,
            "providers": providers_info,
            "alerts": alerts,
        }

    def append_refresh_log_pipeline_details(self, log_id: int, pipeline: dict) -> None:
        """Merge cron pipeline metadata (compile/deploy) into refresh log details_json."""
        m = _get_models()
        log_entry = self.db.query(m.CidrDbRefreshLog).filter(m.CidrDbRefreshLog.id == log_id).first()
        if not log_entry:
            logger.warning("CIDR refresh log %s not found — pipeline details not saved", log_id)
            return

        try:
            details = json.loads(log_entry.details_json or "{}")
        except (TypeError, ValueError):
            details = {}
        if not isinstance(details, dict):
            details = {}

        existing = details.get("_pipeline")
        if not isinstance(existing, dict):
            existing = {}
        existing.update(pipeline)
        details["_pipeline"] = existing
        log_entry.details_json = json.dumps(details, ensure_ascii=False)
        self.db.commit()

    def get_refresh_history(self, limit=10):
        """Return last N refresh log entries."""
        m = _get_models()
        logs = (
            self.db.query(m.CidrDbRefreshLog)
            .order_by(m.CidrDbRefreshLog.started_at.desc())
            .limit(limit)
            .all()
        )
        result = []
        for entry in logs:
            result.append({
                "id": entry.id,
                "started_at": entry.started_at.isoformat(),
                "finished_at": entry.finished_at.isoformat() if entry.finished_at else None,
                "status": entry.status,
                "providers_updated": entry.providers_updated,
                "providers_failed": entry.providers_failed,
                "total_cidrs": entry.total_cidrs,
                "triggered_by": entry.triggered_by,
            })
        return result

    def get_last_failed_providers(self):
        """Return provider keys failed in the most recent non-cleared refresh log."""
        m = _get_models()
        log_entry = (
            self.db.query(m.CidrDbRefreshLog)
            .filter(m.CidrDbRefreshLog.status != "cleared")
            .order_by(m.CidrDbRefreshLog.started_at.desc())
            .first()
        )
        if not log_entry or not log_entry.details_json:
            return []

        try:
            details = json.loads(log_entry.details_json or "{}")
        except (TypeError, ValueError):
            return []

        if not isinstance(details, dict):
            return []

        failed = []
        for provider_key, provider_info in details.items():
            if str(provider_key).startswith("_"):
                continue
            if not isinstance(provider_info, dict):
                continue
            if str(provider_info.get("status") or "") == "error":
                failed.append(str(provider_key))
        return sorted(set(failed))

    def clear_provider_data(self, *, selected_files=None, triggered_by="manual"):
        """Delete stored CIDR/ASN/meta for all or selected providers."""
        from app.services.cidr.pipeline.provider_sources import PROVIDER_SOURCES

        m = _get_models()
        valid_keys = set(PROVIDER_SOURCES.keys())
        if selected_files is None:
            targets = sorted(valid_keys)
        else:
            targets = [str(name) for name in selected_files if str(name) in valid_keys]

        if not targets:
            return {
                "success": False,
                "message": "Нет валидных провайдеров для очистки",
                "providers_cleared": 0,
                "deleted": {},
                "triggered_by": triggered_by,
            }

        deleted = {
            "provider_cidr": self.cidr_db.query(m.ProviderCidr).filter(m.ProviderCidr.provider_key.in_(targets)).delete(synchronize_session=False),
            "provider_asn": self.db.query(m.ProviderAsn).filter(m.ProviderAsn.provider_key.in_(targets)).delete(synchronize_session=False),
            "provider_asn_snapshot": self.db.query(m.ProviderAsnSnapshot).filter(m.ProviderAsnSnapshot.provider_key.in_(targets)).delete(synchronize_session=False),
            "provider_meta": self.db.query(m.ProviderMeta).filter(m.ProviderMeta.provider_key.in_(targets)).delete(synchronize_session=False),
        }
        full_clear = bool(valid_keys) and set(targets) == valid_keys
        if full_clear:
            deleted["cidr_db_refresh_log"] = self.db.query(m.CidrDbRefreshLog).delete(synchronize_session=False)
        else:
            now = datetime.now(timezone.utc)
            clear_log = m.CidrDbRefreshLog(
                started_at=now,
                finished_at=now,
                status="cleared",
                providers_updated=0,
                providers_failed=0,
                total_cidrs=0,
                triggered_by=triggered_by,
                details_json=json.dumps(
                    {"providers_cleared": targets, "deleted": deleted},
                    ensure_ascii=False,
                ),
            )
            self.db.add(clear_log)
        self.cidr_db.commit()
        self.db.commit()

        return {
            "success": True,
            "message": f"Очищено провайдеров: {len(targets)}",
            "providers_cleared": len(targets),
            "providers": targets,
            "deleted": deleted,
            "triggered_by": triggered_by,
        }

    def cleanup_retired_provider_data(self):
        """Remove provider rows that are no longer present in IP_FILES."""
        from app.services.cidr.constants import IP_FILES

        m = _get_models()
        valid_provider_keys = set(IP_FILES.keys())
        if not valid_provider_keys:
            return {
                "success": False,
                "message": "Пустой список валидных провайдеров",
                "deleted": {},
            }

        valid_list = sorted(valid_provider_keys)
        deleted = {
            "provider_cidr": self.cidr_db.query(m.ProviderCidr).filter(~m.ProviderCidr.provider_key.in_(valid_list)).delete(synchronize_session=False),
            "provider_meta": self.db.query(m.ProviderMeta).filter(~m.ProviderMeta.provider_key.in_(valid_list)).delete(synchronize_session=False),
            "provider_asn": self.db.query(m.ProviderAsn).filter(~m.ProviderAsn.provider_key.in_(valid_list)).delete(synchronize_session=False),
            "provider_asn_snapshot": self.db.query(m.ProviderAsnSnapshot).filter(~m.ProviderAsnSnapshot.provider_key.in_(valid_list)).delete(synchronize_session=False),
        }

        self.cidr_db.commit()
        self.db.commit()

        return {
            "success": True,
            "message": "Очистка устаревших провайдеров завершена",
            "deleted": deleted,
        }

    # ── Private helpers ───────────────────────────────────────────────

    def _discover_provider_asns(self, provider_key, sources, *, seed_asns=None, max_asns=ASN_DISCOVERY_MAX_PER_PROVIDER, scan_extra_limit=ASN_DISCOVERY_SCAN_EXTRA_LIMIT):
        """Discover provider ASN pool using static metadata + source hints + scanned pages."""
        discovered = []
        discovered_set = set()
        scan_limit = max(0, int(scan_extra_limit or 0))

        def _append_asns(values):
            for asn_value in values:
                if asn_value is None or asn_value in discovered_set:
                    continue
                discovered.append(asn_value)
                discovered_set.add(asn_value)

        _append_asns(sorted(seed_asns or set()))
        discovery_sources = set()
        errors = []
        scan_candidates = set()

        for source in sources or []:
            source_name = str(source.get("name") or "unknown")
            source_url = str(source.get("url") or "")
            source_fmt = str(source.get("format") or "")

            from_source_meta = _extract_asns_from_source_name(source_name) | _extract_asns_from_url(source_url)
            if from_source_meta:
                _append_asns(sorted(from_source_meta))
                discovery_sources.add("source-meta")

            if source_fmt != "cidr_text_scan" or scan_limit <= 0:
                continue

            try:
                text_data = _download_text(source_url, timeout=ASN_FETCH_SOURCE_TIMEOUT_SECONDS)
                scanned_asns = _extract_asns_from_text(text_data)
                if scanned_asns:
                    scan_candidates.update(a for a in scanned_asns if a is not None and a not in discovered_set)
                    discovery_sources.add(source_name)
            except Exception as exc:
                errors.append(f"{source_name}: {exc}")

        scan_list = sorted(scan_candidates)
        if len(scan_list) > scan_limit:
            _append_asns(scan_list[:scan_limit])
        else:
            _append_asns(scan_list)

        if len(discovered) > max_asns:
            discovered = discovered[:max_asns]

        return discovered, discovery_sources, errors

    def _download_asn_cidrs_with_meta(self, asn):
        """Download prefixes for one ASN from RIPE endpoints with geo fallback."""
        asn_value = _normalize_asn(asn)
        if asn_value is None:
            return [], None, "Некорректный ASN"

        sources = [
            {
                "name": f"ripe-as{asn_value}",
                "url": RIPE_ANNOUNCED_PREFIXES_URL.format(asn=asn_value),
                "format": "ripe_json",
                "timeout": ASN_FETCH_SOURCE_TIMEOUT_SECONDS,
            },
            {
                "name": f"ripe-as{asn_value}-geo",
                "url": RIPE_GEO_BY_ASN_URL.format(asn=asn_value),
                "format": "ripe_geo_json",
                "timeout": ASN_FETCH_SOURCE_TIMEOUT_SECONDS,
            },
            {
                "name": f"ripe-as{asn_value}-bgpstate",
                "url": RIPE_BGP_STATE_URL.format(asn=asn_value),
                "format": "ripe_bgp_state_json",
                "timeout": ASN_FETCH_SOURCE_TIMEOUT_SECONDS,
            },
        ]

        last_error = None
        for attempt in range(3):
            try:
                items, source_used = self._download_cidrs_with_meta(sources)
                return items, source_used, None
            except Exception as exc:
                last_error = str(exc)
                if attempt < 2:
                    time.sleep(1 + attempt)
                    continue
        return [], None, last_error

    @staticmethod
    def _merge_cidr_items(items):
        """Deduplicate CIDR rows and preserve richer geo metadata where possible."""
        merged = {}
        for item in items:
            cidr = str(item.get("cidr") or "").strip()
            if not cidr:
                continue
            existing = merged.get(cidr)
            if existing is None:
                merged[cidr] = {
                    "cidr": cidr,
                    "region": item.get("region") or None,
                    "countries": (list(item.get("countries") or []) or None),
                }
                continue

            existing_countries = set(existing.get("countries") or [])
            new_countries = set(item.get("countries") or [])
            countries = sorted(existing_countries | new_countries)

            region = existing.get("region") or item.get("region") or None
            if (not existing.get("region") and item.get("region")) or (not existing_countries and new_countries):
                merged[cidr] = {
                    "cidr": cidr,
                    "region": region,
                    "countries": countries or None,
                }
            elif countries:
                existing["countries"] = countries

        return list(merged.values())

    def _upsert_provider_asns(self, provider_key, asns, *, commit=True):
        """Upsert provider ASN pool and deactivate ASN entries not seen in this refresh."""
        m = _get_models()
        now = datetime.now(timezone.utc)

        existing_rows = self.db.query(m.ProviderAsn).filter_by(provider_key=provider_key).all()
        existing_by_asn = {int(row.asn): row for row in existing_rows}
        target_asns = {int(asn) for asn in asns if _normalize_asn(asn) is not None}

        for asn in target_asns:
            row = existing_by_asn.get(asn)
            if row is None:
                row = m.ProviderAsn(
                    provider_key=provider_key,
                    asn=asn,
                    source="discovery",
                    active=True,
                    status="ok",
                    error=None,
                    prefix_count=0,
                    discovered_at=now,
                    last_seen_at=now,
                )
                self.db.add(row)
                existing_by_asn[asn] = row
            else:
                row.active = True
                row.last_seen_at = now

        for asn, row in existing_by_asn.items():
            if asn not in target_asns:
                row.active = False

        if commit:
            self.db.commit()
        return sorted((row for row in existing_by_asn.values() if row.active), key=lambda item: item.asn)

    def _apply_provider_asn_runtime_meta(self, provider_key, asn_fetch_meta, *, commit=True):
        """Persist per-AS fetch status and prefix counts for the latest refresh attempt."""
        m = _get_models()
        if not asn_fetch_meta:
            return

        rows = (
            self.db.query(m.ProviderAsn)
            .filter_by(provider_key=provider_key)
            .filter(m.ProviderAsn.asn.in_(list(asn_fetch_meta.keys())))
            .all()
        )
        now = datetime.now(timezone.utc)
        for row in rows:
            meta = asn_fetch_meta.get(int(row.asn)) or {}
            row.status = meta.get("status") or "ok"
            row.error = meta.get("error")
            row.prefix_count = int(meta.get("prefix_count") or 0)
            row.last_seen_at = now

        if commit:
            self.db.commit()

    def _write_provider_asn_snapshots(self, refresh_log_id, provider_key, asn_rows, *, commit=True):
        """Store ASN pool snapshot for refresh history and degradation analysis."""
        m = _get_models()
        if not asn_rows:
            return

        snapshots = [
            m.ProviderAsnSnapshot(
                refresh_log_id=refresh_log_id,
                provider_key=provider_key,
                asn=int(row.asn),
                status=row.status or "ok",
                prefix_count=int(row.prefix_count or 0),
                created_at=datetime.now(timezone.utc),
            )
            for row in asn_rows
        ]
        self.db.bulk_save_objects(snapshots)
        if commit:
            self.db.commit()

    @staticmethod
    def _compute_provider_anomaly(
        *,
        expected_asn_min,
        active_asn_count,
        current_cidr_count,
        previous_cidr_count,
        asn_discovery_errors=None,
        asn_fetch_errors=None,
    ):
        """Classify refresh degradation severity for one provider."""
        level = "none"
        reasons = []
        discovery_errors = list(asn_discovery_errors or [])
        fetch_errors = list(asn_fetch_errors or [])
        healthy_pool = current_cidr_count >= CIDR_FALLBACK_MIN_CANDIDATE

        if expected_asn_min > 0 and active_asn_count < expected_asn_min:
            level = "warning"
            reasons.append(f"ASN меньше ожидаемого: {active_asn_count}/{expected_asn_min}")

        drop_ratio = 0.0
        if previous_cidr_count > 0:
            drop_ratio = 1.0 - (float(current_cidr_count) / float(previous_cidr_count))
            if drop_ratio >= 0.5:
                level = "critical"
                reasons.append(f"CIDR упали на {int(drop_ratio * 100)}%")
            elif drop_ratio >= 0.25 and level != "critical":
                level = "warning"
                reasons.append(f"CIDR упали на {int(drop_ratio * 100)}%")

        no_cidr_drop = previous_cidr_count <= 0 or drop_ratio < 0.25

        if current_cidr_count == 0:
            level = "critical"
            reasons.append("CIDR-пул пуст")

        if discovery_errors or fetch_errors:
            total_asn_errors = len(discovery_errors) + len(fetch_errors)
            reasons.append(f"Ошибки ASN-источников: {total_asn_errors}")
            if healthy_pool and no_cidr_drop:
                if level == "none":
                    level = "info"
            elif fetch_errors and not healthy_pool:
                if level == "none":
                    level = "warning"
            elif discovery_errors and level == "none":
                level = "info"

        return level, "; ".join(reasons) if reasons else None

    @staticmethod
    def _count_unique_cidrs(cidr_items):
        return len({str(item.get("cidr") or "").strip() for item in (cidr_items or []) if item.get("cidr")})

    @staticmethod
    def _should_preserve_previous_pool(*, previous_cidr_count, candidate_cidr_count, asn_errors):
        if previous_cidr_count <= 0:
            return False
        if candidate_cidr_count <= 0:
            return True

        # If the pool is stable and there are no ASN errors, do not trigger
        # safe-fallback for naturally small providers (e.g. Cloudflare official list).
        if candidate_cidr_count == previous_cidr_count and not asn_errors:
            return False

        if candidate_cidr_count >= CIDR_FALLBACK_MIN_CANDIDATE and not asn_errors:
            return False

        if candidate_cidr_count < CIDR_FALLBACK_MIN_CANDIDATE:
            # Keep fallback for large historical pools collapsing to a tiny set.
            # But avoid warning churn for providers that are consistently small.
            if previous_cidr_count < CIDR_FALLBACK_MIN_CANDIDATE and not asn_errors:
                return False
            return True

        drop_ratio = 1.0 - (float(candidate_cidr_count) / float(previous_cidr_count))
        if asn_errors and drop_ratio >= CIDR_FALLBACK_DROP_RATIO_WITH_ERRORS:
            return True
        return False

    @staticmethod
    def _merge_anomaly_reason(*, level, reason, extra_level, extra_reason):
        severity_order = {"critical": 3, "warning": 2, "info": 1, "none": 0}
        current = str(level or "none")
        incoming = str(extra_level or "none")
        merged_level = current if severity_order.get(current, 0) >= severity_order.get(incoming, 0) else incoming

        reasons = []
        if reason:
            reasons.append(str(reason))
        if extra_reason:
            reasons.append(str(extra_reason))
        merged_reason = "; ".join(chunk for chunk in reasons if chunk) or None
        return merged_level, merged_reason

    def _build_degradation_alerts(self, last_log, metas):
        """Build compact alert list for UI based on provider anomaly flags and global drops."""
        m = _get_models()
        alerts = []

        for pm in metas:
            level = pm.anomaly_level or "none"
            if level in ("none", "info"):
                continue
            alerts.append({
                "scope": "provider",
                "provider_key": pm.provider_key,
                "level": level,
                "message": pm.anomaly_reason or "Обнаружена деградация данных провайдера",
            })

        if last_log:
            prev_log = (
                self.db.query(m.CidrDbRefreshLog)
                .filter(m.CidrDbRefreshLog.id != last_log.id)
                .order_by(m.CidrDbRefreshLog.started_at.desc())
                .first()
            )
            if (
                prev_log
                and str(prev_log.status or "") != "cleared"
                and int(prev_log.total_cidrs or 0) > 0
            ):
                previous_total = int(prev_log.total_cidrs or 0)
                current_total = int(last_log.total_cidrs or 0)
                if current_total < int(previous_total * 0.7):
                    alerts.append({
                        "scope": "global",
                        "provider_key": None,
                        "level": "warning",
                        "message": f"Общий пул CIDR снизился: {current_total} против {previous_total}",
                    })

        severity_order = {"critical": 0, "warning": 1, "info": 2, "none": 3}
        alerts.sort(key=lambda item: severity_order.get(item.get("level"), 9))
        return alerts

    def _download_cidrs_with_meta(self, sources, *, return_source_details=False):
        """Try each source in order and merge all successful CIDR datasets."""
        all_items = []
        source_names_used = []
        source_details = []
        errors = []
        source_list = list(sources or [])
        if not source_list:
            raise ValueError("Список источников пуст")

        workers = max(1, int(self._current_source_fetch_workers() or 1))
        workers = min(workers, len(source_list), 16)

        def _fetch_single(source):
            fmt = source.get("format", "")
            timeout = source.get("timeout", SOURCE_FETCH_TIMEOUT_SECONDS)
            try:
                timeout = int(timeout)
            except (TypeError, ValueError):
                timeout = SOURCE_FETCH_TIMEOUT_SECONDS
            timeout = max(3, min(timeout, 180))

            cache_ttl = self._current_source_cache_ttl_seconds()
            cache_key = f"{source.get('url')}|{fmt}|{timeout}"
            retries = max(1, int(SOURCE_FETCH_RETRIES or 1))
            last_exc = None

            for attempt in range(retries):
                cache_hit = False
                text_data = None
                now = time.time()
                with self._source_cache_lock:
                    cached = self._source_cache.get(cache_key)
                    if cached and (now - float(cached.get("ts") or 0)) <= float(cache_ttl):
                        text_data = deepcopy(cached.get("payload") or "")
                        cache_hit = True

                if text_data is None:
                    try:
                        text_data = _download_text(source["url"], timeout=timeout)
                    except Exception as exc:
                        last_exc = exc
                        if attempt < retries - 1:
                            time.sleep(1 + attempt)
                            continue
                        raise

                try:
                    items = _extract_cidrs_with_meta(text_data, fmt)
                    if not items:
                        raise ValueError("Пустой результат")
                except Exception as exc:
                    last_exc = exc
                    if attempt < retries - 1:
                        time.sleep(1 + attempt)
                        continue
                    raise

                if not cache_hit:
                    with self._source_cache_lock:
                        self._source_cache[cache_key] = {"ts": now, "payload": str(text_data or "")}
                return items, cache_hit

            raise last_exc or ValueError("Не удалось загрузить источник")

        if workers <= 1:
            for source in source_list:
                try:
                    items, cache_hit = _fetch_single(source)
                    all_items.extend(items)
                    source_names_used.append(source["name"])
                    source_details.append({
                        "name": source.get("name"),
                        "url": source.get("url"),
                        "status": "ok",
                        "count": len(items),
                        "error": None,
                        "cache_hit": bool(cache_hit),
                    })
                except Exception as exc:
                    err_msg = f"{source['name']}: {exc}"
                    errors.append(err_msg)
                    source_details.append({
                        "name": source.get("name"),
                        "url": source.get("url"),
                        "status": "error",
                        "count": 0,
                        "error": str(exc),
                        "cache_hit": False,
                    })
        else:
            success_by_index = {}
            error_by_index = {}
            cache_hit_by_index = {}
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_index = {
                    executor.submit(_fetch_single, source): idx
                    for idx, source in enumerate(source_list)
                }
                for future in as_completed(future_to_index):
                    idx = future_to_index[future]
                    source = source_list[idx]
                    try:
                        items, cache_hit = future.result()
                        success_by_index[idx] = items
                        cache_hit_by_index[idx] = bool(cache_hit)
                    except Exception as exc:
                        error_by_index[idx] = f"{source['name']}: {exc}"

            for idx, source in enumerate(source_list):
                if idx in success_by_index:
                    all_items.extend(success_by_index[idx])
                    source_names_used.append(source["name"])
                    source_details.append({
                        "name": source.get("name"),
                        "url": source.get("url"),
                        "status": "ok",
                        "count": len(success_by_index[idx]),
                        "error": None,
                        "cache_hit": bool(cache_hit_by_index.get(idx)),
                    })
                elif idx in error_by_index:
                    errors.append(error_by_index[idx])
                    source_details.append({
                        "name": source.get("name"),
                        "url": source.get("url"),
                        "status": "error",
                        "count": 0,
                        "error": error_by_index[idx],
                        "cache_hit": False,
                    })

        if not all_items:
            raise ValueError("; ".join(errors) if errors else "Все источники вернули пустой результат")

        if return_source_details:
            return all_items, ", ".join(source_names_used), source_details
        return all_items, ", ".join(source_names_used)

    def _upsert_provider_cidrs(
        self,
        provider_key,
        cidr_items,
        *,
        commit=True,
        chunk_commit=False,
        progress_callback=None,
        progress_label=None,
    ):
        """Replace provider CIDRs via CSV staging and native SQLite bulk import."""
        del chunk_commit  # legacy kwarg, CSV import replaces ORM chunk commits
        from app.services.cidr.pipeline.cidr_csv_import import (
            get_sqlite_db_path,
            import_provider_cidr_csv,
            write_provider_cidr_csv,
        )

        label = str(progress_label or provider_key)

        def _emit(rel_pct: int, stage: str) -> None:
            if progress_callback is None:
                return
            try:
                progress_callback(rel_pct, stage)
            except Exception:
                pass

        def _commit_sa_session() -> None:
            from sqlalchemy.exc import OperationalError

            for attempt in range(5):
                try:
                    self.db.commit()
                    return
                except OperationalError as exc:
                    if "database is locked" not in str(exc).lower() or attempt == 4:
                        raise
                    time.sleep(0.1 * (attempt + 1))

        refreshed_at = datetime.now(timezone.utc)
        _emit(5, f"{label}: запись CSV…")
        csv_path, total = write_provider_cidr_csv(
            provider_key,
            cidr_items,
            refreshed_at=refreshed_at,
        )
        _emit(35, f"{label}: запись CSV ({total} CIDR)…")

        if commit:
            _commit_sa_session()

        imported = import_provider_cidr_csv(
            get_sqlite_db_path(),
            provider_key,
            csv_path,
            total_rows=total,
            progress_callback=progress_callback,
        )
        return imported

    def _update_provider_meta(
        self,
        provider_key,
        *,
        cidr_count,
        source_used,
        status,
        error,
        expected_asn_min=None,
        asn_count=None,
        active_asn_count=None,
        anomaly_level=None,
        anomaly_reason=None,
        commit=True,
    ):
        m = _get_models()
        meta = self.db.query(m.ProviderMeta).filter_by(provider_key=provider_key).first()
        if not meta:
            meta = m.ProviderMeta(provider_key=provider_key)
            self.db.add(meta)
        if cidr_count is not None:
            meta.cidr_count = cidr_count
        if source_used is not None:
            meta.source_used = source_used
        if expected_asn_min is not None:
            meta.expected_asn_min = int(expected_asn_min)
        if asn_count is not None:
            meta.asn_count = int(asn_count)
        if active_asn_count is not None:
            meta.active_asn_count = int(active_asn_count)
        if anomaly_level is not None:
            meta.anomaly_level = str(anomaly_level)
        if anomaly_reason is not None:
            meta.anomaly_reason = str(anomaly_reason) if anomaly_reason else None
        meta.refresh_status = status
        meta.refresh_error = error
        meta.last_refreshed_at = datetime.now(timezone.utc)
        if commit:
            self.db.commit()

    def add_custom_provider_entries(
        self,
        provider_key: str,
        *,
        cidrs: list[str] | None = None,
        cidrs_text: str | None = None,
        asns: list[str | int] | None = None,
        triggered_by: str = "manual",
    ) -> dict:
        """Add manual ASN/CIDR entries to CIDR DB for an existing provider key."""
        from app.services.cidr.constants import IP_FILES
        from app.services.cidr.pipeline.constants import CIDR_V4_SCAN_PATTERN
        from app.services.cidr.pipeline.db_extract import _normalize_asn

        key = str(provider_key or "").strip()
        if key not in IP_FILES:
            return {
                "success": False,
                "message": f"Неизвестный провайдер: {key}",
                "provider_key": key,
                "cidrs_added": 0,
                "asns_added": 0,
            }

        parsed_cidrs: list[str] = []
        for raw in cidrs or []:
            value = str(raw or "").strip()
            if value and CIDR_V4_SCAN_PATTERN.search(value):
                match = CIDR_V4_SCAN_PATTERN.search(value)
                if match:
                    parsed_cidrs.append(match.group(0))

        if cidrs_text:
            for line in str(cidrs_text).splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                match = CIDR_V4_SCAN_PATTERN.search(stripped)
                if match:
                    parsed_cidrs.append(match.group(0))

        deduped_cidrs = list(dict.fromkeys(parsed_cidrs))

        parsed_asns: list[int] = []
        for raw in asns or []:
            asn = _normalize_asn(raw)
            if asn is not None:
                parsed_asns.append(asn)
        deduped_asns = list(dict.fromkeys(parsed_asns))

        if not deduped_cidrs and not deduped_asns:
            return {
                "success": False,
                "message": "Укажите хотя бы один CIDR или ASN",
                "provider_key": key,
                "cidrs_added": 0,
                "asns_added": 0,
            }

        m = _get_models()
        now = datetime.now(timezone.utc)
        cidrs_added = 0

        if deduped_cidrs:
            existing_rows = self.cidr_db.query(m.ProviderCidr).filter_by(provider_key=key).all()
            existing_items = [
                {
                    "cidr": row.cidr,
                    "region": row.region_scope,
                    "countries": (
                        [c.strip() for c in row.country_codes.split(",") if c.strip()]
                        if row.country_codes
                        else None
                    ),
                }
                for row in existing_rows
            ]
            existing_set = {item["cidr"] for item in existing_items}
            new_items = [
                {"cidr": cidr, "region": None, "countries": None}
                for cidr in deduped_cidrs
                if cidr not in existing_set
            ]
            if new_items:
                self._upsert_provider_cidrs(
                    key,
                    existing_items + new_items,
                    commit=True,
                    progress_label=f"{key}: custom",
                )
                cidrs_added = len(new_items)

        asns_added = 0
        if deduped_asns:
            before_rows = self.db.query(m.ProviderAsn).filter_by(provider_key=key, active=True).all()
            before_asns = {int(row.asn) for row in before_rows}
            merged_asns = sorted(before_asns | set(deduped_asns))
            asn_rows = self._upsert_provider_asns(key, merged_asns, commit=True)
            for row in asn_rows:
                if int(row.asn) in deduped_asns and row.source != "manual":
                    row.source = "manual"
            self.db.commit()
            after_asns = {int(row.asn) for row in asn_rows if row.active}
            asns_added = len(after_asns - before_asns)

        total_cidrs = int(self.cidr_db.query(m.ProviderCidr).filter_by(provider_key=key).count() or 0)
        active_asn_count = int(
            self.db.query(m.ProviderAsn).filter_by(provider_key=key, active=True).count() or 0
        )
        self._update_provider_meta(
            key,
            cidr_count=total_cidrs,
            source_used="manual",
            status="ok",
            error=None,
            asn_count=active_asn_count,
            active_asn_count=active_asn_count,
            commit=True,
        )

        return {
            "success": True,
            "message": f"Добавлено CIDR: {cidrs_added}, ASN: {asns_added}",
            "provider_key": key,
            "cidrs_added": cidrs_added,
            "asns_added": asns_added,
            "total_cidrs": total_cidrs,
            "active_asn_count": active_asn_count,
            "triggered_by": triggered_by,
        }

    # ── Antifilter.download ────────────────────────────────────────────────

    def refresh_antifilter(self, *, triggered_by="manual", progress_callback=None):
        """Download blocked-in-Russia subnets from antifilter.download and store in DB."""
        import ipaddress
        from datetime import datetime, timezone
        from app.config import get_settings

        m = _get_models()
        ANTIFILTER_URL = get_settings().antifilter_url

        def emit(pct, stage):
            if progress_callback:
                try:
                    progress_callback(pct, stage)
                except Exception:
                    pass

        emit(5, "Подключение к antifilter.download…")
        now = datetime.now(timezone.utc)
        try:
            text = _download_text(ANTIFILTER_URL, timeout=120)
        except Exception as exc:
            meta = self.db.query(m.AntifilterMeta).first() or m.AntifilterMeta()
            meta.refresh_status = "error"
            meta.refresh_error = str(exc)[:500]
            meta.last_refreshed_at = now
            self.db.add(meta)
            self.db.commit()
            return {"success": False, "message": f"Ошибка загрузки антифильтра: {exc}"}

        emit(25, "Парсинг CIDR…")
        cidrs = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                net = ipaddress.ip_network(line, strict=False)
                if net.version == 4 and net.prefixlen > 0:
                    cidrs.append(str(net))
            except ValueError:
                pass

        total = len(cidrs)
        existing_count = self.db.query(m.AntifilterCidr).count()
        if existing_count:
            emit(42, f"Очистка {existing_count} старых записей…")
            self.db.query(m.AntifilterCidr).delete(synchronize_session=False)
            self.db.commit()

        if total == 0:
            emit(90, "Нет CIDR для сохранения")
        else:
            emit(45, f"Сохранение {total} CIDR в БД…")
            batch_size = 1000
            for i in range(0, total, batch_size):
                batch = cidrs[i:i + batch_size]
                self.db.bulk_insert_mappings(m.AntifilterCidr, [{"cidr": c} for c in batch])
                self.db.commit()
                saved = min(i + len(batch), total)
                pct = 45 + int(50 * saved / total)
                emit(pct, f"Сохранено {saved}/{total}")

        from app.services.cidr.pipeline.constants import _ANTIFILTER_INDEX_CACHE

        _ANTIFILTER_INDEX_CACHE["index"] = None
        _ANTIFILTER_INDEX_CACHE["expires_at"] = 0.0

        meta = self.db.query(m.AntifilterMeta).first() or m.AntifilterMeta()
        meta.cidr_count = len(cidrs)
        meta.last_refreshed_at = now
        meta.refresh_status = "ok"
        meta.refresh_error = None
        self.db.add(meta)
        self.db.commit()

        emit(100, f"Антифильтр: {len(cidrs)} заблокированных подсетей")
        logger.info("antifilter refresh OK: %d CIDRs (triggered_by=%s)", len(cidrs), triggered_by)
        return {"success": True, "message": f"Загружено {len(cidrs)} CIDR из antifilter.download", "cidr_count": len(cidrs)}

    def get_antifilter_status(self):
        """Return current antifilter DB status."""
        m = _get_models()
        meta = self.db.query(m.AntifilterMeta).first()
        if not meta:
            return {"cidr_count": 0, "last_refreshed_at": None, "refresh_status": "never", "refresh_error": None}
        return {
            "cidr_count": meta.cidr_count or 0,
            "last_refreshed_at": meta.last_refreshed_at.isoformat() if meta.last_refreshed_at else None,
            "refresh_status": meta.refresh_status or "never",
            "refresh_error": meta.refresh_error,
        }
