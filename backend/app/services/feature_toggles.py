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
        key="resource_monitor",
        env_key="MONITOR_ENABLED",
        label="Мониторинг нагрузки CPU/RAM",
        description="Фоновый мониторинг загрузки сервера.",
        icon="📈",
        disable_hint="Мониторинг нагрузки CPU/RAM будет отключён.",
        resource_impact_level="low",
        default=True,
        group="background",
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
        key="logs_dashboard",
        env_key="FEATURE_LOGS_DASHBOARD_ENABLED",
        label="Подключённые клиенты / трафик",
        description="Разделы «Подключённые клиенты» и «Мониторинг трафика».",
        icon="📋",
        disable_hint="Разделы трафика и логов станут недоступны.",
        resource_impact_level="low",
        default=True,
        group="app_module",
        api_prefixes=("/api/logs",),
        api_paths=("/api/monitoring/overview",),
        frontend_paths=("/monitoring", "/logs"),
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
