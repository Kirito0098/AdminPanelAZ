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
_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="bg-task")

_PIPELINE_TASK_TYPES = {
    "cidr_db_refresh",
    "cidr_db_refresh_dry_run",
    "cidr_estimate_from_db",
    "cidr_generate_from_db",
    "cidr_deploy",
    "antifilter_refresh",
    "config_bulk_op",
    "config_csv_import",
    "node_sync_push_full",
    "node_sync_shared_domain",
    "node_update_roll",
}

_TASK_START_PROGRESS: dict[str, tuple[str, str, int]] = {
    "run_doall": ("AntiZapret: применение изменений…", "AntiZapret: запуск doall.sh…", 5),
    "routing_apply": ("Применение маршрутизации…", "Синхронизация провайдеров…", 5),
    "routing_apply_replica": ("Применение маршрутизации на replica…", "Синхронизация провайдеров…", 5),
    "restart_service": ("Перезапуск службы…", "Перезапуск службы…", 10),
    "update_system": ("Обновление кода и зависимостей…", "Обновление: проверка репозитория…", 5),
    "rebuild_frontend": ("Пересборка интерфейса…", "npm run build:all…", 10),
    "cidr_db_refresh": ("Обновление CIDR БД…", "Подготовка обновления провайдеров…", 3),
    "cidr_db_refresh_dry_run": ("Пробный прогон CIDR БД…", "Подготовка обновления провайдеров…", 3),
    "cidr_estimate_from_db": ("Оценка CIDR из БД…", "Подготовка оценки…", 3),
    "cidr_generate_from_db": ("Генерация CIDR из БД…", "Подготовка генерации…", 3),
    "cidr_deploy": ("Развёртывание CIDR на узел…", "Подготовка развёртывания…", 3),
    "antifilter_refresh": ("Обновление Antifilter…", "Подготовка Antifilter…", 3),
    "vpn_network_publish": ("Публикация панели…", "Запуск nginx-setup.sh…", 5),
    "config_bulk_op": ("Массовая операция с клиентами…", "Подготовка…", 3),
    "config_csv_import": ("Импорт CSV клиентов…", "Подготовка импорта…", 3),
    "node_sync_push_full": ("Синхронизация HA…", "Подготовка push-full…", 5),
    "node_sync_shared_domain": ("Применение shared domain…", "Запись хостов в setup…", 5),
    "node_update_roll": ("Rolling update узлов…", "Подготовка очереди…", 3),
}

_TASK_DONE_PROGRESS: dict[str, str] = {
    "run_doall": "AntiZapret: изменения применены",
    "routing_apply": "Маршрутизация применена",
    "routing_apply_replica": "Маршрутизация на replica применена",
    "restart_service": "Служба перезапущена",
    "update_system": "Обновление завершено",
    "rebuild_frontend": "Пересборка завершена",
    "cidr_db_refresh": "CIDR БД обновлена",
    "cidr_db_refresh_dry_run": "Пробный прогон завершён",
    "cidr_estimate_from_db": "Оценка завершена",
    "cidr_generate_from_db": "Генерация завершена",
    "cidr_deploy": "Развёртывание завершено",
    "antifilter_refresh": "Antifilter обновлён",
    "vpn_network_publish": "Публикация панели завершена",
    "config_bulk_op": "Массовая операция завершена",
    "config_csv_import": "Импорт CSV завершён",
    "node_sync_push_full": "Синхронизация HA завершена",
    "node_sync_shared_domain": "Shared domain применён на узлах",
    "node_update_roll": "Rolling update завершён",
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
        if task_type == "vpn_network_publish" and output:
            try:
                parsed = json.loads(output)
            except (TypeError, ValueError, json.JSONDecodeError):
                return None
            return parsed if isinstance(parsed, dict) else None
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

    def recover_stale_running_tasks(self) -> int:
        """Mark orphaned running/queued tasks as failed after process restart."""
        db = SessionLocal()
        try:
            stale = (
                db.query(BackgroundTask)
                .filter(BackgroundTask.status.in_(["queued", "running"]))
                .all()
            )
            if not stale:
                return 0
            now = datetime.now(timezone.utc)
            for task in stale:
                task.status = "failed"
                task.finished_at = now
                task.progress_percent = 100
                task.progress_stage = "Прервано перезапуском панели"
                task.message = "Задача прервана перезапуском панели"
                task.error = "Задача прервана перезапуском панели"
            self._commit_with_retry(db)
            return len(stale)
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
            elif task_type == "vpn_network_publish" and isinstance(result, dict):
                output_value = json.dumps(
                    {
                        "log": result.get("log", result.get("output", "")),
                        "panel_restarted": bool(result.get("panel_restarted")),
                        "requires_manual_restart": bool(result.get("requires_manual_restart")),
                        "restart_command": str(result.get("restart_command") or ""),
                        "resolved_ssl_cert": str(result.get("resolved_ssl_cert") or ""),
                        "resolved_ssl_key": str(result.get("resolved_ssl_key") or ""),
                        "access_url": str(result.get("access_url") or ""),
                        "publish_mode": str(result.get("publish_mode") or ""),
                    },
                    ensure_ascii=False,
                )
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

    def task_run_doall(
        self,
        adapter,
        progress_updater: Callable[[int, str, str | None], None] | None = None,
        *,
        recreate_profiles: bool = True,
    ) -> dict[str, str]:
        if progress_updater:
            progress_updater(10, "AntiZapret: запуск doall.sh…")
        try:
            doall_output = adapter.apply_config_changes()
        except Exception as exc:
            raise self._adapter_error(exc) from exc
        recreate_output = ""
        if recreate_profiles:
            if progress_updater:
                progress_updater(65, "AntiZapret: пересоздание профилей клиентов…")
            try:
                recreate_output = adapter.recreate_profiles()
            except Exception as exc:
                raise self._adapter_error(exc) from exc
        combined = "\n".join(part for part in [doall_output, recreate_output] if part).strip()
        return {
            "message": (
                "doall и пересоздание профилей клиентов выполнены успешно"
                if recreate_profiles
                else "doall выполнен успешно (профили не пересоздавались)"
            ),
            "output": combined,
        }

    def task_routing_apply(
        self,
        adapter,
        progress_updater: Callable[[int, str, str | None], None] | None = None,
        *,
        recreate_profiles: bool = True,
    ) -> dict[str, str]:
        if progress_updater:
            progress_updater(5, "Синхронизация провайдеров…")
        try:
            sync_output = adapter.sync_cidr_providers()
        except Exception as exc:
            raise self._adapter_error(exc) from exc
        sync_text = json.dumps(sync_output, ensure_ascii=False) if isinstance(sync_output, dict) else str(sync_output or "")
        result = self.task_run_doall(adapter, progress_updater, recreate_profiles=recreate_profiles)
        combined = "\n".join(part for part in [sync_text, result.get("output", "")] if part).strip()
        return {
            "message": "Маршрутизация применена (doall.sh)",
            "output": combined,
        }

    def make_routing_apply_for_node_callable(
        self,
        node_id: int,
        *,
        recreate_profiles: bool = True,
    ) -> BackgroundTaskCallable:
        captured_node_id = int(node_id)
        captured_recreate = bool(recreate_profiles)

        def _callable(progress_updater: Callable[[int, str, str | None], None] | None = None) -> dict[str, str]:
            from app.models import Node
            from app.services.node_manager import get_adapter_for_node

            db = SessionLocal()
            try:
                node = db.get(Node, captured_node_id)
                if node is None:
                    raise RuntimeError(f"Node {captured_node_id} not found")

                node_label = node.name or str(captured_node_id)

                def _node_progress(percent: int, stage: str, message: str | None = None) -> None:
                    if not progress_updater:
                        return
                    staged = f"{node_label}: {stage}" if stage else node_label
                    msg = f"{node_label}: {message}" if message else None
                    progress_updater(percent, staged, msg)

                adapter = get_adapter_for_node(node)
                result = self.task_routing_apply(
                    adapter, _node_progress, recreate_profiles=captured_recreate
                )
                result["message"] = f"{node_label}: {result.get('message', 'Маршрутизация применена')}"
                result["output"] = json.dumps(
                    {
                        "node_id": captured_node_id,
                        "node_name": node.name,
                        "log": result.get("output", ""),
                    },
                    ensure_ascii=False,
                )
                return result
            finally:
                db.close()

        return _callable

    def task_update_system(self, progress_updater: Callable[[int, str, str | None], None] | None = None) -> dict[str, str]:
        from app.services.system_update import apply_controller_update

        def _progress(percent: int, stage: str) -> None:
            if progress_updater:
                progress_updater(percent, stage)

        result = apply_controller_update(repo_root=PROJECT_ROOT, progress=_progress)
        if not result.get("success"):
            error_text = "; ".join(result.get("errors") or []) or "Обновление не выполнено"
            raise RuntimeError(error_text)
        return {
            "message": str(result.get("message") or "Обновление применено"),
            "output": str(result.get("output") or ""),
        }

    def task_rebuild_frontend(self, progress_updater: Callable[[int, str, str | None], None] | None = None) -> dict[str, str]:
        from app.services.system_update import apply_controller_rebuild

        def _progress(percent: int, stage: str) -> None:
            if progress_updater:
                progress_updater(percent, stage)

        result = apply_controller_rebuild(repo_root=PROJECT_ROOT, progress=_progress)
        if not result.get("success"):
            error_text = "; ".join(result.get("errors") or []) or "Пересборка не выполнена"
            raise RuntimeError(error_text)
        return {
            "message": str(result.get("message") or "Frontend пересобран"),
            "output": str(result.get("output") or ""),
        }

    def task_vpn_network_publish(
        self,
        payload: dict[str, object],
        progress_updater: Callable[[int, str, str | None], None] | None = None,
    ) -> dict[str, str | bool]:
        from app.services.env_file import EnvFileService
        from app.services.panel_publish_info import panel_restart_command, resolve_publish_ssl_paths
        from app.services.system_update import _systemd_unit_installed, schedule_controller_restart

        mode_flags = {
            "http_direct": "--http",
            "nginx_le": "--nginx-le",
            "nginx_selfsigned": "--nginx-selfsigned",
            "nginx_custom": "--nginx-custom",
            "uvicorn_le": "--uvicorn-le",
            "uvicorn_selfsigned": "--uvicorn-selfsigned",
            "uvicorn_custom": "--uvicorn-custom",
        }
        mode = str(payload.get("mode") or "")
        flag = mode_flags.get(mode)
        if not flag:
            raise RuntimeError(f"Неизвестный режим публикации: {mode}")

        uvicorn_modes = {"uvicorn_le", "uvicorn_selfsigned", "uvicorn_custom"}
        backend_port = int(payload.get("backend_port") or 8000)
        domain = str(payload.get("domain") or "").strip()
        ssl_cert = str(payload.get("ssl_cert") or "").strip()
        ssl_key = str(payload.get("ssl_key") or "").strip()
        resolved_cert = ssl_cert
        resolved_key = ssl_key

        env_path = APP_ROOT / ".env"
        env = EnvFileService(env_path)
        if mode in {"nginx_custom", "uvicorn_custom"}:
            resolved_cert, resolved_key = resolve_publish_ssl_paths(
                ssl_cert=ssl_cert or None,
                ssl_key=ssl_key or None,
                domain=domain or None,
                get_env_value=env.get_env_value,
            )

        if progress_updater:
            progress_updater(10, "Подготовка nginx-setup.sh…")

        cmd_env: dict[str, str] = {
            "NON_INTERACTIVE": "true",
            "SKIP_PANEL_RESTART": "true",
            "BACKEND_PORT": str(backend_port),
            "HTTPS_PUBLIC_PORT": str(
                backend_port if mode in uvicorn_modes else (payload.get("https_public_port") or 443)
            ),
            "HTTP_ACME_PORT": str(payload.get("http_acme_port") or 80),
        }
        if domain:
            cmd_env["DOMAIN"] = domain
        email = payload.get("email")
        if email:
            cmd_env["EMAIL"] = str(email)
        if resolved_cert:
            cmd_env["SSL_CERT"] = resolved_cert
        if resolved_key:
            cmd_env["SSL_KEY"] = resolved_key
        access_path = str(payload.get("access_path") or "").strip()
        # Явно передаём ACCESS_PATH (в т.ч. пустой), чтобы сбросить подпуть в .env.
        cmd_env["ACCESS_PATH"] = access_path
        if payload.get("nginx_subpath_integrate"):
            cmd_env["NGINX_SUBPATH_INTEGRATE"] = "true"

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

        restart_cmd = panel_restart_command()
        panel_restarted = False
        requires_manual_restart = True

        if progress_updater:
            progress_updater(90, "Перезапуск панели…")

        if _systemd_unit_installed() or (PROJECT_ROOT / "start.sh").is_file():
            schedule_controller_restart(PROJECT_ROOT)
            panel_restarted = True
            requires_manual_restart = False

        log_output = "\n".join(part for part in [stdout, stderr] if part).strip()
        access_url = ""
        for line in log_output.splitlines():
            if "ACCESS_URL=" in line:
                access_url = line.split("ACCESS_URL=", 1)[-1].strip()
                break

        mode_labels = {
            "http_direct": "Прямой HTTP · Uvicorn",
            "nginx_le": "Let's Encrypt · Nginx",
            "nginx_selfsigned": "Самоподписанный SSL · Nginx",
            "nginx_custom": "Собственные сертификаты · Nginx",
            "uvicorn_le": "Let's Encrypt · Uvicorn",
            "uvicorn_selfsigned": "Самоподписанный SSL · Uvicorn",
            "uvicorn_custom": "Собственные сертификаты · Uvicorn",
        }
        message = f"Публикация применена: {mode_labels.get(mode, mode)}"
        if access_url:
            message += f". Откройте: {access_url}"
        if panel_restarted:
            message += ". Панель перезапускается через несколько секунд"
        elif requires_manual_restart:
            message += f". Перезапустите панель: {restart_cmd}"

        return {
            "message": message,
            "log": log_output,
            "panel_restarted": panel_restarted,
            "requires_manual_restart": requires_manual_restart,
            "restart_command": restart_cmd,
            "resolved_ssl_cert": resolved_cert,
            "resolved_ssl_key": resolved_key,
            "access_url": access_url,
            "publish_mode": mode,
        }

    def start_cidr_runner(self, task_id: str, runner: Callable) -> None:
        progress_lock = threading.Lock()
        progress_state = {"last_at": 0.0, "last_pct": -1, "last_stage": ""}

        def _progress_callback(percent: int, stage: str) -> None:
            pct = max(0, min(99, int(percent)))
            stage_str = str(stage or "Выполняется операция…")
            now = time.monotonic()
            skip_percent = False
            with progress_lock:
                stage_changed = stage_str != progress_state["last_stage"]
                if (
                    pct < 99
                    and not stage_changed
                    and (now - progress_state["last_at"]) < 1.5
                    and pct <= progress_state["last_pct"] + 1
                ):
                    return
                if (
                    pct < 99
                    and (now - progress_state["last_at"]) < 1.5
                    and pct <= progress_state["last_pct"] + 1
                ):
                    skip_percent = True
                progress_state["last_at"] = now
                progress_state["last_stage"] = stage_str
                if not skip_percent:
                    progress_state["last_pct"] = pct

            fields: dict[str, Any] = {
                "status": "running",
                "progress_stage": stage_str,
                "message": stage_str,
            }
            if not skip_percent:
                fields["progress_percent"] = pct
            self.update_background_task(task_id, **fields)

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

        self.update_background_task(
            task_id,
            status="running",
            progress_percent=1,
            progress_stage="Запуск фоновой задачи…",
            started_at=datetime.now(timezone.utc),
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
