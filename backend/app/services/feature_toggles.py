"""Feature toggle registry (ported from AdminAntizapret 1.9.0)."""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from app.services.env_file import EnvFileService

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
        description="Раздел «Маршрутизация / CIDR».",
        icon="🗺️",
        disable_hint="Раздел маршрутизации будет недоступен.",
        resource_impact_level="minimal",
        default=True,
        group="app_module",
        api_prefixes=("/api/routing",),
        frontend_paths=("/routing",),
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
        description="Telegram-авторизация и Mini App.",
        icon="✈️",
        disable_hint="Вход через Telegram и Mini App будут недоступны.",
        resource_impact_level="low",
        default=True,
        group="app_module",
        api_prefixes=("/api/tg-mini",),
        api_paths=("/api/auth/telegram", "/api/auth/telegram/config"),
        settings_tabs=("telegram",),
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
        label="Тесты и диагностика",
        description="Вкладка «Тесты» с in-panel pytest.",
        icon="🧪",
        disable_hint="Вкладка тестов будет недоступна.",
        resource_impact_level="medium",
        default=True,
        group="app_module",
        api_prefixes=("/api/tests",),
        settings_tabs=("tests",),
    ),
    FeatureToggleDefinition(
        key="user_management",
        env_key="FEATURE_USER_MANAGEMENT_ENABLED",
        label="Пользователи и доступ",
        description="Вкладка «Пользователи»: учётные записи, роли и права viewer на конфиги.",
        icon="👤",
        disable_hint="Вкладка «Пользователи» и API управления пользователями станут недоступны.",
        resource_impact_level="minimal",
        default=True,
        group="app_module",
        api_prefixes=("/api/users", "/api/system/viewer-access"),
        settings_tabs=("users",),
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
        key="vpn_network",
        env_key="FEATURE_VPN_NETWORK_ENABLED",
        label="Порт, HTTPS и Nginx",
        description="Вкладка «Порт, HTTPS и Nginx»: публикация панели и reverse-proxy (фаза 17).",
        icon="🌐",
        disable_hint="Вкладка «Порт, HTTPS и Nginx» будет недоступна.",
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
)

FEATURE_TOGGLE_BY_KEY = {item.key: item for item in FEATURE_TOGGLES}
FEATURE_TOGGLE_BY_ENV = {item.env_key: item for item in FEATURE_TOGGLES}

FRONTEND_PATH_TO_MODULE: dict[str, str] = {}
SETTINGS_TAB_TO_MODULE: dict[str, str] = {}
for _item in FEATURE_TOGGLES:
    for _path in _item.frontend_paths:
        FRONTEND_PATH_TO_MODULE[_path] = _item.key
    for _tab in _item.settings_tabs:
        SETTINGS_TAB_TO_MODULE[_tab] = _item.key


def _parse_bool(raw: str | None, *, default: bool) -> bool:
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


class FeatureToggleService:
    def __init__(self, env_path: Path):
        self.env = EnvFileService(env_path)

    def is_enabled(self, key: str) -> bool:
        definition = FEATURE_TOGGLE_BY_KEY.get(key)
        if definition is None:
            return True
        raw = self.env.get_env_value(definition.env_key, "")
        if not raw:
            return definition.default
        return _parse_bool(raw, default=definition.default)

    def get_feature_states(self) -> dict[str, bool]:
        return {definition.key: self.is_enabled(definition.key) for definition in FEATURE_TOGGLES}

    def get_app_module_states(self) -> dict[str, bool]:
        return {
            definition.key: self.is_enabled(definition.key)
            for definition in FEATURE_TOGGLES
            if definition.group == "app_module"
        }

    def list_toggles(self) -> dict:
        items = []
        enabled_count = 0
        for definition in FEATURE_TOGGLES:
            enabled = self.is_enabled(definition.key)
            if enabled:
                enabled_count += 1
            impact = RESOURCE_IMPACT_LEVELS.get(definition.resource_impact_level, RESOURCE_IMPACT_LEVELS["low"])
            items.append({
                **asdict(definition),
                "enabled": enabled,
                "resource_impact_label": impact["label"],
                "group_meta": FEATURE_TOGGLE_GROUPS.get(definition.group, {}),
            })
        return {
            "items": items,
            "groups": FEATURE_TOGGLE_GROUPS,
            "total": len(items),
            "enabled_count": enabled_count,
            "disabled_count": len(items) - enabled_count,
        }

    def update_toggles(self, updates: dict[str, bool]) -> dict:
        for key, enabled in updates.items():
            definition = FEATURE_TOGGLE_BY_KEY.get(key)
            if definition is None:
                raise ValueError(f"Неизвестный модуль: {key}")
            self.env.set_env_value(definition.env_key, "true" if enabled else "false")
        return self.list_toggles()
