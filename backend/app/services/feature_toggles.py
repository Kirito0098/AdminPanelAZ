"""Feature toggle registry (ported from AdminAntizapret 1.9.0)."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.services.env_file import EnvFileService
from app.services.shared_helpers import parse_bool as _parse_bool

RESOURCE_IMPACT_LEVELS = {
    "minimal": {"label": "минимальная"},
    "low": {"label": "низкая"},
    "medium": {"label": "средняя"},
    "high": {"label": "высокая"},
}

FEATURE_TOGGLE_GROUPS = {
    "background": {
        "label": "Фоновые задачи",
        "description": "Cron-задачи и фоновые потоки — разделы UI остаются доступными.",
        "badge": "Фоновая задача",
    },
    "app_module": {
        "label": "Разделы приложения",
        "description": "Полное отключение модулей: меню, страницы и связанные API.",
        "badge": "Раздел приложения",
    },
}


@dataclass(frozen=True)
class FeatureToggleDefinition:
    key: str
    env_key: str
    label: str
    description: str
    default: bool = True
    group: str = "background"
    icon: str = "⚙️"
    disable_hint: Optional[str] = None
    resource_impact_level: str = "low"
    resource_savings: str = ""
    api_prefixes: tuple[str, ...] = ()
    api_paths: tuple[str, ...] = ()
    frontend_paths: tuple[str, ...] = ()
    settings_tabs: tuple[str, ...] = ()


FEATURE_TOGGLES: tuple[FeatureToggleDefinition, ...] = (
    FeatureToggleDefinition(
        key="traffic_sync",
        env_key="TRAFFIC_SYNC_ENABLED",
        label="Синхронизация трафика",
        description="Фоновый сбор статистики OpenVPN и WireGuard в БД. Нужен для «Трафик (БД)» и лимитов.",
        icon="📊",
        disable_hint="Перестанут обновляться «Трафик (БД)» и автоматические лимиты трафика.",
        resource_impact_level="high",
        resource_savings="Cron/фоновый цикл, чтение status-логов и запись в SQLite.",
        default=True,
        group="background",
        api_prefixes=("/api/traffic",),
        frontend_paths=("/traffic",),
    ),
    FeatureToggleDefinition(
        key="wg_policy_sync",
        env_key="WG_POLICY_SYNC_ENABLED",
        label="Синхронизация WG/AWG политик",
        description="Периодическая сверка блокировок WireGuard/AWG с runtime (expiry, temp block, drift repair).",
        icon="🛡️",
        disable_hint="Автоматическое применение WG-блокировок после перезапуска и по расписанию будет отключено.",
        resource_impact_level="medium",
        resource_savings="Фоновый цикл reconcile_all и wg set на узлах.",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="resource_monitor",
        env_key="MONITOR_ENABLED",
        label="Мониторинг нагрузки CPU/RAM",
        description="Фоновый мониторинг загрузки сервера.",
        icon="📈",
        disable_hint="Мониторинг нагрузки CPU/RAM будет отключён.",
        resource_impact_level="low",
        default=True,
        group="background",
        settings_tabs=("monitoring",),
    ),
    FeatureToggleDefinition(
        key="openvpn",
        env_key="FEATURE_OPENVPN_ENABLED",
        label="OpenVPN",
        description="Управление клиентами OpenVPN, блокировки и лимиты трафика.",
        icon="🔐",
        disable_hint="Действия OpenVPN на главной станут недоступны.",
        resource_impact_level="minimal",
        default=True,
        group="app_module",
        api_prefixes=("/api/client-access/openvpn",),
    ),
    FeatureToggleDefinition(
        key="wireguard",
        env_key="FEATURE_WIREGUARD_ENABLED",
        label="WireGuard",
        description="Вкладка WireGuard, политики доступа и лимиты трафика.",
        icon="🛡️",
        disable_hint="Вкладка WireGuard и связанные действия станут недоступны.",
        resource_impact_level="minimal",
        default=True,
        group="app_module",
        api_prefixes=("/api/client-access/wireguard",),
    ),
    FeatureToggleDefinition(
        key="amneziawg",
        env_key="FEATURE_AMNEZIAWG_ENABLED",
        label="AmneziaWG",
        description="Вкладка AmneziaWG на главной и связанные операции с клиентами AWG.",
        icon="🛡️",
        disable_hint="Вкладка AmneziaWG и связанные действия станут недоступны.",
        resource_impact_level="minimal",
        default=True,
        group="app_module",
        api_prefixes=("/api/client-access/wireguard",),
    ),
    FeatureToggleDefinition(
        key="logs_dashboard",
        env_key="FEATURE_LOGS_DASHBOARD_ENABLED",
        label="Подключённые клиенты / трафик",
        description="Разделы «Подключённые клиенты» и «Мониторинг трафика».",
        icon="📋",
        disable_hint="Разделы трафика и логов станут недоступны.",
        resource_impact_level="low",
        default=True,
        group="app_module",
        api_paths=(
            "/api/logs/connections",
            "/api/logs/openvpn-events",
            "/api/logs/openvpn-sockets",
            "/api/monitoring/overview",
        ),
        frontend_paths=("/monitoring",),
    ),
    FeatureToggleDefinition(
        key="server_monitor",
        env_key="FEATURE_SERVER_MONITOR_ENABLED",
        label="Мониторинг сервера",
        description="Страница «Мониторинг сервера»: CPU/RAM, WebSocket и vnstat.",
        icon="🖥️",
        disable_hint="Страница «Мониторинг сервера» будет недоступна.",
        resource_impact_level="medium",
        default=True,
        group="app_module",
        api_prefixes=("/api/server-monitor",),
        frontend_paths=("/server-monitor",),
    ),
    FeatureToggleDefinition(
        key="routing",
        env_key="FEATURE_ROUTING_ENABLED",
        label="Маршрутизация",
        description="Раздел «Маршрутизация / CIDR»: провайдеры, pipeline и развёртывание списков.",
        icon="🗺️",
        disable_hint="Раздел маршрутизации / CIDR будет недоступен. «Конфиг AntiZapret» не затрагивается.",
        resource_impact_level="minimal",
        default=True,
        group="app_module",
        api_prefixes=("/api/routing",),
        api_paths=("/api/routing/apply",),
        frontend_paths=("/routing",),
    ),
    FeatureToggleDefinition(
        key="antizapret_config",
        env_key="FEATURE_ANTIZAPRET_CONFIG_ENABLED",
        label="Конфиг AntiZapret",
        description="Раздел «Конфиг AntiZapret»: параметры setup (маршруты, порты, WARP, AdBlock).",
        icon="⚙️",
        disable_hint="Раздел «Конфиг AntiZapret» и API настроек setup будут недоступны.",
        resource_impact_level="minimal",
        default=True,
        group="app_module",
        api_paths=(
            "/api/routing/antizapret-settings",
            "/api/routing/apply",
        ),
        frontend_paths=("/antizapret",),
    ),
    FeatureToggleDefinition(
        key="warper",
        env_key="FEATURE_WARPER_ENABLED",
        label="AZ-WARP",
        description="Точечная маршрутизация доменов и подсетей через Cloudflare WARP / AZ-WARP на VPN-узле.",
        icon="🌐",
        disable_hint="Раздел AZ-WARP и связанные API будут недоступны.",
        resource_impact_level="minimal",
        default=True,
        group="app_module",
        api_prefixes=("/api/warper",),
        frontend_paths=("/warper",),
    ),
    FeatureToggleDefinition(
        key="awg2",
        env_key="FEATURE_AWG2_ENABLED",
        label="AZ-AWG2",
        description="Параллельный слой AmneziaWG 2.0 (az-awg2): статусы и установка. Клиенты — в следующем срезе.",
        icon="🧬",
        disable_hint="Раздел AZ-AWG2 и связанные API станут недоступны.",
        resource_impact_level="minimal",
        default=False,
        group="app_module",
        api_prefixes=("/api/awg2", "/api/client-access/amneziawg2"),
        frontend_paths=("/awg2",),
    ),
    FeatureToggleDefinition(
        key="edit_files",
        env_key="FEATURE_EDIT_FILES_ENABLED",
        label="Редактор файлов",
        description="Страница «Редактировать файлы».",
        icon="📝",
        disable_hint="Редактор файлов будет недоступен.",
        resource_impact_level="minimal",
        default=True,
        group="app_module",
        api_prefixes=("/api/edit-files",),
        frontend_paths=("/edit-files",),
    ),
    FeatureToggleDefinition(
        key="telegram",
        env_key="FEATURE_TELEGRAM_ENABLED",
        label="Telegram",
        description=(
            "Полная интеграция: бот, webhook, Mini App, вход через Telegram, AdminNotify и доставка бэкапов."
        ),
        icon="✈️",
        disable_hint=(
            "Раздел Telegram, webhook, Mini App и все вызовы Bot API будут отключены. "
            "Webhook снимается автоматически; перезапустите панель после сохранения."
        ),
        resource_impact_level="low",
        resource_savings="Webhook, Bot API, Mini App auth и исходящие TG-уведомления/бэкапы.",
        default=False,
        group="app_module",
        api_prefixes=("/api/tg-mini", "/api/telegram"),
        api_paths=(
            "/api/auth/telegram",
            "/api/auth/telegram/config",
            "/api/settings/telegram",
            "/api/settings/admin-notify",
        ),
        frontend_paths=("/telegram",),
    ),
    FeatureToggleDefinition(
        key="proxy_nodes",
        env_key="FEATURE_PROXY_NODES_ENABLED",
        label="Прокси-узлы",
        description=(
            "Управление прокси-узлами (proxy_agent): создание узлов kind=proxy, "
            "статус/destination/mappings. Включайте только если уже используете proxy.sh. "
            "Важно: префикс /api/nodes в ALWAYS_ALLOWED — создание proxy и будущие "
            "маршруты /api/nodes/{id}/proxy/* проверяются только в обработчиках "
            "(is_enabled / is_proxy_nodes_enabled), не middleware."
        ),
        icon="🔗",
        disable_hint=(
            "Создание прокси-узлов и proxy-API будут недоступны. "
            "Существующие VPN-узлы не затрагиваются."
        ),
        resource_impact_level="minimal",
        default=False,
        group="app_module",
        # Paths are documentation for operators/UI; middleware cannot gate them because
        # /api/nodes is ALWAYS_ALLOWED. Handlers must call is_proxy_nodes_enabled().
        api_paths=(
            "/api/nodes/{id}/proxy/status",
            "/api/nodes/{id}/proxy/destination",
            "/api/nodes/{id}/proxy/mappings",
        ),
    ),
    FeatureToggleDefinition(
        key="backups",
        env_key="FEATURE_BACKUPS_ENABLED",
        label="Резервные копии",
        description="Раздел бэкапов в настройках.",
        icon="💾",
        disable_hint="Бэкапы и авто-бэкап будут отключены.",
        resource_impact_level="medium",
        default=True,
        group="app_module",
        api_prefixes=("/api/backups",),
        settings_tabs=("backup",),
    ),
    FeatureToggleDefinition(
        key="maintenance",
        env_key="FEATURE_MAINTENANCE_ENABLED",
        label="Обслуживание",
        description="Вкладка «Обслуживание»: doall, пересоздание профилей и перезапуск VPN-служб.",
        icon="🔧",
        disable_hint="Вкладка «Обслуживание» и связанные операции будут недоступны.",
        resource_impact_level="minimal",
        default=True,
        group="app_module",
        api_prefixes=("/api/maintenance",),
        api_paths=(
            "/api/settings/run-doall",
            "/api/settings/restart-service",
            "/api/settings/recreate-profiles",
        ),
        settings_tabs=("maintenance",),
    ),
    FeatureToggleDefinition(
        key="security",
        env_key="FEATURE_SECURITY_ENABLED",
        label="Безопасность",
        description="IP-ограничения, whitelist и защита от сканеров.",
        icon="🔒",
        disable_hint="Вкладка «Безопасность» будет недоступна.",
        resource_impact_level="minimal",
        default=True,
        group="app_module",
        api_prefixes=("/api/security",),
        settings_tabs=("security",),
    ),
    FeatureToggleDefinition(
        key="diagnostics_tests",
        env_key="FEATURE_DIAGNOSTICS_TESTS_ENABLED",
        label="Диагностика",
        description="Runbook диагностики запуска панели и site-diagnostics.",
        icon="🧪",
        disable_hint="Вкладка диагностики будет недоступна.",
        resource_impact_level="medium",
        default=True,
        group="app_module",
        api_prefixes=("/api/site-diagnostics",),
        settings_tabs=("tests",),
    ),
    FeatureToggleDefinition(
        key="user_management",
        env_key="FEATURE_USER_MANAGEMENT_ENABLED",
        label="Пользователи и доступ",
        description="Вкладка «Пользователи»: учётные записи, роли, квоты и доп. доступ к клиентам.",
        icon="👤",
        disable_hint="Вкладка «Пользователи» и API управления пользователями станут недоступны.",
        resource_impact_level="minimal",
        default=True,
        group="app_module",
        api_prefixes=("/api/users",),
        settings_tabs=("users",),
    ),
    FeatureToggleDefinition(
        key="clients_page",
        env_key="FEATURE_CLIENTS_PAGE_ENABLED",
        label="Клиенты",
        description="Пункт «Клиенты» в меню. Маршрут остаётся доступен из карточки пользователя.",
        icon="📇",
        disable_hint="Пункт «Клиенты» скроется из меню; маршрут карточки пользователя останется доступен.",
        resource_impact_level="minimal",
        default=True,
        group="app_module",
        # Sidebar-only: the / route must stay reachable, no api_prefixes here.
        frontend_paths=(),
    ),
    FeatureToggleDefinition(
        key="user_provisioning",
        env_key="FEATURE_USER_PROVISIONING_ENABLED",
        label="Пользователи (абоненты)",
        description="Раздел «Пользователи», набор конфигов и provisioning API.",
        icon="👥",
        disable_hint="Раздел «Пользователи (абоненты)» и API предоставления конфигов будут недоступны.",
        resource_impact_level="minimal",
        default=False,
        group="app_module",
        # No broad /api/users prefix — user_management owns it. Explicit path checks in
        # feature_guards cover only provisioning routes.
        frontend_paths=("/users",),
    ),
    FeatureToggleDefinition(
        key="action_logs",
        env_key="FEATURE_ACTION_LOGS_ENABLED",
        label="Логи действий",
        description="Журнал действий администраторов на странице «Журналы».",
        icon="📜",
        disable_hint="Журнал действий администраторов станет недоступен.",
        resource_impact_level="low",
        default=True,
        group="app_module",
        api_paths=("/api/logs/actions", "/api/logs/action-logs/export"),
        frontend_paths=("/logs",),
    ),
    FeatureToggleDefinition(
        key="system_updates",
        env_key="FEATURE_SYSTEM_UPDATES_ENABLED",
        label="Обновления системы",
        description="Вкладка «Обновления»: проверка git-репозитория и обновление панели.",
        icon="⬆️",
        disable_hint="Вкладка «Обновления» и API обновления из панели станут недоступны.",
        resource_impact_level="medium",
        default=True,
        group="app_module",
        api_prefixes=("/api/system/update",),
        settings_tabs=("updates",),
    ),
    FeatureToggleDefinition(
        key="qr_downloads",
        env_key="FEATURE_QR_DOWNLOADS_ENABLED",
        label="Скачивание и QR",
        description="Скачивание конфигов, QR-коды и одноразовые ссылки.",
        icon="📲",
        disable_hint="Кнопки скачивания/QR и одноразовые ссылки станут недоступны.",
        resource_impact_level="low",
        default=True,
        group="app_module",
        api_paths=("/api/logs/qr-downloads",),
        settings_tabs=("qr_downloads",),
    ),
    FeatureToggleDefinition(
        key="unlock_codes",
        env_key="FEATURE_UNLOCK_CODES_ENABLED",
        label="Unlock-коды доступа",
        description="Unlock-коды для выдачи доступа с заданным сроком и поддерживаемыми протоколами.",
        icon="🎟️",
        disable_hint="Unlock-коды доступа и связанные операции будут недоступны.",
        resource_impact_level="low",
        default=True,
        group="app_module",
        api_prefixes=("/api/unlock-codes",),
    ),
    FeatureToggleDefinition(
        key="client_portal",
        env_key="FEATURE_CLIENT_PORTAL_ENABLED",
        label="Клиентский портал",
        description="Постоянные ссылки на поддомене портала (страница установки, OpenVPN import, скачивание).",
        icon="🔗",
        disable_hint="Ссылки и страница клиентского портала станут недоступны.",
        resource_impact_level="low",
        default=True,
        group="app_module",
        api_prefixes=("/api/portal", "/api/public/portal"),
        settings_tabs=("qr_downloads",),
    ),
    FeatureToggleDefinition(
        key="vpn_network",
        env_key="FEATURE_VPN_NETWORK_ENABLED",
        label="Адрес сайта и HTTPS",
        description="Вкладка «Адрес сайта и HTTPS»: публикация панели, домен, reverse-proxy и Cloudflare proxy-mode.",
        icon="🌐",
        disable_hint="Вкладка «Адрес сайта и HTTPS» будет недоступна.",
        resource_impact_level="minimal",
        default=True,
        group="app_module",
        settings_tabs=("vpn_network",),
    ),
    FeatureToggleDefinition(
        key="active_web_sessions",
        env_key="ACTIVE_WEB_SESSION_TRACKING_ENABLED",
        label="Учёт активных web-сессий",
        description="Heartbeat и last_seen для определения активных вкладок панели (нужен для ночного рестарта).",
        icon="👁️",
        disable_hint="Heartbeat не будет обновлять БД; ночной рестарт не увидит активных пользователей.",
        resource_impact_level="low",
        resource_savings="Периодические записи в SQLite при heartbeat и API-запросах.",
        default=True,
        group="background",
        api_paths=("/api/session-heartbeat",),
    ),
    FeatureToggleDefinition(
        key="nightly_idle_restart",
        env_key="NIGHTLY_IDLE_RESTART_ENABLED",
        label="Ночной рестарт при простое",
        description="Перезапуск systemd-сервиса панели, если нет активных web-сессий (по расписанию cron).",
        icon="🌙",
        disable_hint="Автоматический ночной перезапуск панели при отсутствии активных сессий будет отключён.",
        resource_impact_level="low",
        resource_savings="Один systemctl restart в сутки при простое.",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="runtime_backup_cleanup",
        env_key="RUNTIME_BACKUP_CLEANUP_ENABLED",
        label="Очистка runtime-бэкапов CIDR",
        description="Удаление устаревших каталогов runtime_backups после pipeline CIDR (retention 12 ч).",
        icon="🧹",
        disable_hint="Старые runtime-бэкапы списков не будут удаляться автоматически.",
        resource_impact_level="low",
        resource_savings="Почасовая очистка каталогов в data/cidr/runtime_backups.",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="nodes",
        env_key="FEATURE_NODES_ENABLED",
        label="Узлы",
        description="Страница «Узлы»: список VPN/прокси-узлов, ключи, mTLS и обновления агента.",
        icon="🖥️",
        disable_hint="Страница «Узлы» и операции создания/изменения узлов станут недоступны. Фоновый опрос и чтение узлов другими разделами сохраняются.",
        resource_impact_level="minimal",
        default=True,
        group="app_module",
        frontend_paths=("/nodes",),
    ),
    FeatureToggleDefinition(
        key="node_ssh_transport",
        env_key="FEATURE_NODE_SSH_TRANSPORT_ENABLED",
        label="SSH transport узлов",
        description="Способ связи SSH (local forward) на странице «Узлы». Требует модуль «Узлы».",
        icon="🔐",
        disable_hint="SSH в picker станет недоступен; http/mtls без изменений.",
        resource_impact_level="low",
        default=False,
        group="app_module",
    ),
    FeatureToggleDefinition(
        key="panel_ops",
        env_key="FEATURE_PANEL_OPS_ENABLED",
        label="Операции панели",
        description="Вкладка «Операции панели»: пересборка фронтенда и связанные действия.",
        icon="🔄",
        disable_hint="Вкладка «Операции панели» и пересборка из неё станут недоступны. Перезапуск панели из баннера модулей останется доступен.",
        resource_impact_level="minimal",
        default=True,
        group="app_module",
        settings_tabs=("panel_ops",),
        api_prefixes=("/api/system/rebuild",),
    ),
    FeatureToggleDefinition(
        key="node_health",
        env_key="NODE_HEALTH_SYNC_ENABLED",
        label="Опрос health узлов",
        description="Фоновый опрос статуса VPN/прокси-узлов.",
        icon="❤️",
        disable_hint="Статусы узлов перестанут обновляться автоматически.",
        resource_impact_level="medium",
        resource_savings="Периодические HTTP-запросы к агентам узлов.",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="cert_sync",
        env_key="CERT_SYNC_ENABLED",
        label="Синхронизация сертификатов OpenVPN",
        description="Фоновая подтяжка сроков сертификатов OpenVPN с узлов в БД.",
        icon="📜",
        disable_hint="Сроки сертификатов в БД перестанут синхронизироваться с узлами.",
        resource_impact_level="low",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="resource_metrics",
        env_key="RESOURCE_METRICS_ENABLED",
        label="Метрики ресурсов VPN-узлов",
        description="Сбор CPU/RAM и связанных метрик с VPN-узлов.",
        icon="📉",
        disable_hint="Графики и история нагрузки узлов перестанут обновляться.",
        resource_impact_level="medium",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="panel_resource_metrics",
        env_key="PANEL_RESOURCE_METRICS_ENABLED",
        label="Метрики ресурсов панели",
        description="Сбор CPU/RAM процесса панели для карточек профилей и мониторинга.",
        icon="📊",
        disable_hint="Живые замеры RAM панели на профилях перестанут обновляться.",
        resource_impact_level="low",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="cidr_scheduler",
        env_key="CIDR_DB_REFRESH_ENABLED",
        label="Планировщик CIDR DB",
        description="Ночное/периодическое автообновление CIDR DB.",
        icon="🗓️",
        disable_hint="Автообновление CIDR DB по расписанию будет отключено (ручной pipeline останется при включённой маршрутизации).",
        resource_impact_level="high",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="node_sync_reconcile",
        env_key="NODE_SYNC_RECONCILE_ENABLED",
        label="Сверка Node Sync",
        description="Фоновый reconcile групп синхронизации узлов.",
        icon="🔁",
        disable_hint="Автоматическая сверка Node Sync будет отключена.",
        resource_impact_level="medium",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="retention",
        env_key="RETENTION_ENABLED",
        label="Автоочистка БД (retention)",
        description="Удаление старых сэмплов трафика, логов и метрик по срокам из Обслуживания.",
        icon="🗑️",
        disable_hint="Автоочистка таблиц истории будет остановлена.",
        resource_impact_level="low",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="key_rotation",
        env_key="FEATURE_KEY_ROTATION_ENABLED",
        label="Ротация API-ключей узлов",
        description="Фоновая ротация API-ключей узлов по сроку (если задан интервал в настройках).",
        icon="🔑",
        disable_hint="Авторотация API-ключей узлов будет отключена (ручная ротация на странице Узлы — при включённом модуле Узлы).",
        resource_impact_level="low",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="user_reminders",
        env_key="SELF_SERVICE_REMINDER_ENABLED",
        label="Напоминания self-service",
        description="Фоновые напоминания пользователям (сертификаты / трафик) через self-service каналы.",
        icon="🔔",
        disable_hint="Автонапоминания self-service будут отключены.",
        resource_impact_level="low",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="alert_rules",
        env_key="ALERT_RULES_ENABLED",
        label="Правила алертов",
        description="Фоновая оценка правил алертов (доставка зависит от Telegram).",
        icon="🚨",
        disable_hint="Правила алертов не будут оцениваться; карточка в мониторинге скроется.",
        resource_impact_level="low",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="noc_reports",
        env_key="NOC_REPORT_ENABLED",
        label="NOC-отчёты по расписанию",
        description="Ежедневные/еженедельные NOC-отчёты (обычно в Telegram).",
        icon="📰",
        disable_hint="Планировщик NOC-отчётов будет отключён.",
        resource_impact_level="low",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="cloudflare_ips_update",
        env_key="CLOUDFLARE_IPS_AUTO_UPDATE",
        label="Автообновление Cloudflare IP",
        description="Периодическое обновление списков IP Cloudflare для proxy-mode.",
        icon="☁️",
        disable_hint="Списки Cloudflare IP не будут обновляться автоматически.",
        resource_impact_level="low",
        default=False,
        group="background",
    ),
    FeatureToggleDefinition(
        key="access_expiry",
        env_key="FEATURE_ACCESS_EXPIRY_ENABLED",
        label="Автоистечение access-until",
        description="Фоновое применение блокировок по сроку access-until / unlock.",
        icon="⏳",
        disable_hint="Истёкший access-until не будет применяться автоматически.",
        resource_impact_level="low",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="connection_history",
        env_key="FEATURE_CONNECTION_HISTORY_ENABLED",
        label="История подключений (сэмплы)",
        description="Фоновый сбор счётчиков подключений для NOC-графиков.",
        icon="📈",
        disable_hint="Сэмплы числа подключений перестанут записываться.",
        resource_impact_level="low",
        default=True,
        group="background",
    ),
)

FEATURE_TOGGLE_BY_KEY = {item.key: item for item in FEATURE_TOGGLES}
FEATURE_TOGGLE_BY_ENV = {item.env_key: item for item in FEATURE_TOGGLES}

# Stage 5 (§8.2): resource profiles (Minimal/Standard/Full) are replaced by
# scenario presets. `SCENARIO_PRESETS` is the single source of truth for
# toggles + env + disabled workers + grace months.
LEGACY_RESOURCE_PROFILE_TO_SCENARIO: dict[str, str] = {
    "minimal": "panel_only",
    "standard": "home",
    "full": "commercial",
}


def map_legacy_resource_profile(raw: str) -> str | None:
    """Map a legacy `RESOURCE_PROFILE` value to a scenario key (label only)."""
    key = (raw or "").strip().lower()
    return LEGACY_RESOURCE_PROFILE_TO_SCENARIO.get(key)


# Scenario presets describe loading, not host layout. Host-dependent app modules
# (`awg2`, `proxy_nodes`, `warper`, `routing`, `antizapret_config`,
# `cloudflare_ips_update`, `node_ssh_transport`, VPN protocols) are deliberately
# absent from every preset: enabling a section the operator does not use (or
# hiding one they do) is not a preset's job.
#
# Each preset has three levels:
#   * `required` — hard core: applied and locked against switching off while the
#     scenario is active (only «Коммерческое» has one);
#   * `toggles` — soft defaults: applied once, editable afterwards;
#   * everything else — untouched.
SCENARIO_CUSTOM = "custom"
SCENARIO_BASED_ON_ENV = "SCENARIO_BASED_ON"

# Хотя бы один из этих протоколов должен оставаться включённым всегда.
VPN_PROTOCOL_TOGGLES: tuple[str, ...] = ("openvpn", "wireguard", "amneziawg", "awg2")

SCENARIO_PRESETS: dict[str, dict] = {
    "panel_only": {
        "label": "🖥 Только панель",
        "description": "Панель без локального AntiZapret-набора фоновых задач; минимум collectors.",
        "recommended_ram_gb": 1,
        "panel_mb_delta": -40,
        "impact": {
            "ram": "меньше фоновых процессов панели; VPN на хосте не меняется",
            "cpu_disk": "нет traffic/CIDR/metrics collectors и опроса узлов",
            "note": "Для VDS без AntiZapret на том же хосте — только AdminPanelAZ",
        },
        "workers_disabled": [
            "traffic_collector",
            "node_health",
            "resource_metrics",
            "panel_resource_metrics",
            "cidr_scheduler",
            "cert_sync",
            "resource_monitor",
        ],
        "required": [],
        "match": "full",
        "settings": {"inactive_user_grace_period_months": 0},
        "toggles": {
            # §8.2 + former Minimal remainder
            "clients_page": True,
            "user_provisioning": False,
            "unlock_codes": False,
            "client_portal": False,
            "traffic_sync": False,
            "noc_reports": False,
            "alert_rules": False,
            "warper": False,
            "server_monitor": False,
            "telegram": False,
            "node_sync_reconcile": False,
            "cloudflare_ips_update": False,
            "edit_files": True,
            "node_ssh_transport": True,
            "server_resources": False,
            # Bridge until platform-cleanup 03 merges `server_resources`.
            "resource_monitor": False,
            "resource_metrics": False,
            "panel_resource_metrics": False,
            "wg_policy_sync": False,
            "logs_dashboard": False,
            "routing": False,
            "antizapret_config": False,
            "diagnostics_tests": False,
            "runtime_backup_cleanup": True,
            "nightly_idle_restart": True,
            "active_web_sessions": True,
            "node_health": False,
            "cert_sync": False,
            "cidr_scheduler": False,
            "retention": True,
            "key_rotation": True,
            "user_reminders": False,
            "access_expiry": True,
            "connection_history": False,
        },
        "env": {
            "SCENARIO_PRESET": "panel_only",
            "UVICORN_WORKERS": "1",
            "TRAFFIC_SYNC_ENABLED": "false",
            "WG_POLICY_SYNC_ENABLED": "false",
            "SERVER_RESOURCES_ENABLED": "false",
            "MONITOR_ENABLED": "false",
            "RESOURCE_METRICS_ENABLED": "false",
            "PANEL_RESOURCE_METRICS_ENABLED": "false",
            "NODE_HEALTH_SYNC_ENABLED": "false",
            "CERT_SYNC_ENABLED": "false",
            "CIDR_DB_REFRESH_ENABLED": "false",
            "NODE_SYNC_RECONCILE_ENABLED": "false",
            "RETENTION_ENABLED": "true",
            "FEATURE_KEY_ROTATION_ENABLED": "true",
            "SELF_SERVICE_REMINDER_ENABLED": "false",
            "ALERT_RULES_ENABLED": "false",
            "NOC_REPORT_ENABLED": "false",
            "CLOUDFLARE_IPS_AUTO_UPDATE": "false",
            "FEATURE_ACCESS_EXPIRY_ENABLED": "true",
            "FEATURE_CONNECTION_HISTORY_ENABLED": "false",
            "INACTIVE_USER_GRACE_PERIOD_MONTHS": "0",
        },
    },
    "home": {
        "label": "🏠 Домашнее",
        "description": "Семейный/личный сервер: мониторинг и узлы без коммерческих модулей.",
        "recommended_ram_gb": 1,
        "panel_mb_delta": -20,
        "impact": {
            "ram": "чуть меньше RAM панели, чем Коммерческое; VPN на хосте тот же",
            "cpu_disk": "без CIDR auto-scheduler и без commercial toggles",
            "note": "Ориентир 1 GB+; замер стека — на карточке текущего пресета в UI",
        },
        "workers_disabled": ["cidr_scheduler"],
        "required": [],
        "match": "on",
        "settings": {"inactive_user_grace_period_months": 0},
        "toggles": {
            "clients_page": True,
            "user_provisioning": False,
            "unlock_codes": False,
            "client_portal": False,
            "traffic_sync": False,
            "noc_reports": False,
            "alert_rules": False,
            "warper": False,
            "server_monitor": True,
            "telegram": True,
            "node_sync_reconcile": True,
            "cloudflare_ips_update": True,
            "edit_files": True,
            "node_ssh_transport": True,
            "server_resources": True,
            # Bridge until platform-cleanup 03 merges `server_resources`.
            "resource_monitor": True,
            "resource_metrics": True,
            "panel_resource_metrics": True,
            "wg_policy_sync": True,
            "logs_dashboard": True,
            "routing": True,
            "antizapret_config": True,
            "diagnostics_tests": True,
            "runtime_backup_cleanup": True,
            "nightly_idle_restart": True,
            "active_web_sessions": True,
            "node_health": True,
            "cert_sync": True,
            "cidr_scheduler": False,
            "retention": True,
            "key_rotation": True,
            "user_reminders": True,
            "access_expiry": True,
            "connection_history": True,
        },
        "env": {
            "SCENARIO_PRESET": "home",
            "UVICORN_WORKERS": "1",
            "TRAFFIC_SYNC_ENABLED": "false",
            "WG_POLICY_SYNC_ENABLED": "true",
            "SERVER_RESOURCES_ENABLED": "true",
            "MONITOR_ENABLED": "true",
            "RESOURCE_METRICS_ENABLED": "true",
            "PANEL_RESOURCE_METRICS_ENABLED": "true",
            "NODE_HEALTH_SYNC_ENABLED": "true",
            "CERT_SYNC_ENABLED": "true",
            "CIDR_DB_REFRESH_ENABLED": "false",
            "NODE_SYNC_RECONCILE_ENABLED": "true",
            "RETENTION_ENABLED": "true",
            "FEATURE_KEY_ROTATION_ENABLED": "true",
            "SELF_SERVICE_REMINDER_ENABLED": "true",
            "ALERT_RULES_ENABLED": "false",
            "NOC_REPORT_ENABLED": "false",
            "CLOUDFLARE_IPS_AUTO_UPDATE": "true",
            "FEATURE_ACCESS_EXPIRY_ENABLED": "true",
            "FEATURE_CONNECTION_HISTORY_ENABLED": "true",
            "INACTIVE_USER_GRACE_PERIOD_MONTHS": "0",
        },
    },
    "commercial": {
        "label": "💼 Коммерческое",
        "description": "Все разделы для распространения доступа: provisioning, портал, unlock, отчёты.",
        "recommended_ram_gb": 1,
        "panel_mb_delta": 0,
        "impact": {
            "ram": "максимум фоновых задач панели; VPN на хосте тот же",
            "cpu_disk": "полная фоновая нагрузка collectors",
            "note": "Замер «панель + VPN на сервере»; лучше 2 GB с запасом под ОС",
        },
        "workers_disabled": [],
        # Жёсткое ядро: без этих модулей коммерческий сценарий работает
        # неполноценно или падает. Заблокированы от выключения, пока сценарий активен.
        "required": [
            "user_management",
            "clients_page",
            "user_provisioning",
            "telegram",
            "traffic_sync",
            "unlock_codes",
            "client_portal",
            "access_expiry",
            "connection_history",
            "noc_reports",
            "alert_rules",
        ],
        "match": "required",
        "settings": {"inactive_user_grace_period_months": 3},
        # Мягкие дефолты: включаются сценарием, но админ может выключить.
        "toggles": {
            "user_reminders": True,
            "qr_downloads": True,
            "server_monitor": True,
            "logs_dashboard": True,
            "server_resources": True,
            # Bridge until platform-cleanup 03 merges `server_resources`.
            "resource_monitor": True,
            "resource_metrics": True,
            "panel_resource_metrics": True,
            "node_health": True,
            "cert_sync": True,
            "wg_policy_sync": True,
            "node_sync_reconcile": True,
            "cidr_scheduler": True,
        },
        "env": {
            "SCENARIO_PRESET": "commercial",
            "UVICORN_WORKERS": "1",
            "TRAFFIC_SYNC_ENABLED": "true",
            "WG_POLICY_SYNC_ENABLED": "true",
            "SERVER_RESOURCES_ENABLED": "true",
            "MONITOR_ENABLED": "true",
            "RESOURCE_METRICS_ENABLED": "true",
            "PANEL_RESOURCE_METRICS_ENABLED": "true",
            "NODE_HEALTH_SYNC_ENABLED": "true",
            "CERT_SYNC_ENABLED": "true",
            "CIDR_DB_REFRESH_ENABLED": "true",
            "NODE_SYNC_RECONCILE_ENABLED": "true",
            "RETENTION_ENABLED": "true",
            "FEATURE_KEY_ROTATION_ENABLED": "true",
            "SELF_SERVICE_REMINDER_ENABLED": "true",
            "ALERT_RULES_ENABLED": "true",
            "NOC_REPORT_ENABLED": "true",
            "FEATURE_ACCESS_EXPIRY_ENABLED": "true",
            "FEATURE_CONNECTION_HISTORY_ENABLED": "true",
            "INACTIVE_USER_GRACE_PERIOD_MONTHS": "3",
        },
    },
}

VALID_SCENARIO_PRESETS = frozenset(SCENARIO_PRESETS.keys())

FRONTEND_PATH_TO_MODULE: dict[str, str] = {}
SETTINGS_TAB_TO_MODULE: dict[str, str] = {}
for _item in FEATURE_TOGGLES:
    for _path in _item.frontend_paths:
        FRONTEND_PATH_TO_MODULE[_path] = _item.key
    for _tab in _item.settings_tabs:
        SETTINGS_TAB_TO_MODULE[_tab] = _item.key


class FeatureToggleService:
    """Env-backed feature toggles with a per-instance parsed-.env cache.

    Cache is keyed by file mtime so external writers (install scripts, manual
    edits) are picked up without re-reading the file on every ``is_enabled``
    call. Writes through this service invalidate immediately.
    """

    def __init__(self, env_path: Path):
        self.env_path = Path(env_path)
        self.env = EnvFileService(self.env_path)
        self._env_map_cache: dict[str, str] | None = None
        self._env_map_mtime: float | None = None

    def _invalidate_env_map(self) -> None:
        self._env_map_cache = None
        self._env_map_mtime = None

    def _env_map(self) -> dict[str, str]:
        path = self.env_path
        try:
            mtime = path.stat().st_mtime if path.exists() else None
        except OSError:
            mtime = None
        if self._env_map_cache is not None and self._env_map_mtime == mtime:
            return self._env_map_cache

        values: dict[str, str] = {}
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                text = ""
            for raw in text.splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()

        self._env_map_cache = values
        self._env_map_mtime = mtime
        return values

    def _raw_env(self, key: str, default: str = "") -> str:
        values = self._env_map()
        if key in values:
            return values[key]
        return os.getenv(key, default)

    def is_enabled(self, key: str) -> bool:
        definition = FEATURE_TOGGLE_BY_KEY.get(key)
        if definition is None:
            return True
        raw = self._raw_env(definition.env_key, "")
        if not raw:
            return definition.default
        return _parse_bool(raw, default=definition.default)

    def get_feature_states(self) -> dict[str, bool]:
        # One map load for all toggles (avoids N full-file scans).
        self._env_map()
        return {definition.key: self.is_enabled(definition.key) for definition in FEATURE_TOGGLES}


    def list_toggles(self) -> dict:
        self._env_map()
        required = self._scenario_required_keys()
        scenario = self.get_scenario_preset()
        scenario_label = SCENARIO_PRESETS.get(scenario, {}).get("label", "")
        last_protocol = self._last_protocol_toggle()
        items = []
        enabled_count = 0
        for definition in FEATURE_TOGGLES:
            enabled = self.is_enabled(definition.key)
            if enabled:
                enabled_count += 1
            impact = RESOURCE_IMPACT_LEVELS.get(definition.resource_impact_level, RESOURCE_IMPACT_LEVELS["low"])
            lock_reason = None
            if enabled and definition.key in required:
                lock_reason = (
                    f"Обязательный модуль сценария «{scenario_label}». "
                    "Чтобы отключить, смените сценарий или снимите ограничения."
                )
            elif enabled and definition.key == last_protocol:
                lock_reason = (
                    "Должен оставаться хотя бы один VPN-протокол — сначала включите другой."
                )
            items.append({
                **asdict(definition),
                "enabled": enabled,
                "resource_impact_label": impact["label"],
                "group_meta": FEATURE_TOGGLE_GROUPS.get(definition.group, {}),
                "locked": lock_reason is not None,
                "lock_reason": lock_reason,
            })
        return {
            "items": items,
            "groups": FEATURE_TOGGLE_GROUPS,
            "total": len(items),
            "enabled_count": enabled_count,
            "disabled_count": len(items) - enabled_count,
        }

    def update_toggles(
        self, updates: dict[str, bool], db: Session | None = None
    ) -> dict:
        for key in updates:
            definition = FEATURE_TOGGLE_BY_KEY.get(key)
            if definition is None:
                raise ValueError(f"Неизвестный модуль: {key}")

        intended = {key: self.is_enabled(key) for key in FEATURE_TOGGLE_BY_KEY}
        intended.update({key: bool(value) for key, value in updates.items()})

        required = self._scenario_required_keys()
        if required:
            scenario = self.get_scenario_preset()
            scenario_label = SCENARIO_PRESETS[scenario]["label"]
            blocked = [
                FEATURE_TOGGLE_BY_KEY[key].label
                for key, value in updates.items()
                if value is False and key in required and self.is_enabled(key)
            ]
            if blocked:
                names = ", ".join(f"«{label}»" for label in blocked)
                raise ValueError(
                    f"{names} — обязательные модули сценария «{scenario_label}». "
                    "Смените сценарий или снимите ограничения, чтобы отключить их."
                )

        # «Пользователи (абоненты)» работают поверх «Пользователи и доступ»:
        # выключение user_management тянет за собой user_provisioning.
        if "user_management" in updates and not updates["user_management"]:
            updates = dict(updates)
            updates["user_provisioning"] = False
            intended["user_provisioning"] = False

        self._validate_intended_toggles(intended)

        for key, enabled in updates.items():
            definition = FEATURE_TOGGLE_BY_KEY[key]
            self.env.set_env_value(definition.env_key, "true" if enabled else "false")
        self._invalidate_env_map()
        # Выключение сбора трафика снимает все пользовательские блоки user_traffic_limit.
        if (
            db is not None
            and "traffic_sync" in updates
            and not updates["traffic_sync"]
            and intended.get("traffic_sync", False)
        ):
            from app.services.user_traffic_limit import _lift_all_user_traffic_blocks

            _lift_all_user_traffic_blocks(db)
        return self.list_toggles()

    def get_scenario_preset(self) -> str:
        """Last applied scenario (label only — never rewrites stored toggles).

        ``custom`` means «сняты ограничения»: toggles are free, no locks apply.
        """
        raw = (self._raw_env("SCENARIO_PRESET", "") or "").strip().lower()
        if raw == SCENARIO_CUSTOM:
            return SCENARIO_CUSTOM
        if raw in VALID_SCENARIO_PRESETS:
            return raw
        mapped = map_legacy_resource_profile(self._raw_env("RESOURCE_PROFILE", ""))
        if mapped:
            return mapped
        return "home"

    def _current_grace_months(self, db: Session | None = None) -> int:
        """Runtime grace: AppSetting when ``db`` is given; else .env (install/CLI)."""
        if db is not None:
            from app.services.user_grace import get_grace_months

            return get_grace_months(db)
        raw = (self._raw_env("INACTIVE_USER_GRACE_PERIOD_MONTHS", "0") or "0").strip()
        try:
            value = int(raw)
        except ValueError:
            return 0
        return value if value in {0, 1, 2, 3, 6, 12} else 0

    def _scenario_required_keys(self) -> frozenset[str]:
        """Toggles locked by the scenario that is currently applied."""
        meta = SCENARIO_PRESETS.get(self.get_scenario_preset())
        if meta is None:
            return frozenset()
        return frozenset(meta.get("required", ()))

    def _last_protocol_toggle(self) -> str | None:
        """The only enabled VPN protocol, if exactly one is left."""
        enabled = [key for key in VPN_PROTOCOL_TOGGLES if self.is_enabled(key)]
        return enabled[0] if len(enabled) == 1 else None

    def _preset_toggles(self, preset_key: str) -> dict[str, bool]:
        """What a preset applies: hard ``required`` core + soft ``toggles``."""
        meta = SCENARIO_PRESETS[preset_key]
        merged = {key: True for key in meta.get("required", ())}
        merged.update(meta.get("toggles", {}))
        return merged

    def _scenario_mismatches(self, preset_key: str) -> tuple[list[str], list[str]]:
        """Toggles that keep the label from matching this scenario.

        ``required`` (Коммерческое) — only the hard core matters; soft defaults
        and extra modules never demote the badge.
        ``on`` (Домашнее) — the preset's explicit "on" set must be present;
        enabling extra modules does not demote it.
        ``full`` (Только панель) — exact match: an extra module leaves the
        minimal profile.
        """
        meta = SCENARIO_PRESETS[preset_key]
        match = meta.get("match")
        if match == "required":
            return [key for key in meta.get("required", ()) if not self.is_enabled(key)], []
        toggles = {
            key: enabled
            for key, enabled in meta.get("toggles", {}).items()
            if key in FEATURE_TOGGLE_BY_KEY
        }
        missing = [key for key, enabled in toggles.items() if enabled and not self.is_enabled(key)]
        extra: list[str] = []
        if match == "full":
            extra = [key for key, enabled in toggles.items() if not enabled and self.is_enabled(key)]
        return missing, extra

    def _scenario_changed_count(self, preset_key: str) -> int:
        """How many preset-owned toggles differ, for the «изменено: N» badge."""
        missing, extra = self._scenario_mismatches(preset_key)
        changed = set(missing) | set(extra)
        meta = SCENARIO_PRESETS[preset_key]
        if meta.get("match") == "required":
            for key, enabled in meta.get("toggles", {}).items():
                if key in FEATURE_TOGGLE_BY_KEY and self.is_enabled(key) != enabled:
                    changed.add(key)
        return len(changed)

    def _scenario_changed_total(self, preset_key: str, db: Session | None = None) -> int:
        """Toggle changes + a changed grace period, for the custom badge."""
        changed = self._scenario_changed_count(preset_key)
        grace_want = SCENARIO_PRESETS[preset_key]["settings"]["inactive_user_grace_period_months"]
        if self._current_grace_months(db) != grace_want:
            changed += 1
        return changed

    def _validate_intended_toggles(self, intended: dict[str, bool]) -> None:
        # «Клиенты» и «Пользователи (абоненты)» не выключаются одновременно.
        if not intended.get("clients_page", True) and not intended.get("user_provisioning", False):
            raise ValueError(
                "Нельзя отключить «Клиенты» и «Пользователи (абоненты)» одновременно — "
                "хотя бы один раздел должен оставаться включённым."
            )
        # Включение user_provisioning требует включённого user_management.
        if intended.get("user_provisioning", False) and not intended.get("user_management", True):
            raise ValueError(
                "«Пользователи (абоненты)» требуют включённый модуль «Пользователи и доступ»."
            )
        # Панель без VPN-протокола бессмысленна в любом сценарии.
        if not any(intended.get(key, False) for key in VPN_PROTOCOL_TOGGLES):
            raise ValueError(
                "Должен оставаться включённым хотя бы один VPN-протокол: "
                "OpenVPN, WireGuard, AmneziaWG или AZ-AWG2."
            )

    def _custom_scenario_state(
        self, based: str, changed: int, *, last_applied: str | None = None
    ) -> dict:
        base_label = SCENARIO_PRESETS[based]["label"]
        required = sorted(self._scenario_required_keys())
        return {
            "key": SCENARIO_CUSTOM,
            "label": "⚙️ Кастомный",
            "is_custom": True,
            "based_on": based,
            "changed_count": changed,
            "badge_label": f"⚙️ Кастомный (на основе {base_label}, изменено: {changed})",
            "base_label": base_label,
            "last_applied": last_applied or based,
            "locks_active": bool(required),
            "required": required,
            "required_labels": [
                FEATURE_TOGGLE_BY_KEY[item].label
                for item in required
                if item in FEATURE_TOGGLE_BY_KEY
            ],
        }

    def _toggle_diff_against_preset(self, preset_key: str) -> tuple[list[str], list[str]]:
        want = self._preset_toggles(preset_key)
        will_enable: list[str] = []
        will_disable: list[str] = []
        for key, enabled in want.items():
            if key not in FEATURE_TOGGLE_BY_KEY:
                continue
            current = self.is_enabled(key)
            if current == enabled:
                continue
            (will_enable if enabled else will_disable).append(key)
        return will_enable, will_disable

    def _settings_diff_against_preset(self, preset_key: str, db: Session | None = None) -> dict:
        grace_want = SCENARIO_PRESETS[preset_key]["settings"]["inactive_user_grace_period_months"]
        grace_now = self._current_grace_months(db)
        if grace_now == grace_want:
            return {}
        return {
            "inactive_user_grace_period_months": {
                "from": grace_now,
                "to": grace_want,
            }
        }

    def diff_scenario_preset(self, preset: str, db: Session | None = None) -> dict:
        """Raw diff (toggle keys + settings) between the current .env and a preset."""
        normalized = (preset or "").strip().lower()
        if normalized not in SCENARIO_PRESETS:
            raise ValueError(f"Неизвестный сценарий: {preset}")
        will_enable_keys, will_disable_keys = self._toggle_diff_against_preset(normalized)
        return {
            "preset": normalized,
            "will_enable": will_enable_keys,
            "will_disable": will_disable_keys,
            "settings_changes": self._settings_diff_against_preset(normalized, db),
        }

    def preview_scenario_preset(self, preset: str, db: Session | None = None) -> dict:
        """Diff + labels for the UI confirm dialog (nothing is written)."""
        normalized = (preset or "").strip().lower()
        if normalized not in SCENARIO_PRESETS:
            raise ValueError(f"Неизвестный сценарий: {preset}")
        meta = SCENARIO_PRESETS[normalized]
        will_enable_keys, will_disable_keys = self._toggle_diff_against_preset(normalized)

        def labels(keys: list[str]) -> list[str]:
            return [FEATURE_TOGGLE_BY_KEY[k].label for k in keys]

        settings_changes = self._settings_diff_against_preset(normalized, db)
        enable_labels = labels(will_enable_keys)
        disable_labels = labels(will_disable_keys)
        summary_parts: list[str] = []
        if disable_labels:
            summary_parts.append(f"Выключится: {', '.join(disable_labels)}")
        if enable_labels:
            summary_parts.append(f"Включится: {', '.join(enable_labels)}")
        if not summary_parts:
            summary_parts.append("Модули уже соответствуют сценарию")
        return {
            "preset": normalized,
            "label": meta["label"],
            "will_enable_keys": will_enable_keys,
            "will_disable_keys": will_disable_keys,
            "will_enable": enable_labels,
            "will_disable": disable_labels,
            "settings_changes": settings_changes,
            "summary_ru": ". ".join(summary_parts) + ".",
            "required_keys": list(meta.get("required", ())),
            "required_labels": [
                FEATURE_TOGGLE_BY_KEY[key].label
                for key in meta.get("required", ())
                if key in FEATURE_TOGGLE_BY_KEY
            ],
            "workers_disabled": meta.get("workers_disabled", []),
            "impact": meta.get("impact", {}),
        }

    def apply_scenario_preset(self, preset: str, db: Session | None = None) -> dict:
        """Apply a scenario: write env + toggles + grace, drop the legacy label.

        With ``db`` (API path): also writes AppSetting via ``user_grace.set_grace_months``
        — that is what the grace worker reads. Install/CLI may omit ``db`` and only
        touch ``.env``.
        """
        normalized = (preset or "").strip().lower()
        if normalized not in SCENARIO_PRESETS:
            raise ValueError(f"Неизвестный сценарий: {preset}")
        meta = SCENARIO_PRESETS[normalized]
        toggles = self._preset_toggles(normalized)
        intended = {key: self.is_enabled(key) for key in FEATURE_TOGGLE_BY_KEY}
        intended.update(toggles)
        self._validate_intended_toggles(intended)
        traffic_was_enabled = self.is_enabled("traffic_sync")
        for env_key, value in meta.get("env", {}).items():
            self.env.set_env_value(env_key, str(value))
        for toggle_key, enabled in toggles.items():
            definition = FEATURE_TOGGLE_BY_KEY.get(toggle_key)
            if definition is None:
                continue
            self.env.set_env_value(definition.env_key, "true" if enabled else "false")
        self.env.remove_env_key("RESOURCE_PROFILE")
        self.env.remove_env_key(SCENARIO_BASED_ON_ENV)
        self._invalidate_env_map()
        if db is not None and traffic_was_enabled and not intended.get("traffic_sync", False):
            from app.services.user_traffic_limit import _lift_all_user_traffic_blocks

            _lift_all_user_traffic_blocks(db)
        grace_months = int(meta["settings"]["inactive_user_grace_period_months"])
        if db is not None:
            from app.services.user_grace import set_grace_months

            set_grace_months(db, grace_months)
        return {
            "preset": normalized,
            "requires_restart": True,
            "impact": meta.get("impact", {}),
            "workers_disabled": meta.get("workers_disabled", []),
            "toggles": self.list_toggles(),
            "presets": self.list_scenario_presets(db),
        }

    def resolve_scenario_state(self, db: Session | None = None) -> dict:
        """Current scenario or the computed «Кастомный» state.

        The label follows the last applied scenario: «Коммерческое» matches by
        its locked core, while soft defaults and extra modules never demote the
        badge. «Домашнее» / «Только панель» match by their explicit "on" set
        (panel_only additionally rejects extra modules). A different preset is
        never guessed from the toggle soup — switching scenarios is explicit.
        """
        last = self.get_scenario_preset()
        if last == SCENARIO_CUSTOM:
            based = (self._raw_env(SCENARIO_BASED_ON_ENV, "") or "").strip().lower()
            if based not in SCENARIO_PRESETS:
                based = "home"
            return self._custom_scenario_state(based, self._scenario_changed_total(based, db))

        based = last if last in SCENARIO_PRESETS else "home"
        meta = SCENARIO_PRESETS[based]
        missing, extra = self._scenario_mismatches(based)
        grace_want = meta["settings"]["inactive_user_grace_period_months"]
        if not missing and not extra and self._current_grace_months(db) == grace_want:
            required = list(meta.get("required", ()))
            return {
                "key": based,
                "label": meta["label"],
                "is_custom": False,
                "based_on": based,
                "changed_count": 0,
                "badge_label": meta["label"],
                "last_applied": last,
                "locks_active": bool(required),
                "required": required,
                "required_labels": [
                    FEATURE_TOGGLE_BY_KEY[item].label
                    for item in required
                    if item in FEATURE_TOGGLE_BY_KEY
                ],
            }
        return self._custom_scenario_state(
            based,
            self._scenario_changed_total(based, db),
            last_applied=last if last in SCENARIO_PRESETS else None,
        )

    def list_scenario_presets(self, db: Session | None = None) -> dict:
        resolved = self.resolve_scenario_state(db)
        items = []
        for key, meta in SCENARIO_PRESETS.items():
            required = list(meta.get("required", ()))
            items.append({
                "key": key,
                "label": meta["label"],
                "description": meta["description"],
                "recommended_ram_gb": meta.get("recommended_ram_gb"),
                "panel_mb_delta": meta.get("panel_mb_delta", 0),
                "impact": meta.get("impact", {}),
                "workers_disabled": meta.get("workers_disabled", []),
                "required": required,
                "required_labels": [
                    FEATURE_TOGGLE_BY_KEY[item].label
                    for item in required
                    if item in FEATURE_TOGGLE_BY_KEY
                ],
                "active": (not resolved["is_custom"]) and resolved["key"] == key,
            })
        return {
            "current_preset": resolved["key"] if not resolved["is_custom"] else SCENARIO_CUSTOM,
            "last_applied": resolved["last_applied"],
            "resolved": resolved,
            "requires_restart": True,
            "items": items,
        }

    def clear_scenario_locks(self, db: Session | None = None) -> dict:
        """Drop the strict-mode locks without touching any toggle.

        The scenario becomes «Кастомный»; the previous preset is remembered as
        the base for the badge and for «Сбросить к пресету».
        """
        last = self.get_scenario_preset()
        based = last if last in SCENARIO_PRESETS else (
            (self._raw_env(SCENARIO_BASED_ON_ENV, "") or "").strip().lower()
        )
        if based not in SCENARIO_PRESETS:
            based = "home"
        self.env.set_env_value("SCENARIO_PRESET", SCENARIO_CUSTOM)
        self.env.set_env_value(SCENARIO_BASED_ON_ENV, based)
        self._invalidate_env_map()
        return self.list_scenario_presets(db)

    def migrate_resource_profile_label_only(self) -> bool:
        """Rename RESOURCE_PROFILE → SCENARIO_PRESET. Never rewrite toggles."""
        changed = False
        has_scenario = self.env.env_key_defined_in_file("SCENARIO_PRESET")
        legacy_raw = self.env.get_env_value("RESOURCE_PROFILE", "")
        if not has_scenario:
            mapped = map_legacy_resource_profile(legacy_raw)
            if mapped:
                self.env.set_env_value("SCENARIO_PRESET", mapped)
                changed = True
        if self.env.env_key_defined_in_file("RESOURCE_PROFILE"):
            self.env.remove_env_key("RESOURCE_PROFILE")
            changed = True
        if changed:
            self._invalidate_env_map()
        return changed


def is_proxy_nodes_enabled(db=None) -> bool:
    """Return whether the proxy_nodes feature toggle is enabled.

    ``db`` is unused (toggle is env-backed) and kept for call-site parity with
    other ``is_*_enabled(db)`` helpers. Prefer this over middleware path guards:
    ``/api/nodes`` is ALWAYS_ALLOWED.
    """
    from app.services.feature_guards import get_feature_service

    _ = db
    return get_feature_service().is_enabled("proxy_nodes")


def is_nodes_enabled(db=None) -> bool:
    """Admin Nodes UI/mutations gate. ``/api/nodes`` stays ALWAYS_ALLOWED."""
    from app.services.feature_guards import get_feature_service

    _ = db
    return get_feature_service().is_enabled("nodes")


def is_node_ssh_transport_enabled(db=None) -> bool:
    """Return whether the SSH transport option is enabled for nodes."""
    from app.services.feature_guards import get_feature_service

    _ = db
    return get_feature_service().is_enabled("node_ssh_transport")


def is_awg2_enabled(db=None) -> bool:
    """Return whether the awg2 feature toggle is enabled.

    ``db`` is unused (toggle is env-backed) and kept for call-site parity with
    other ``is_*_enabled(db)`` helpers.
    """
    from app.services.feature_guards import get_feature_service

    _ = db
    return get_feature_service().is_enabled("awg2")
