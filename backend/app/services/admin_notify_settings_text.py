"""Human-readable Russian action lines for settings_change Telegram notifications."""

from __future__ import annotations

import re

SETTINGS_CHANGE_LABELS: dict[str, str] = {
    "settings_port_update": "Изменён порт",
    "settings_telegram_auth_update": "Изменены настройки Telegram-авторизации",
    "settings_nightly_update": "Изменено расписание ночного рестарта",
    "settings_backup_update": "Изменены настройки бэкапов",
    "settings_backup_create": "Создан бэкап",
    "settings_backup_restore": "Запущено восстановление из бэкапа",
    "settings_backup_delete": "Удалён бэкап",
    "settings_restart_service": "Перезапуск сервиса",
    "settings_user_password_update": "Изменён пароль пользователя",
    "settings_user_role_update": "Изменена роль пользователя",
    "settings_cidr_update_queued": "Обновление CIDR-файлов",
    "settings_cidr_rollback_queued": "Откат CIDR-файлов",
    "settings_cidr_db_refresh_queued": "Обновление CIDR из базы",
    "settings_cidr_db_clear": "Очистка базы CIDR",
    "settings_cidr_generate_from_db": "Генерация CIDR из базы",
    "settings_cidr_preset_create": "Создан CIDR-пресет",
    "settings_cidr_preset_update": "Обновлён CIDR-пресет",
    "settings_cidr_preset_delete": "Удалён CIDR-пресет",
    "settings_cidr_preset_reset": "Сброс CIDR-пресета до базовых значений",
    "settings_antifilter_refresh": "Обновление AntiFilter",
    "settings_run_doall": "Перегенерация конфигурации VPN (doall.sh)",
    "settings_vpn_network_publish": "Публикация панели (VPN-сеть)",
}

_ROLE_LABELS_RU = {
    "admin": "администратор",
    "user": "пользователь",
    "viewer": "наблюдатель",
}


def parse_mini_details_kv(raw_details: str | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for token in str(raw_details or "").split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        key = key.strip()
        if not key:
            continue
        result[key] = value.strip()
    return result


def _parse_arrow_change(details: str | None) -> tuple[str, str] | None:
    text = str(details or "").strip()
    if "→" not in text:
        return None
    old_value, new_value = text.split("→", 1)
    return old_value.strip(), new_value.strip()


def _humanize_cron(cron_expr: str) -> str:
    parts = str(cron_expr or "").strip().split()
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        minute, hour = int(parts[0]), int(parts[1])
        return f"ежедневно в {hour:02d}:{minute:02d}"
    return str(cron_expr or "").strip()


def _format_nightly_update_details(details: str | None) -> str:
    raw = str(details or "").strip()
    if not raw:
        return "Ночной рестарт: настройки изменены"

    enabled_match = re.search(r"enabled=(\S+)", raw)
    cron_match = re.search(r"cron=(.+?)\s+ttl=", raw)
    ttl_match = re.search(r"ttl=(\d+)", raw)
    touch_match = re.search(r"touch=(\d+)", raw)

    enabled_raw = (enabled_match.group(1) if enabled_match else "").lower()
    if enabled_raw in {"вкл", "1", "true", "yes"}:
        enabled_text = "включён"
    elif enabled_raw in {"выкл", "0", "false", "no"}:
        enabled_text = "выключен"
    else:
        enabled_text = "изменён"

    parts = [f"Ночной рестарт {enabled_text}"]
    if cron_match:
        parts.append(f"по расписанию {_humanize_cron(cron_match.group(1))}")
    if ttl_match:
        parts.append(f"TTL сессии {ttl_match.group(1)} с")
    if touch_match:
        parts.append(f"интервал активности {touch_match.group(1)} с")
    return ", ".join(parts)


def _humanize_raw_details_for_tg(details: str | None) -> str | None:
    raw = str(details or "").strip()
    if not raw:
        return None
    if "→" in raw:
        old_val, new_val = _parse_arrow_change(raw) or ("—", "—")
        return f"с {old_val} на {new_val}"
    return None


def user_action_tg_action_line(
    event_key: str,
    *,
    details: str | None = None,
    target_name: str | None = None,
    target_type: str | None = None,
) -> str:
    """Human-readable Russian action line for Telegram settings notifications."""
    key = str(event_key or "").strip()
    details_value = str(details or "").strip()
    target_value = str(target_name or "").strip()
    _ = target_type

    if key == "settings_nightly_update":
        return _format_nightly_update_details(details_value)

    if key == "settings_port_update":
        arrow = _parse_arrow_change(details_value)
        if arrow:
            return f"Порт панели: с {arrow[0]} на {arrow[1]}"

    if key == "settings_user_password_update":
        return "Пароль пользователя изменён"

    if key == "settings_user_role_update" and "→" in details_value:
        old_val, new_val = _parse_arrow_change(details_value) or ("—", "—")
        user = target_value or "пользователь"
        old_ru = _ROLE_LABELS_RU.get(old_val.lower(), old_val)
        new_ru = _ROLE_LABELS_RU.get(new_val.lower(), new_val)
        return f"Роль пользователя {user}: с «{old_ru}» на «{new_ru}»"

    if key == "settings_backup_create":
        return "Запущено ручное создание резервной копии"

    if key == "settings_backup_restore":
        archive = target_value if target_value and target_value != "manual_create" else ""
        if archive:
            return f"Восстановление из архива «{archive}» поставлено в очередь"
        return "Восстановление из бэкапа поставлено в очередь"

    if key == "settings_backup_delete":
        if target_value:
            return f"Удалён бэкап «{target_value}»"
        return "Удалён файл бэкапа"

    if key == "settings_restart_service":
        svc = target_value or "сервис"
        return f"Перезапущена служба {svc}"

    if key == "settings_run_doall":
        return "Запущена перегенерация конфигурации VPN (doall.sh)"

    humanized = _humanize_raw_details_for_tg(details_value)
    if humanized:
        label = SETTINGS_CHANGE_LABELS.get(key, "Настройки")
        return f"{label}: {humanized}"

    return SETTINGS_CHANGE_LABELS.get(key, "Изменение настроек")
