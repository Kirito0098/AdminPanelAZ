"""Server config the web update leaves behind: full-update.sh --server-only, preview and apply."""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.services import ddns_settings
from app.services.nginx_impact import build_nginx_impact

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = PROJECT_ROOT / "scripts" / "full-update.sh"
SECTIONS = ("add", "change", "recheck", "keep", "remove", "effect")
# Строки под пунктом превью: вид в tsv → поле в details.
DETAIL_KINDS = {"minus": "removed", "plus": "added", "why": "why", "info": "info"}
# Шаги, которые делает --server-only. Порядок — порядок выполнения; ключ уходит в FU_ONLY/full-update.sh.
STEPS = (
    {"key": "apt", "label": "Пакеты"},
    {"key": "systemd", "label": "Службы systemd"},
    {"key": "nginx", "label": "nginx"},
    {"key": "firewall", "label": "firewall"},
    {"key": "ddns", "label": "DDNS"},
)
LABELS = {step["key"]: step["label"] for step in STEPS}


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


def _ddns_configured() -> bool:
    return ddns_settings.ddns_config_path().is_file() or ddns_settings.load_ddns_config().provider != "none"


def available_steps() -> list[dict[str, Any]]:
    ddns = _ddns_configured()
    steps: list[dict[str, Any]] = []
    for step in STEPS:
        available = step["key"] != "ddns" or ddns
        item: dict[str, Any] = {"key": step["key"], "label": step["label"], "available": available}
        if not available:
            item["reason"] = "DDNS не настроен"
        steps.append(item)
    return steps


def validate_steps(steps: list[str] | None) -> list[str]:
    """Selected step keys, in requested order. Empty or unknown/unavailable keys are an error."""
    if not steps:
        raise ValueError("Выберите хотя бы один шаг обновления")
    available = {item["key"] for item in available_steps() if item["available"]}
    selected: list[str] = []
    for raw in steps:
        key = raw.strip()
        if key not in available:
            raise ValueError(f"Неизвестный или недоступный шаг обновления: {raw}")
        if key not in selected:
            selected.append(key)
    return selected


def _panel_domain() -> str:
    from app.config import get_settings

    return (get_settings().domain or os.environ.get("DOMAIN", "")).strip()


def _portal_domain(db: Any | None) -> str:
    if db is None:
        return ""
    from app.services.client_portal import get_portal_domain

    return get_portal_domain(db)


def preview(db: Any | None = None) -> dict[str, Any]:
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
    return {
        "sections": sections,
        "details": details,
        "pending": len(sections["add"]) + len(sections["change"]),
        "steps": available_steps(),
        "nginx_impact": build_nginx_impact(
            project_root=PROJECT_ROOT,
            panel_domain=_panel_domain(),
            portal_domain=_portal_domain(db),
        ),
    }


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


def apply(
    steps: list[str] | None = None,
    progress_updater: Callable[[int, str], None] | None = None,
) -> dict[str, Any]:
    selected = validate_steps(steps) if steps is not None else None
    if progress_updater:
        progress_updater(10, "Обновление настроек сервера…")
    env = {"DEBIAN_FRONTEND": "noninteractive"}
    if selected:
        env["FU_ONLY"] = ",".join(selected)
    with tempfile.NamedTemporaryFile(prefix="server-config-", suffix=".tsv") as report:
        output = _run_script(
            "--server-only",
            "--report",
            report.name,
            timeout=1200,
            env=env,
            ok_codes=(0, 1),  # 1 — шаг с ошибкой, итог всё равно в отчёте
        )
        result = parse_report(Path(report.name).read_text(encoding="utf-8"))
    result["output"] = output[-4000:]
    return result
