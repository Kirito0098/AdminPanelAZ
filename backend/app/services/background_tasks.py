"""Unified background task queue with DB-backed progress tracking."""

from __future__ import annotations

import inspect
import json
import logging
import os
import secrets
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from fastapi import HTTPException
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import BackgroundTask

logger = logging.getLogger(__name__)

APP_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = APP_ROOT.parent
MAX_OUTPUT_CHARS = 50_000
_COMMIT_RETRY_ATTEMPTS = 5
_COMMIT_RETRY_DELAY_SEC = 0.1
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bg-task")

_PIPELINE_TASK_TYPES = {
    "pytest_run",
    "cidr_db_refresh",
    "cidr_db_refresh_dry_run",
    "cidr_estimate_from_db",
    "cidr_generate_from_db",
    "cidr_deploy",
    "antifilter_refresh",
}

_TASK_START_PROGRESS: dict[str, tuple[str, str, int]] = {
    "run_doall": ("AntiZapret: применение изменений…", "AntiZapret: запуск doall.sh…", 5),
    "routing_apply": ("Применение маршрутизации…", "Синхронизация провайдеров…", 5),
    "restart_service": ("Перезапуск службы…", "Перезапуск службы…", 10),
    "update_system": ("Обновление кода и зависимостей…", "Обновление: проверка репозитория…", 5),
    "pytest_run": ("Запуск тестов…", "Подготовка pytest…", 5),
    "cidr_db_refresh": ("Обновление CIDR БД…", "Подготовка обновления провайдеров…", 3),
    "cidr_db_refresh_dry_run": ("Пробный прогон CIDR БД…", "Подготовка обновления провайдеров…", 3),
    "cidr_estimate_from_db": ("Оценка CIDR из БД…", "Подготовка оценки…", 3),
    "cidr_generate_from_db": ("Генерация CIDR из БД…", "Подготовка генерации…", 3),
    "cidr_deploy": ("Развёртывание CIDR на ноду…", "Подготовка развёртывания…", 3),
    "antifilter_refresh": ("Обновление Antifilter…", "Подготовка Antifilter…", 3),
    "vpn_network_publish": ("Публикация панели…", "Запуск nginx-setup.sh…", 5),
}

_TASK_DONE_PROGRESS: dict[str, str] = {
    "run_doall": "AntiZapret: изменения применены",
    "routing_apply": "Маршрутизация применена",
    "restart_service": "Служба перезапущена",
    "update_system": "Обновление завершено",
    "pytest_run": "Тесты завершены",
    "cidr_db_refresh": "CIDR БД обновлена",
    "cidr_db_refresh_dry_run": "Пробный прогон завершён",
    "cidr_estimate_from_db": "Оценка завершена",
    "cidr_generate_from_db": "Генерация завершена",
    "cidr_deploy": "Развёртывание завершено",
    "antifilter_refresh": "Antifilter обновлён",
    "vpn_network_publish": "Публикация панели завершена",
}


class BackgroundTaskCallable(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        ...


class BackgroundTaskService:
    def _commit_with_retry(self, db: Session) -> None:
        for attempt in range(_COMMIT_RETRY_ATTEMPTS):
            try:
                db.commit()
                return
            except OperationalError as exc:
                if "database is locked" not in str(exc).lower() or attempt == _COMMIT_RETRY_ATTEMPTS - 1:
                    raise
                time.sleep(_COMMIT_RETRY_DELAY_SEC * (attempt + 1))

    def trim_background_task_text(self, value: str | None) -> str:
        text = (value or "").strip()
        if len(text) <= MAX_OUTPUT_CHARS:
            return text
        return text[:MAX_OUTPUT_CHARS] + "\n...[truncated]"

    def _parse_result_from_output(self, task_type: str, output: str | None) -> dict[str, Any] | None:
        if task_type not in _PIPELINE_TASK_TYPES or not output:
            return None
        try:
            parsed = json.loads(output)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    def serialize_background_task(self, task: BackgroundTask | dict[str, Any]) -> dict[str, Any]:
        if isinstance(task, dict):
            payload = dict(task)
            task_type = str(payload.get("task_type") or "")
            output = payload.get("output")
        else:
            task_type = task.task_type
            output = task.output
            payload = {
                "task_id": task.id,
                "task_type": task.task_type,
                "status": task.status,
                "message": task.message,
                "output": task.output,
                "error": task.error,
                "progress_percent": task.progress_percent or 0,
                "progress_stage": task.progress_stage,
                "created_at": task.created_at,
                "started_at": task.started_at,
                "finished_at": task.finished_at,
            }

        payload["progress_percent"] = int(payload.get("progress_percent") or 0)
        for key in ("created_at", "started_at", "finished_at", "updated_at"):
            value = payload.get(key)
            payload[key] = value.isoformat() if isinstance(value, datetime) else value

        result = self._parse_result_from_output(task_type, output if isinstance(output, str) else None)
        payload["result"] = result
        return payload

    def update_background_task(self, task_id: str, **fields: Any) -> None:
        db = SessionLocal()
        try:
            task = db.get(BackgroundTask, task_id)
            if not task:
                return
            for key, value in fields.items():
                if key == "message" and isinstance(value, str):
                    value = value[:255]
                if key == "progress_stage" and isinstance(value, str):
                    value = value[:255]
                setattr(task, key, value)
            self._commit_with_retry(db)
        finally:
            db.close()

    def get_task(self, task_id: str) -> BackgroundTask | None:
        db = SessionLocal()
        try:
            return db.get(BackgroundTask, task_id)
        finally:
            db.close()

    def find_active_task(self, task_type: str) -> BackgroundTask | None:
        db = SessionLocal()
        try:
            return (
                db.query(BackgroundTask)
                .filter(
                    BackgroundTask.task_type == task_type,
                    BackgroundTask.status.in_(["queued", "running"]),
                )
                .order_by(BackgroundTask.created_at.desc())
                .first()
            )
        finally:
            db.close()

    def find_last_completed_task(self, task_type: str) -> BackgroundTask | None:
        db = SessionLocal()
        try:
            return (
                db.query(BackgroundTask)
                .filter(
                    BackgroundTask.task_type == task_type,
                    BackgroundTask.status.in_(["completed", "failed"]),
                )
                .order_by(BackgroundTask.finished_at.desc())
                .first()
            )
        finally:
            db.close()

    def create_queued_task(
        self,
        task_type: str,
        message: str,
        *,
        created_by_username: str | None = None,
    ) -> str:
        task_id = secrets.token_hex(16)
        db = SessionLocal()
        try:
            task = BackgroundTask(
                id=task_id,
                task_type=task_type,
                status="queued",
                created_by_username=created_by_username,
                message=(message or "Задача поставлена в очередь")[:255],
                progress_percent=0,
                progress_stage="Ожидание запуска задачи…",
            )
            db.add(task)
            self._commit_with_retry(db)
            return task_id
        finally:
            db.close()

    def _task_start_progress(self, task_type: str) -> tuple[str, str, int]:
        return _TASK_START_PROGRESS.get(task_type, ("Задача выполняется…", "Запуск…", 5))

    def _task_done_stage(self, task_type: str) -> str:
        return _TASK_DONE_PROGRESS.get(task_type, "Готово")

    def _make_progress_updater(self, task_id: str) -> Callable[[int, str, str | None], None]:
        def updater(percent: int, stage: str, message: str | None = None) -> None:
            fields: dict[str, Any] = {
                "status": "running",
                "progress_percent": max(0, min(99, int(percent))),
                "progress_stage": str(stage or "").strip()[:255] or None,
            }
            if message:
                fields["message"] = str(message).strip()[:255]
            self.update_background_task(task_id, **fields)

        return updater

    def _invoke_task_callable(
        self,
        task_callable: BackgroundTaskCallable,
        progress_updater: Callable[[int, str, str | None], None],
    ) -> dict[str, Any]:
        try:
            signature = inspect.signature(task_callable)
        except (TypeError, ValueError):
            signature = None

        if signature is not None and "progress_updater" in signature.parameters:
            return task_callable(progress_updater=progress_updater) or {}

        return task_callable() or {}

    def run_background_task(self, task_id: str, task_callable: BackgroundTaskCallable) -> None:
        db = SessionLocal()
        try:
            task = db.get(BackgroundTask, task_id)
            task_type = str(getattr(task, "task_type", "") or "")
        finally:
            db.close()

        running_message, starting_stage, starting_percent = self._task_start_progress(task_type)
        progress_updater = self._make_progress_updater(task_id)

        self.update_background_task(
            task_id,
            status="running",
            started_at=datetime.now(timezone.utc),
            message=running_message,
            progress_percent=starting_percent,
            progress_stage=starting_stage,
        )

        try:
            result = self._invoke_task_callable(task_callable, progress_updater)
            done_stage = self._task_done_stage(task_type)
            output_value = result.get("output", "")
            if task_type in _PIPELINE_TASK_TYPES and isinstance(result, dict) and "success" in result:
                output_value = json.dumps(result, ensure_ascii=False)
            self.update_background_task(
                task_id,
                status="completed",
                finished_at=datetime.now(timezone.utc),
                message=str(result.get("message") or running_message)[:255],
                output=self.trim_background_task_text(
                    output_value if isinstance(output_value, str) else str(output_value or "")
                ),
                error=None,
                progress_percent=100,
                progress_stage=done_stage,
            )
        except Exception as exc:
            logger.exception("Background task %s failed: %s", task_id, exc)
            self.update_background_task(
                task_id,
                status="failed",
                finished_at=datetime.now(timezone.utc),
                message="Задача завершилась с ошибкой",
                error=self.trim_background_task_text(str(exc)),
                progress_percent=100,
                progress_stage="Ошибка выполнения",
            )

    def enqueue_background_task(
        self,
        task_type: str,
        task_callable: BackgroundTaskCallable,
        *,
        created_by_username: str | None = None,
        queued_message: str | None = None,
    ) -> BackgroundTask:
        task_id = self.create_queued_task(
            task_type,
            queued_message or "Задача поставлена в очередь",
            created_by_username=created_by_username,
        )
        _EXECUTOR.submit(self.run_background_task, task_id, task_callable)
        task = self.get_task(task_id)
        if task is None:
            raise RuntimeError("Failed to create background task")
        return task

    def run_checked_command(
        self,
        args: list[str],
        cwd: str | Path | None = None,
        timeout: int = 120,
        env: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        result = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=run_env,
        )
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        if result.returncode != 0:
            raise RuntimeError(
                f"Команда {' '.join(args)} завершилась с кодом {result.returncode}. {stderr or stdout}"
            )
        return stdout, stderr

    def _adapter_error(self, exc: Exception) -> RuntimeError:
        if isinstance(exc, HTTPException):
            detail = exc.detail
            if isinstance(detail, list):
                detail = "; ".join(str(item) for item in detail)
            return RuntimeError(str(detail or "Ошибка операции"))
        return RuntimeError(str(exc))

    def task_run_doall(self, adapter, progress_updater: Callable[[int, str, str | None], None] | None = None) -> dict[str, str]:
        if progress_updater:
            progress_updater(10, "AntiZapret: запуск doall.sh…")
        try:
            doall_output = adapter.apply_config_changes()
        except Exception as exc:
            raise self._adapter_error(exc) from exc
        if progress_updater:
            progress_updater(65, "AntiZapret: пересоздание профилей клиентов…")
        try:
            recreate_output = adapter.recreate_profiles()
        except Exception as exc:
            raise self._adapter_error(exc) from exc
        combined = "\n".join(part for part in [doall_output, recreate_output] if part).strip()
        return {
            "message": "doall и пересоздание профилей клиентов выполнены успешно",
            "output": combined,
        }

    def task_routing_apply(self, adapter, progress_updater: Callable[[int, str, str | None], None] | None = None) -> dict[str, str]:
        if progress_updater:
            progress_updater(5, "Синхронизация провайдеров…")
        try:
            sync_output = adapter.sync_cidr_providers()
        except Exception as exc:
            raise self._adapter_error(exc) from exc
        sync_text = json.dumps(sync_output, ensure_ascii=False) if isinstance(sync_output, dict) else str(sync_output or "")
        result = self.task_run_doall(adapter, progress_updater)
        combined = "\n".join(part for part in [sync_text, result.get("output", "")] if part).strip()
        return {
            "message": "Маршрутизация применена (doall.sh)",
            "output": combined,
        }

    def task_update_system(self, progress_updater: Callable[[int, str, str | None], None] | None = None) -> dict[str, str]:
        output_parts: list[str] = []
        if progress_updater:
            progress_updater(15, "Обновление: проверка репозитория…")
        fetch_stdout, fetch_stderr = self.run_checked_command(
            ["git", "fetch", "origin"],
            cwd=APP_ROOT,
            timeout=90,
        )
        output_parts.extend([part for part in [fetch_stdout, fetch_stderr] if part])
        if progress_updater:
            progress_updater(60, "Обновление: git pull origin main…")
        pull_stdout, pull_stderr = self.run_checked_command(
            ["git", "pull", "origin", "main"],
            cwd=APP_ROOT,
            timeout=120,
        )
        output_parts.extend([part for part in [pull_stdout, pull_stderr] if part])
        return {
            "message": "Обновление применено",
            "output": "\n".join(output_parts).strip(),
        }

    def task_vpn_network_publish(
        self,
        payload: dict[str, object],
        progress_updater: Callable[[int, str, str | None], None] | None = None,
    ) -> dict[str, str]:
        mode_flags = {
            "http_direct": "--http",
            "nginx_le": "--nginx-le",
            "nginx_selfsigned": "--nginx-selfsigned",
        }
        mode = str(payload.get("mode") or "")
        flag = mode_flags.get(mode)
        if not flag:
            raise RuntimeError(f"Неизвестный режим публикации: {mode}")

        if progress_updater:
            progress_updater(10, "Подготовка nginx-setup.sh…")

        cmd_env: dict[str, str] = {
            "NON_INTERACTIVE": "true",
            "BACKEND_PORT": str(payload.get("backend_port") or 8000),
            "HTTPS_PUBLIC_PORT": str(payload.get("https_public_port") or 443),
            "HTTP_ACME_PORT": str(payload.get("http_acme_port") or 80),
        }
        domain = payload.get("domain")
        if domain:
            cmd_env["DOMAIN"] = str(domain)
        email = payload.get("email")
        if email:
            cmd_env["EMAIL"] = str(email)

        script = PROJECT_ROOT / "scripts" / "nginx-setup.sh"
        if not script.is_file():
            raise RuntimeError(f"Скрипт не найден: {script}")

        if progress_updater:
            progress_updater(25, f"Запуск nginx-setup.sh {flag}…")

        stdout, stderr = self.run_checked_command(
            ["bash", str(script), "--non-interactive", flag],
            cwd=PROJECT_ROOT,
            timeout=600,
            env=cmd_env,
        )

        if progress_updater:
            progress_updater(95, "Перезапуск панели…")

        output = "\n".join(part for part in [stdout, stderr] if part).strip()
        mode_labels = {
            "http_direct": "Прямой HTTP",
            "nginx_le": "Nginx + Let's Encrypt",
            "nginx_selfsigned": "Nginx + самоподписанный SSL",
        }
        return {
            "message": f"Публикация применена: {mode_labels.get(mode, mode)}",
            "output": output,
        }

    def start_cidr_runner(self, task_id: str, runner: Callable) -> None:
        progress_lock = threading.Lock()
        progress_state = {"last_at": 0.0, "last_pct": -1}

        def _progress_callback(percent: int, stage: str) -> None:
            pct = max(0, min(99, int(percent)))
            stage_str = str(stage or "Выполняется операция…")
            now = time.monotonic()
            with progress_lock:
                if pct < 99 and (now - progress_state["last_at"]) < 0.5 and pct <= progress_state["last_pct"] + 1:
                    return
                progress_state["last_at"] = now
                progress_state["last_pct"] = pct
            self.update_background_task(
                task_id,
                status="running",
                progress_percent=pct,
                progress_stage=stage_str,
                message=stage_str,
            )

        def _worker() -> None:
            self.update_background_task(
                task_id,
                status="running",
                progress_percent=1,
                progress_stage="Подготовка к выполнению…",
                started_at=datetime.now(timezone.utc),
            )
            try:
                result = runner(_progress_callback) or {}
                if not bool(result.get("success")):
                    self.update_background_task(
                        task_id,
                        status="failed",
                        progress_percent=100,
                        progress_stage="Операция завершилась с ошибкой",
                        message=str(result.get("message") or "Операция завершилась с ошибкой")[:255],
                        error=str(result.get("message") or "Операция завершилась с ошибкой"),
                        output=json.dumps(result, ensure_ascii=False),
                        finished_at=datetime.now(timezone.utc),
                    )
                    return
                self.update_background_task(
                    task_id,
                    status="completed",
                    progress_percent=100,
                    progress_stage="Операция успешно завершена",
                    message=str(result.get("message") or "Операция завершена")[:255],
                    error=None,
                    output=json.dumps(result, ensure_ascii=False),
                    finished_at=datetime.now(timezone.utc),
                )
            except Exception as exc:
                logger.exception("CIDR background task failed (%s): %s", task_id, exc)
                self.update_background_task(
                    task_id,
                    status="failed",
                    progress_percent=100,
                    progress_stage="Операция завершилась с ошибкой",
                    message="Операция завершилась с ошибкой",
                    error=str(exc),
                    finished_at=datetime.now(timezone.utc),
                )

        _EXECUTOR.submit(_worker)

    def build_accepted_payload(self, task: BackgroundTask, message: str) -> dict[str, Any]:
        payload = self.serialize_background_task(task)
        payload.update(
            {
                "success": True,
                "queued": True,
                "message": message,
                "status_url": f"/api/tasks/{task.id}",
            }
        )
        return payload


background_task_service = BackgroundTaskService()
