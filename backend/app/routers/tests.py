"""In-panel pytest runner (ported from AdminAntizapret settings/api_tests.py)."""

import os
import re
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.services.cidr.cidr_tasks import (
    create_cidr_task,
    find_active_cidr_task,
    serialize_cidr_task,
    start_cidr_task,
)

router = APIRouter(prefix="/tests", tags=["tests"])
APP_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = APP_ROOT / "tests"
NODEID_RE = re.compile(r"^tests/[\w./-]+(::[\w\[\].\-]+)*$")


class RunTestsRequest(BaseModel):
    test_ids: list[str] = []


def _pytest_bin() -> str:
    venv_pytest = APP_ROOT / ".venv" / "bin" / "pytest"
    if venv_pytest.is_file():
        return str(venv_pytest)
    return "pytest"


@router.get("/collect")
def collect_tests(_: User = Depends(require_admin)):
    tests_dir = str(TESTS_DIR)
    if not TESTS_DIR.is_dir():
        return {"success": True, "tests": [], "count": 0}
    try:
        proc = subprocess.run(
            [_pytest_bin(), "--collect-only", "-q", "--no-header", tests_dir],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(APP_ROOT),
        )
        lines = (proc.stdout + proc.stderr).strip().splitlines()
        tests: list[str] = []
        seen: set[str] = set()
        for line in lines:
            stripped = line.strip()
            if "::" not in stripped or stripped.startswith("="):
                continue
            if stripped not in seen:
                seen.add(stripped)
                tests.append(stripped)
        if proc.returncode != 0 and not tests:
            err = (proc.stderr or proc.stdout or "").strip() or f"pytest exit {proc.returncode}"
            raise HTTPException(status_code=500, detail=err)
        tests.sort()
        enriched = [{"id": t, "title": t.split("::")[-1], "description": t} for t in tests]
        return {
            "success": True,
            "tests": enriched,
            "count": len(tests),
            "collect_warnings": proc.returncode != 0,
        }
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="Таймаут сбора тестов") from exc


@router.post("/run")
def run_tests(payload: RunTestsRequest, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    for tid in payload.test_ids:
        if tid.startswith("-") or ".." in tid or not NODEID_RE.fullmatch(tid):
            raise HTTPException(status_code=400, detail=f"Недопустимый идентификатор теста: {tid}")

    active = find_active_cidr_task("pytest_run")
    if active:
        return {
            "success": True,
            "queued": True,
            "task_id": active.get("task_id"),
            "message": "Тесты уже выполняются",
        }

    task_id = create_cidr_task("pytest_run", "Запуск тестов...")
    test_ids = list(payload.test_ids)

    def _runner(progress_callback):
        progress_callback(5, "Запуск pytest...")
        cmd = [_pytest_bin(), "-v", "--tb=short", "--no-header", "--color=no"]
        if test_ids:
            cmd.extend(test_ids)
        else:
            cmd.append(str(TESTS_DIR))
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=str(APP_ROOT))
            output = proc.stdout + (proc.stderr or "")
            progress_callback(90, "Разбор результатов...")
            tests_result = []
            passed = failed = errors = skipped = 0
            for line in output.splitlines():
                stripped = line.strip()
                if "::" not in stripped:
                    continue
                if " PASSED" in stripped:
                    test_id = stripped.split(" PASSED")[0].strip()
                    tests_result.append({"id": test_id, "title": test_id.split("::")[-1], "status": "passed"})
                    passed += 1
                elif " FAILED" in stripped:
                    test_id = stripped.split(" FAILED")[0].strip()
                    tests_result.append({"id": test_id, "title": test_id.split("::")[-1], "status": "failed"})
                    failed += 1
                elif " ERROR" in stripped:
                    test_id = stripped.split(" ERROR")[0].strip()
                    tests_result.append({"id": test_id, "title": test_id.split("::")[-1], "status": "error"})
                    errors += 1
                elif " SKIPPED" in stripped:
                    test_id = stripped.split(" SKIPPED")[0].strip()
                    tests_result.append({"id": test_id, "title": test_id.split("::")[-1], "status": "skipped"})
                    skipped += 1
            total = passed + failed + errors + skipped
            success = proc.returncode == 0
            problems = failed + errors
            return {
                "success": success,
                "message": (
                    f"Выполнено {total}: {passed} прошло"
                    + (f", {problems} с ошибками" if problems else "")
                    + (f", {skipped} пропущено" if skipped else "")
                ),
                "summary": {"passed": passed, "failed": failed, "error": errors, "skipped": skipped, "total": total},
                "tests": tests_result,
                "raw_output": output,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "Таймаут выполнения тестов (300 сек)"}
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    start_cidr_task(task_id, _runner)
    return {
        "success": True,
        "queued": True,
        "task_id": task_id,
        "message": "Тесты запущены в фоне",
    }


@router.get("/tasks/{task_id}")
def get_test_task(task_id: str, _: User = Depends(require_admin)):
    from app.services.cidr.cidr_tasks import get_cidr_task

    task = get_cidr_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return serialize_cidr_task(task)
