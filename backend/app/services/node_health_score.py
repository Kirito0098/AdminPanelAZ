"""Deterministic node health score for NOC cards and incidents."""

from __future__ import annotations

from typing import Literal

# Keep aligned with frontend metricColors / MonitoringTab thresholds.
CPU_CRITICAL_PERCENT = 90.0
RAM_CRITICAL_PERCENT = 90.0
CPU_WARN_PERCENT = 75.0
RAM_WARN_PERCENT = 75.0

HealthLevel = Literal["ok", "warn", "critical"]


def compute_node_health_score(
    *,
    status: str,
    error: str | None = None,
    cpu_percent: float | None = None,
    memory_percent: float | None = None,
    active_services: int = 0,
    total_services: int = 0,
) -> tuple[int, HealthLevel]:
    status_norm = (status or "").strip().lower()
    if status_norm != "online":
        return 0, "critical"

    score = 100
    if error:
        score -= 40

    cpu = float(cpu_percent) if cpu_percent is not None else None
    ram = float(memory_percent) if memory_percent is not None else None

    cpu_critical = cpu is not None and cpu >= CPU_CRITICAL_PERCENT
    ram_critical = ram is not None and ram >= RAM_CRITICAL_PERCENT
    if cpu_critical:
        score -= 25
    if ram_critical:
        score -= 25

    inactive = max(0, int(total_services) - int(active_services))
    if inactive > 0:
        score -= min(30, 10 * inactive)

    if not cpu_critical and cpu is not None and cpu >= CPU_WARN_PERCENT:
        score -= 10
    if not ram_critical and ram is not None and ram >= RAM_WARN_PERCENT:
        score -= 10

    score = max(0, min(100, score))
    if score < 40:
        level: HealthLevel = "critical"
    elif score < 70:
        level = "warn"
    else:
        level = "ok"
    return score, level
