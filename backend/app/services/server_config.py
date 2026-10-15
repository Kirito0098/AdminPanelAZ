"""Server config the web update leaves behind: full-update.sh --server-only, preview and apply."""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = PROJECT_ROOT / "scripts" / "full-update.sh"
SECTIONS = ("add", "change", "recheck", "keep", "remove", "effect")
# Строки под пунктом превью: вид в tsv → поле в details.
DETAIL_KINDS = {"minus": "removed", "plus": "added", "why": "why", "info": "info"}
LABELS = {"apt": "Пакеты", "systemd": "Службы systemd", "nginx": "nginx", "firewall": "firewall", "ddns": "DDNS"}


def _run_script(*args: str, timeout: int, env: dict[str, str] | None = None, ok_codes: tuple[int, ...] = (0,)) -> str:
    result = subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=PROJECT_ROOT,
        env={**os.environ, "NO_COLOR": "1", "INSTALL_DIR": str(PROJECT_ROOT), **(env or {})},
        # Ошибки шагов (nginx -t, apt, ui_fail) идут в stderr — без них итог «см. вывод выше» пуст.
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode not in ok_codes:
        raise RuntimeError(result.stdout.strip()[-500:] or f"код {result.returncode}")
    return result.stdout


def preview() -> dict[str, Any]:
    sections: dict[str, list[str]] = {key: [] for key in SECTIONS}
    details: dict[str, dict[str, list[str]]] = {}
    item = ""
    output = _run_script("--preview", "HEAD", "--server-only", timeout=60, env={"UP_FORMAT": "tsv"})
    for line in output.splitlines():
        key, _, text = line.partition("\t")
        if not text:
            continue
        if key in sections:
            item = text
            sections[key].append(item)
        elif key in DETAIL_KINDS and item:
            details.setdefault(item, {kind: [] for kind in DETAIL_KINDS.values()})[DETAIL_KINDS[key]].append(text)
    return {"sections": sections, "details": details, "pending": len(sections["add"]) + len(sections["change"])}


def parse_report(text: str) -> dict[str, Any]:
    rows = []
    for line in text.splitlines():
        step, _, rest = line.partition("\t")
        status, _, detail = rest.partition("\t")
        if step in LABELS:
            rows.append({"step": step, "label": LABELS[step], "status": status, "detail": detail})
    if not rows:
        return {"success": False, "message": "Шаги не выполнялись — подробности в журнале задачи", "rows": []}
    errors = sum(row["status"] == "ошибка" for row in rows)
    return {
        "success": errors == 0,
        "message": f"Есть ошибки: {errors}" if errors else "Настройки сервера обновлены",
        "rows": rows,
    }


def apply(progress_updater: Callable[[int, str], None] | None = None) -> dict[str, Any]:
    if progress_updater:
        progress_updater(10, "Обновление настроек сервера…")
    with tempfile.NamedTemporaryFile(prefix="server-config-", suffix=".tsv") as report:
        output = _run_script(
            "--server-only",
            "--report",
            report.name,
            timeout=1200,
            env={"DEBIAN_FRONTEND": "noninteractive"},
            ok_codes=(0, 1),  # 1 — шаг с ошибкой, итог всё равно в отчёте
        )
        result = parse_report(Path(report.name).read_text(encoding="utf-8"))
    result["output"] = output[-4000:]
    return result
