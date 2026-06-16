"""DPI log analysis."""
import re

from app.services.cidr.pipeline.dpi_checker_suite import lookup_checker_node
from app.services.cidr.pipeline.provider_sources import (
    DPI_NODE_CODE_TO_FILE,
    DPI_PROVIDER_ALIASES,
    _normalize_provider_name_token,
)

_ALIVE_CONSOLE_PATTERN = re.compile(r"alived:\s*(yes|no|unknown)", re.IGNORECASE)
_DPI_METHOD_PATTERN = re.compile(r"method:\s*(\d+)", re.IGNORECASE)


def _provider_name_to_file(provider_name):
    token = _normalize_provider_name_token(provider_name)
    if not token:
        return None

    if token in DPI_PROVIDER_ALIASES:
        return DPI_PROVIDER_ALIASES[token]

    for alias, file_name in DPI_PROVIDER_ALIASES.items():
        if token.startswith(alias) or alias.startswith(token):
            return file_name
    return None


def _normalize_alive_token(value):
    text = str(value or "").strip().lower()
    if text in {"yes", "да"} or "yes" in text or "🟢" in text:
        return "yes"
    if text in {"no", "нет"} or "no" in text or "🔴" in text:
        return "no"
    if "unknown" in text or "неизвест" in text:
        return "unknown"
    return None


def _normalize_dpi_severity(value):
    text = str(value or "").strip().lower()
    if not text:
        return "unknown", -1

    if text == "ok" or text.startswith("ok "):
        return "not_detected", 0
    if "not detected" in text:
        return "not_detected", 0
    if "unlikely" in text:
        return "unlikely", 1
    if ("possible" in text or "probably" in text) and "detected" in text:
        return "possible_detected", 2
    if "detected" in text:
        return "detected", 3

    return "unknown", -1


def _dpi_node_id_to_file(node_id):
    cyrillic_homoglyphs = str.maketrans(
        {
            "А": "A",
            "В": "B",
            "С": "C",
            "Е": "E",
            "К": "K",
            "М": "M",
            "Н": "H",
            "О": "O",
            "Р": "P",
            "Т": "T",
            "У": "Y",
            "Х": "X",
        }
    )

    value = str(node_id or "").strip().upper().translate(cyrillic_homoglyphs).lstrip("#")
    if not value:
        return None

    tokens = [item for item in re.split(r"[\.\-_/:\s]+", value) if item]
    for token in tokens:
        file_name = DPI_NODE_CODE_TO_FILE.get(token)
        if file_name:
            return file_name

    if "." in value:
        value = value.split(".", 1)[1]

    code = value.split("-", 1)[0]
    return DPI_NODE_CODE_TO_FILE.get(code)


def _enrich_node(node_id, file_name, severity_key, severity_score, status_text, alive=None):
    suite = lookup_checker_node(node_id) or {}
    dpi_method = None
    method_match = _DPI_METHOD_PATTERN.search(str(status_text or ""))
    if method_match:
        dpi_method = int(method_match.group(1))

    return {
        "node_id": node_id,
        "file": file_name,
        "severity": severity_key,
        "severity_score": severity_score,
        "status_text": status_text,
        "alive": alive,
        "host": suite.get("host"),
        "checker_provider": suite.get("provider"),
        "checker_country": suite.get("country"),
        "dpi_method": dpi_method,
    }


def _build_recommendations(nodes):
    by_file = {}
    for item in nodes:
        file_name = item.get("file")
        if not file_name:
            continue
        by_file.setdefault(file_name, []).append(item)

    recommendations = []
    for file_name in sorted(by_file.keys()):
        file_nodes = [item for item in by_file[file_name] if item.get("severity_score", -1) >= 0]
        if not file_nodes:
            continue

        grouped = {}
        for item in file_nodes:
            score = item.get("severity_score", -1)
            grouped.setdefault(score, []).append(item)

        max_score = max(grouped.keys())
        not_detected = grouped.get(0, [])
        triggers = grouped.get(max_score, [])
        total = len(file_nodes)

        if max_score == 3:
            level = "must"
            if not_detected:
                confidence = "weak"
                reason = (
                    f"detected только на {len(triggers)} из {total} узлов checker; "
                    "остальные not detected — возможен сигнал одного endpoint, VPN или POST ~64 KB, а не DPI на весь провайдер."
                )
            else:
                confidence = "high"
                reason = (
                    "POST ~64 KB на живой хост оборвался по таймауту (tcp 16-20 detected). "
                    "Открытие сайта в браузере этот тест не воспроизводит."
                )
        elif max_score == 2:
            level = "should"
            if not_detected:
                confidence = "weak"
                reason = (
                    f"possible detected на {len(triggers)} узле(ах), но {len(not_detected)} узел(ов) — not detected. "
                    "Скорее слабый или локальный сигнал, не блокировка всего провайдера."
                )
            else:
                confidence = "medium"
                reason = "Мгновенная ошибка на большом запросе при живом хосте — возможный, но не подтверждённый tcp 16-20."
        elif max_score == 1:
            level = "consider"
            alive_values = {item.get("alive") for item in triggers}
            if not_detected or alive_values.intersection({"unknown", "no", None}):
                confidence = "inconclusive"
                reason = (
                    "unlikely при unknown/no alive или при not detected на других узлах — "
                    "часто недоступность сервера checker, а не DPI."
                )
            else:
                confidence = "low"
                reason = "Слабый сигнал tcp 16-20 — включайте только при запасе бюджета маршрутов."
        else:
            level = "skip"
            confidence = "high"
            triggers = not_detected or file_nodes
            reason = "На тестовых узлах checker блокировка tcp 16-20 не выявлена."

        actionable = level in {"must", "should"} and confidence in {"high", "medium"}

        recommendations.append(
            {
                "file": file_name,
                "level": level,
                "confidence": confidence,
                "actionable": actionable,
                "reason": reason,
                "trigger_nodes": [
                    {
                        "node_id": item.get("node_id"),
                        "host": item.get("host"),
                        "alive": item.get("alive"),
                        "severity": item.get("severity"),
                        "severity_score": item.get("severity_score"),
                        "status_text": item.get("status_text"),
                        "dpi_method": item.get("dpi_method"),
                    }
                    for item in sorted(
                        triggers,
                        key=lambda row: (-row.get("severity_score", -1), row.get("node_id") or ""),
                    )
                ],
                "all_nodes": [
                    {
                        "node_id": item.get("node_id"),
                        "host": item.get("host"),
                        "alive": item.get("alive"),
                        "severity": item.get("severity"),
                        "severity_score": item.get("severity_score"),
                        "status_text": item.get("status_text"),
                        "dpi_method": item.get("dpi_method"),
                    }
                    for item in sorted(file_nodes, key=lambda row: row.get("node_id") or "")
                ],
            }
        )

    level_order = {"must": 0, "should": 1, "consider": 2, "skip": 3}
    confidence_order = {"high": 0, "medium": 1, "low": 2, "weak": 3, "inconclusive": 4}
    recommendations.sort(
        key=lambda item: (
            level_order.get(item["level"], 9),
            confidence_order.get(item["confidence"], 9),
            item["file"],
        )
    )
    return recommendations


def _build_caveats():
    return [
        {
            "type": "vpn",
            "severity": "warning",
            "title": "Checker запускайте без VPN",
            "message": (
                "TCP 16-20 checker рассчитан на «голый» канал провайдера. "
                "С включённым VPN (особенно полным) detected часто отражает туннель или POST ~64 KB, "
                "а не необходимость включать CIDR-список."
            ),
        },
        {
            "type": "test_method",
            "severity": "info",
            "title": "Detected ≠ «сайт не открывается»",
            "message": (
                "Checker проверяет HEAD (жив ли хост) и POST ~64 KB (method 1) или длинный URL (method 2). "
                "HTTP 200/404 в браузере и detected в логе могут сосуществовать."
            ),
        },
        {
            "type": "selective_routing",
            "severity": "info",
            "title": "CIDR-списки — для выборочной маршрутизации",
            "message": (
                "Рекомендации относятся к split-маршрутизации AntiZapret. "
                "При полном VPN отдельные списки (Akamai, OVH и т.д.) обычно не меняют картину."
            ),
        },
    ]


def analyze_dpi_log(dpi_log_text):
    text = str(dpi_log_text or "")
    if not text.strip():
        return {
            "success": False,
            "message": "Лог DPI пуст",
            "summary": {},
            "nodes": [],
            "providers": [],
            "recommendations": [],
            "caveats": _build_caveats(),
            "priority_files": [],
            "critical_files": [],
            "actionable_files": [],
            "unknown_nodes": [],
        }

    node_pattern = re.compile(r"DPI\s*checking\s*\(\s*#?([^\)]+)\s*\)", re.IGNORECASE)
    status_pattern = re.compile(r"tcp\s*16\s*[-–—]\s*20\s*:\s*([^\n\r]+)", re.IGNORECASE)
    provider_pattern = re.compile(r"provider\s*[:=]\s*([^,\n\r\]]+)", re.IGNORECASE)
    table_row_pattern = re.compile(
        r"^\s*[\|│]\s*([^\|│]+?)\s*[\|│]\s*([^\|│]+?)\s*[\|│]\s*([^\|│]+?)\s*[\|│]\s*([^\|│]+?)\s*[\|│]\s*([^\|│]+?)\s*[\|│]\s*([^\|│]+?)\s*[\|│]\s*$"
    )
    table_row_pattern_4col = re.compile(
        r"^\s*[\|│]\s*([^\|│]+?)\s*[\|│]\s*([^\|│]+?)\s*[\|│]\s*([^\|│]+?)\s*[\|│]\s*([^\|│]+?)\s*[\|│]\s*$"
    )

    node_alive = {}
    node_events = {}
    unknown_nodes = set()

    for raw_line in text.splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue

        node_match = node_pattern.search(line)
        if node_match:
            node_id = str(node_match.group(1) or "").strip()
            if not node_id:
                continue
            alive_match = _ALIVE_CONSOLE_PATTERN.search(line)
            if alive_match and not status_pattern.search(line):
                node_alive[node_id] = alive_match.group(1).lower()
                continue

    for raw_line in text.splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue

        node_match = node_pattern.search(line)
        table_match = table_row_pattern.match(line)
        table_match_4 = None if table_match else table_row_pattern_4col.match(line)

        node_id = ""
        file_name = None
        status_text = ""
        alive = None

        if node_match:
            node_id = str(node_match.group(1) or "").strip()
            if not node_id:
                continue

            file_name = _dpi_node_id_to_file(node_id)
            if not file_name:
                provider_match = provider_pattern.search(line)
                provider_name = str(provider_match.group(1) or "").strip() if provider_match else ""
                if provider_name:
                    file_name = _provider_name_to_file(provider_name)

            if not file_name:
                normalized_line = _normalize_provider_name_token(line)
                for alias, mapped_file in DPI_PROVIDER_ALIASES.items():
                    if alias and alias in normalized_line:
                        file_name = mapped_file
                        break

            status_match = status_pattern.search(line)
            if not status_match:
                continue

            status_text = str(status_match.group(1) or "").strip()
            alive = node_alive.get(node_id)
        elif table_match:
            node_id = str(table_match.group(1) or "").strip()
            provider_name = str(table_match.group(3) or "").strip()
            alive = _normalize_alive_token(table_match.group(4))
            status_text = str(table_match.group(5) or "").strip()

            node_id_lower = node_id.lower()
            status_lower = status_text.lower()
            if node_id_lower in {"id", "ид"} or status_lower in {"status", "статус"}:
                continue

            if not node_id or not status_text:
                continue

            file_name = _dpi_node_id_to_file(node_id)
            if not file_name and provider_name:
                file_name = _provider_name_to_file(provider_name)

            if not file_name:
                normalized_provider = _normalize_provider_name_token(provider_name)
                for alias, mapped_file in DPI_PROVIDER_ALIASES.items():
                    if alias and alias in normalized_provider:
                        file_name = mapped_file
                        break
        elif table_match_4:
            node_id = str(table_match_4.group(1) or "").strip()
            alive = _normalize_alive_token(table_match_4.group(3))
            status_text = str(table_match_4.group(4) or "").strip()

            if not node_id or not status_text:
                continue

            node_id_lower = node_id.lower()
            status_lower = status_text.lower()
            if node_id_lower in {"id", "ид"} or status_lower in {"status", "статус", "tcp 16-20"}:
                continue

            file_name = _dpi_node_id_to_file(node_id)
            if not file_name:
                provider_name = str(table_match_4.group(2) or "").strip()
                file_name = _provider_name_to_file(provider_name)
        else:
            continue

        severity_key, severity_score = _normalize_dpi_severity(status_text)
        event = node_events.get(node_id)
        if event is None or severity_score > event.get("severity_score", -1):
            node_events[node_id] = _enrich_node(
                node_id,
                file_name,
                severity_key,
                severity_score,
                status_text,
                alive=alive or node_alive.get(node_id),
            )

        if not file_name:
            unknown_nodes.add(node_id)

    if not node_events:
        return {
            "success": False,
            "message": "В логе не найдены результаты tcp 16-20",
            "summary": {},
            "nodes": [],
            "providers": [],
            "recommendations": [],
            "caveats": _build_caveats(),
            "priority_files": [],
            "critical_files": [],
            "actionable_files": [],
            "unknown_nodes": [],
        }

    provider_stats = {}
    nodes = sorted(node_events.values(), key=lambda item: item["node_id"])
    for item in nodes:
        file_name = item.get("file")
        if not file_name:
            continue

        stats = provider_stats.setdefault(
            file_name,
            {
                "file": file_name,
                "max_severity_score": -1,
                "detected": 0,
                "possible_detected": 0,
                "unlikely": 0,
                "not_detected": 0,
                "unknown": 0,
                "nodes": 0,
            },
        )
        stats["nodes"] += 1
        severity_key = item.get("severity") or "unknown"
        stats[severity_key] = stats.get(severity_key, 0) + 1
        stats["max_severity_score"] = max(stats["max_severity_score"], item["severity_score"])

    providers = sorted(
        provider_stats.values(),
        key=lambda item: (-item["max_severity_score"], -item["nodes"], item["file"]),
    )
    recommendations = _build_recommendations(nodes)

    all_seen_files = [item["file"] for item in providers]
    detected_files = [item["file"] for item in providers if item["max_severity_score"] >= 3]
    priority_files = [item["file"] for item in providers if item["max_severity_score"] >= 1]
    critical_files = [item["file"] for item in providers if item["max_severity_score"] >= 2]
    actionable_files = [item["file"] for item in recommendations if item.get("actionable")]

    return {
        "success": True,
        "message": "DPI лог обработан",
        "summary": {
            "total_nodes": len(nodes),
            "matched_nodes": sum(1 for item in nodes if item.get("file")),
            "unknown_nodes": len(unknown_nodes),
            "all_seen_files": len(all_seen_files),
            "detected_files": len(detected_files),
            "priority_files": len(priority_files),
            "critical_files": len(critical_files),
            "actionable_files": len(actionable_files),
            "weak_signals": sum(
                1 for item in recommendations if item.get("confidence") in {"weak", "inconclusive"}
            ),
        },
        "nodes": nodes,
        "providers": providers,
        "recommendations": recommendations,
        "caveats": _build_caveats(),
        "all_seen_files": all_seen_files,
        "detected_files": detected_files,
        "priority_files": priority_files,
        "critical_files": critical_files,
        "actionable_files": actionable_files,
        "unknown_nodes": sorted(unknown_nodes),
    }
