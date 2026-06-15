"""Telegram alerts for CIDR pipeline failures."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.admin_notify import admin_notify_service


def _format_deploy_failure_details(result: dict[str, Any]) -> str:
    per_node = result.get("per_node") or []
    failed = [entry for entry in per_node if entry.get("status") == "failed"]
    skipped = [entry for entry in per_node if entry.get("status") == "skipped"]

    parts: list[str] = []
    message = str(result.get("message") or "").strip()
    if message:
        parts.append(message)

    if failed:
        labels = []
        for entry in failed[:5]:
            name = entry.get("node_name") or f"#{entry.get('node_id')}"
            err = str(entry.get("error") or "").strip()
            if err:
                labels.append(f"{name}: {err[:120]}")
            else:
                labels.append(str(name))
        suffix = f" (+{len(failed) - 5})" if len(failed) > 5 else ""
        parts.append(f"Ошибки на {len(failed)} узел(ов): {', '.join(labels)}{suffix}")

    if skipped and not failed:
        labels = [entry.get("node_name") or f"#{entry.get('node_id')}" for entry in skipped[:5]]
        suffix = f" (+{len(skipped) - 5})" if len(skipped) > 5 else ""
        parts.append(f"Пропущено {len(skipped)} узел(ов): {', '.join(labels)}{suffix}")

    deploy_failed = result.get("deploy", {}).get("failed") or []
    if deploy_failed and not failed:
        first = deploy_failed[0]
        parts.append(f"Файл {first.get('file', '?')}: {first.get('error', 'ошибка')}")

    return " · ".join(parts) if parts else "Развёртывание CIDR завершилось с ошибкой"


def _format_ingest_partial_details(result: dict[str, Any]) -> str:
    parts: list[str] = []
    updated = int(result.get("providers_updated") or 0)
    failed = int(result.get("providers_failed") or 0)
    parts.append(f"Обновлено: {updated}, ошибок: {failed}")

    per_provider = result.get("per_provider") or {}
    problem_providers: list[str] = []
    for name, info in per_provider.items():
        if not isinstance(info, dict):
            continue
        status = str(info.get("status") or "")
        if status in ("error", "partial"):
            problem_providers.append(str(name))

    if problem_providers:
        labels = problem_providers[:8]
        suffix = f" (+{len(problem_providers) - 8})" if len(problem_providers) > 8 else ""
        parts.append(f"Проблемные: {', '.join(labels)}{suffix}")

    return " · ".join(parts) if parts else "Обновление CIDR БД завершилось частично"


def maybe_notify_ingest_partial(
    db: Session,
    result: dict[str, Any],
    *,
    triggered_by: str | None = None,
) -> None:
    if result.get("dry_run"):
        return
    if str(result.get("status") or "") != "partial":
        return
    admin_notify_service.send_cidr_ingest_partial(
        db,
        details=_format_ingest_partial_details(result),
        actor_username=triggered_by,
    )


def maybe_notify_deploy_failed(
    db: Session,
    result: dict[str, Any],
    *,
    triggered_by: str | None = None,
) -> None:
    if bool(result.get("success")):
        return
    admin_notify_service.send_cidr_deploy_failed(
        db,
        details=_format_deploy_failure_details(result),
        actor_username=triggered_by,
    )


def _format_rollback_failure_details(result: dict[str, Any]) -> str:
    parts: list[str] = []
    message = str(result.get("message") or "").strip()
    if message:
        parts.append(message)
    missing = result.get("missing") or []
    if missing:
        parts.append(f"Не найдено: {', '.join(missing[:5])}")
    deploy = result.get("deploy") or {}
    failed = deploy.get("failed") or []
    if failed:
        first = failed[0]
        parts.append(f"Deploy {first.get('file', '?')}: {first.get('error', 'ошибка')}")
    return " · ".join(parts) if parts else "Откат CIDR завершился с ошибкой"


def maybe_notify_rollback_failed(
    db: Session,
    result: dict[str, Any],
    *,
    triggered_by: str | None = None,
) -> None:
    if bool(result.get("success")):
        return
    admin_notify_service.send_cidr_rollback_failed(
        db,
        details=_format_rollback_failure_details(result),
        actor_username=triggered_by,
    )
