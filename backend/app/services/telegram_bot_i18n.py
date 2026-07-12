"""Russian UI strings for the Telegram bot (single-locale dictionary)."""

from __future__ import annotations

# --- Shared helpers ---


def on_off(value: bool) -> str:
    return "ВКЛ" if value else "ВЫКЛ"


def yes_no(value: bool) -> str:
    return "✅" if value else "❌"


def token_set(value: bool) -> str:
    return "задан" if value else "не задан"


def webhook_registered(value: bool) -> str:
    return "зарег." if value else "нет"


def firewall_active(value: bool) -> str:
    return "активен" if value else "нет"


# --- Common ---

UNLINKED = (
    "Аккаунт Telegram не привязан к панели.\n\n"
    "1. Войдите в панель → <b>Настройки → Личное</b>\n"
    "2. Получите код привязки в блоке Telegram\n"
    "3. Отправьте боту: <code>/link &lt;код&gt;</code>"
)

UNKNOWN_COMMAND = "Неизвестная команда. Откройте меню или /help"
UNKNOWN_TEXT = "Не понял сообщение.\n\nВыберите раздел в меню внизу или отправьте /start."
ADMIN_ONLY = "Команда доступна только администратору."
INSUFFICIENT_PERMISSIONS = "Недостаточно прав."
VALUE_EMPTY = "Значение не может быть пустым."
MODULE_DISABLED = "Модуль «{name}» отключён в настройках панели."

# --- Buttons ---

BTN_OPEN_MINI_APP = "📱 Открыть Mini App"
BTN_OPEN_MINI_APP_CONFIG = "📱 Открыть в Mini App"
BTN_HELP = "❓ Помощь"
BTN_ALL_CONFIGS = "📁 Все конфиги"
BTN_BACK = "◀️ Назад"
BTN_BACK_SETTINGS = "◀️ Настройки"
BTN_REFRESH = "🔄 Обновить"
BTN_NODES_HEALTH = "🩺 Проверить связь"
BTN_NODES_ACTIVATE = "⭐ Сделать активным"
BTN_NODES_BACK = "◀️ К списку узлов"

BTN_SETTINGS_TELEGRAM = "Telegram"
BTN_SETTINGS_NOTIFY = "Уведомления"
BTN_SETTINGS_BACKUPS = "Бэкапы"
BTN_SETTINGS_MONITOR = "Мониторинг"
BTN_SETTINGS_SECURITY = "Безопасность"
BTN_SETTINGS_MAINTENANCE = "Обслуживание"

# --- Main menu (Reply Keyboard + inline nav) ---

BTN_MENU_STATUS = "📊 Статус"
BTN_MENU_CONFIGS = "📁 Конфиги"
BTN_MENU_MORE = "⋯ Ещё"
BTN_MENU_TRAFFIC = "📈 Трафик"
BTN_MENU_HELP = BTN_HELP
BTN_MENU_HOME = "🏠 Главная"
BTN_MENU_SETTINGS = "⚙️ Настройки"
BTN_MENU_NODES = "🖥 Узлы"
BTN_MENU_CIDR = "🗂 CIDR"
BTN_MENU_WARPER = "🌐 WARP"

MENU_KEYBOARD_PLACEHOLDER = "Конфиги, статус или Ещё…"
MENU_MORE_TITLE = "📋 <b>Дополнительно</b>\n\n<i>Остальные разделы — кнопками ниже.</i>"

MENU_ACTIONS: dict[str, str] = {
    BTN_MENU_STATUS: "status",
    BTN_MENU_CONFIGS: "configs",
    BTN_MENU_MORE: "more",
    BTN_MENU_TRAFFIC: "traffic",
    BTN_MENU_HELP: "help",
    BTN_MENU_HOME: "home",
    BTN_MENU_SETTINGS: "settings",
    BTN_MENU_NODES: "nodes",
    BTN_MENU_CIDR: "cidr",
    BTN_MENU_WARPER: "warper",
    # Старые подписи кнопок (до обновления меню)
    "🌐 AZ-WARP": "warper",
}

BOT_COMMANDS: tuple[tuple[str, str], ...] = (
    ("start", "Главное меню"),
    ("help", "Справка по командам"),
    ("link", "Привязка аккаунта"),
    ("status", "Статус панели"),
    ("myconfigs", "Мои VPN-конфиги"),
    ("traffic", "Трафик: сводка и топ-5"),
    ("configs", "Список VPN-конфигов"),
    ("config", "Карточка конфига"),
    ("settings", "Настройки панели (admin)"),
    ("nodes", "VPN-узлы (admin)"),
    ("cidr", "Статус CIDR pipeline (admin)"),
    ("warper", "Статус AZ-WARP (admin)"),
)

# --- /start ---

START_TITLE = "👋 <b>AdminPanelAZ Bot</b>"
START_UNLINKED = (
    "{title}\n\n"
    "Привяжите аккаунт панели, чтобы открыть меню:\n"
    "<code>/link &lt;код&gt;</code>\n\n"
    "Код — в панели: <b>Настройки → Личное</b>."
)
START_LINKED = (
    "{title}\n\n"
    "Привет, <b>{username}</b> · {role_display}\n\n"
    "<i>Внизу — Конфиги и Статус; остальное в «⋯ Ещё».</i>"
)
START_ROLE_DISPLAY = {
    "admin": "🔑 Администратор",
    "user": "👤 Пользователь",
    "viewer": "👁 Наблюдатель",
}

# --- /help ---

HELP_TITLE = "❓ <b>Справка</b>"
HELP_SECTION_MAIN = "<b>📌 Основное</b>"
HELP_LINES_MAIN = (
    "• /start — главное меню",
    "• Кнопки <b>Конфиги</b> и <b>Статус</b> — внизу чата",
    "• <b>⋯ Ещё</b> — трафик, помощь и разделы admin",
    "• /help — эта справка",
    "• /link &lt;код&gt; — привязка Telegram",
)
HELP_SECTION_CONFIGS = "<b>📁 Конфиги</b>"
HELP_LINES_CONFIGS = (
    "• Кнопка <b>Конфиги</b> — список и отправка файлов",
    "• /myconfigs — ваши конфиги",
    "• /config &lt;имя&gt; — карточка конфига",
    "• @bot &lt;имя&gt; — inline-поиск конфига",
    "• /traffic — сводка и топ-5 за 24 ч (admin: все конфиги)",
)
HELP_SECTION_ADMIN = "<b>⚙️ Администратор</b>"
HELP_LINES_ADMIN = (
    "• /settings — настройки панели",
    "• /nodes — VPN-узлы",
)
HELP_FOOTER = "<i>💡 Кнопки внизу чата — основной способ навигации.</i>"
HELP_ADMIN_CIDR = "• /cidr — статус CIDR pipeline"
HELP_ADMIN_NODES = "• /nodes — VPN-узлы (health, активация)"
HELP_ADMIN_WARPER = "• /warper — статус AZ-WARP"
HELP_ADMIN_SETTINGS = "/settings — настройки панели (inline-меню)"
HELP_ADMIN_FOOTER = ""
HELP_LINES = HELP_LINES_MAIN

# --- /status ---

STATUS_TITLE = "📊 <b>Статус панели</b>"
STATUS_BODY = (
    "{title}\n\n"
    "🖥 Узел: <b>{node_name}</b>\n"
    "📁 Конфигов: <b>{total_configs}</b>\n"
    "🔐 OpenVPN online: <b>{connected_openvpn}</b>\n"
    "🛡️ WireGuard online: <b>{connected_wireguard}</b>\n"
    "🌐 IP сервера: <code>{server_ip}</code>"
)
STATUS_SERVER_HEADER = "\n🖥 <b>Ресурсы сервера</b>"
STATUS_SERVER_METRICS = (
    "CPU <b>{cpu}%</b> · RAM <b>{ram}%</b> ({mem_used} / {mem_total})\n"
    "Диск <b>{disk}%</b> · аптайм {uptime}"
)
STATUS_SERVER_LOAD = "Load avg: <code>{load_1m}</code> / <code>{load_5m}</code> / <code>{load_15m}</code>"
STATUS_SERVER_NETWORK = "\n🌐 <b>Сеть</b> (сейчас)\n{iface_lines}"
STATUS_SERVER_NETWORK_LINE = "{state} <code>{name}</code> ↑ {tx_mbps} · ↓ {rx_mbps} Mbps"
STATUS_SERVER_NETWORK_EMPTY = "\n🌐 <b>Сеть</b>: интерфейсы не найдены"
STATUS_SERVER_UNAVAILABLE = "\n🖥 <i>Мониторинг сервера ({node_name}) временно недоступен</i>"
STATUS_FOOTER = "\n\n🕐 <i>Обновлено: {timestamp}</i>"

# --- /configs ---

CONFIGS_LIST = (
    "📁 <b>Конфигурации</b> · {filter_label}\n"
    "Стр. {page}/{total_pages} · <b>{count}</b> клиент(ов){hint}\n\n"
    "{preview}\n"
    "<i>Выберите клиента ↓</i>"
)
CONFIGS_FILTER_ALL = "все типы"
CONFIGS_FILTER_OVPN = "🔐 OpenVPN"
CONFIGS_FILTER_WG = "🛡️ WireGuard"
CONFIGS_FILTER_AWG = "🌀 AmneziaWG"
CONFIGS_FILTER_HINT = "\n💡 🔐OVPN · 🛡️WG · 🌀AWG — метка на каждой кнопке"
CONFIGS_FILTER_HINT_WG_AWG = (
    "\n💡 <b>WG</b> — WireGuard · <b>AWG</b> — AmneziaWG"
    "\nПри выборе фильтра сразу откроются файлы нужного типа"
)
CONFIGS_NONE = "📭 Конфигурации не найдены.\n\nСоздайте клиента в веб-панели или Mini App."
CONFIGS_NONE_ON_NODE = (
    "📭 На активном узле нет файлов конфигурации.\n\n"
    "Клиенты есть в панели, но профили на сервере не найдены."
)
CONFIGS_FILTER_EMPTY = "<i>Нет клиентов с файлами этого типа на узле.</i>"

# --- /traffic ---

TRAFFIC_FLEET_TITLE = "📊 <b>Трафик · сводка</b>"
TRAFFIC_USER_TITLE = "📊 <b>Мой трафик</b>"
TRAFFIC_USER_SCOPE = "<i>Только ваши конфиги</i>\n"
TRAFFIC_SUMMARY = (
    "{title}\n\n"
    "🖥 Узел: <b>{node_name}</b>\n"
    "{scope_hint}"
    "Клиентов: <b>{count}</b> · online <b>{active}</b>\n"
    "За 24 ч: <b>{traffic_1d}</b> · всего: <b>{total_all}</b>\n\n"
    "🏆 <b>Топ-5 за сутки</b>\n"
    "{top_lines}"
)
TRAFFIC_TOP_LINE = "{medal} {status} <code>{name}</code> — {traffic}"
TRAFFIC_TOP_EMPTY = "<i>За последние 24 ч трафика нет</i>"
TRAFFIC_NONE = "📭 У вас нет конфигураций для отображения трафика."
TRAFFIC_NO_STATS = "📊 Статистика трафика ещё не собрана."

CONFIG_NOT_FOUND = "Конфиг <code>{name}</code> не найден."
CONFIG_NOT_FOUND_ID = "Конфигурация не найдена."
CONFIG_CARD = (
    "📄 <b>{name}</b>\n"
    "Тип: <code>{vpn_type}</code>\n"
    "ID: <code>{config_id}</code>"
)
CONFIG_SEND_OK = "✅ Конфиг <b>{name}</b> отправлен ({count} файл(ов))"
CONFIG_SEND_OK_ONE = "✅ Файл конфига <b>{name}</b> отправлен в чат"
CONFIG_SEND_FAILED = "❌ Не удалось отправить конфиг: {detail}"
CONFIG_SEND_UNKNOWN = "неизвестная ошибка"
CONFIG_FILES_NONE = "Файлы конфигурации не найдены на узле."
CONFIG_PICK_PROTOCOL = (
    "📄 <b>{name}</b>\n"
    "Тип: <code>{vpn_type}</code>\n\n"
    "Выберите протокол:"
)
CONFIG_PICK_FILE = (
    "📄 <b>{name}</b>\n"
    "{protocol}\n\n"
    "{preview}\n\n"
    "<i>Выберите файл ↓</i>"
)
CONFIG_GROUP_NOT_FOUND = "Группа конфигов не найдена."
CONFIG_FILE_NOT_FOUND = "Файл конфигурации не найден."
BTN_CONFIG_BACK = "◀️ К протоколам"
BTN_CONFIG_PICK_ANOTHER = "📤 Ещё файл"

# --- Inline mode ---

INLINE_MINI_APP_TITLE = "📱 AdminPanelAZ Mini App"
INLINE_MINI_APP_DESC = "Открыть панель в Telegram"
INLINE_MINI_APP_MESSAGE = (
    "📱 <b>AdminPanelAZ Mini App</b>\n\n"
    "Откройте панель для управления конфигами:\n"
    "<code>{mini_app_url}</code>"
)
INLINE_UNLINKED_TITLE = "🔗 Привязка аккаунта"
INLINE_UNLINKED_DESC = "Telegram не привязан к панели"
INLINE_CONFIG_TITLE = "📄 {name} ({vpn_type})"
INLINE_CONFIG_DESC = "{name} · {vpn_type} · {filename}"
INLINE_CONFIG_ARTICLE_DESC = "Конфиг {vpn_type}"
INLINE_CONFIG_MESSAGE = (
    "📄 <b>{name}</b>\n"
    "Тип: <code>{vpn_type}</code>\n\n"
    "Mini App: <code>{mini_app_url}</code>"
)
INLINE_EMPTY_TITLE = "🔍 Ничего не найдено"
INLINE_EMPTY_DESC = "Запрос: {query}"
INLINE_EMPTY_MESSAGE = "Конфиги по запросу <code>{query}</code> не найдены."

# --- /settings root ---

SETTINGS_ROOT_TITLE = "⚙️ <b>Настройки панели</b>\n\nВыберите раздел:"
SETTINGS_SECTION_STUB = "Раздел «{section}» — в разработке."

SETTINGS_SECTION_LABELS = {
    "an": "Уведомления",
    "bk": "Бэкапы",
    "mon": "Мониторинг",
    "sec": "Безопасность",
    "mnt": "Обслуживание",
}

# --- /settings → Telegram ---

TG_SETTINGS_TITLE = "📱 <b>Telegram — настройки</b>"
TG_SETTINGS_BODY = (
    "{title}\n\n"
    "Токен: {token_icon} {token_state}\n"
    "Username: <code>{username}</code>\n"
    "Max auth age: <code>{max_age}</code> сек\n"
    "Chat ID: <code>{chat_id}</code>\n"
    "Уведомления: <b>{notify}</b>\n"
    "TG при бэкапе: <b>{notify_backup}</b>\n"
    "Интерактив: <b>{interactive}</b>\n"
    "Webhook: {webhook_icon} {webhook_state}\n"
    "Mini App: <code>{mini_app_url}</code>"
)
TG_USERNAME_DEFAULT = "(не задан)"
TG_CHAT_DEFAULT = "(не задан)"
TG_ASK_USERNAME = "Введите username бота (без @ или с @):"
TG_ASK_CHAT = "Введите Chat ID для уведомлений:"
TG_ASK_AGE = "Введите max auth age (30–86400 сек):"
TG_ASK_TOKEN = "Введите новый токен бота:"
TG_NO_PENDING_TOKEN = "Нет ожидающего токена. Начните заново."
TG_NO_PENDING_TOKEN_SHORT = "Нет ожидающего токена."
TG_AGE_INVALID = "Введите целое число от 30 до 86400."
TG_AGE_RANGE = "Допустимый диапазон: 30–86400 сек."

# --- /settings → Security ---

SEC_TITLE = "🛡 <b>Безопасность</b>"
SEC_BODY = (
    "{title}\n"
    "IP-ограничение: <b>{ip_restriction}</b>\n"
    "iptables whitelist: {fw_icon} {fw_state}\n"
    "Блок сканеров: <b>{block_scanners}</b>\n"
    "Постоянных IP: <code>{allowed_count}</code>\n"
    "Разрешённые: {allowed_preview}\n"
    "Временных IP: <code>{temp_count}</code>\n"
    "Банов сканеров: <code>{ban_count}</code>"
)
SEC_ALLOWED_EMPTY = "(пусто)"
SEC_TEMP_LIST_HEADER = "\nВременный whitelist:"
SEC_TEMP_EMPTY = "Временный whitelist пуст."
SEC_BANS_EMPTY = "Активных банов сканеров нет."
SEC_ASK_ALLOW = "Введите IP или CIDR для постоянного whitelist\n(например <code>192.168.1.0/24</code>):"
SEC_ASK_TEMP = "Введите IP для временного whitelist\n(например <code>1.2.3.4</code>):"
SEC_ENTER_IP_FIRST = "Сначала введите IP."
SEC_INVALID_IP = "Некорректный IP или CIDR."

# --- /settings → Maintenance ---

MNT_TITLE = "🔧 <b>Обслуживание</b>"
MNT_BODY = (
    "{title}\n\n"
    "AntiZapret path:\n<code>{path}</code>\n\n"
    "Опасные операции требуют подтверждения."
)
MNT_RESTART_TITLE = "🔄 <b>Перезапуск службы VPN</b>\n\nВыберите службу:"
MNT_CONFIRM_DOALL = "Запустить doall.sh?\n\nАктивные VPN-сессии будут прерваны."

# --- /settings → Backups ---

BK_TITLE = "📦 <b>Бэкапы</b>"
BK_AUTO = "Авто-бэкап: <b>{state}</b> (интервал {interval} дн.)"
BK_RETENTION = "Хранить копий: <code>{count}</code>"
BK_TG = "TG при бэкапе: <b>{state}</b>"
BK_ARCHIVES = "Архивов на сервере: <b>{count}</b>"
BK_LIST_EMPTY = "Архивов нет."
BK_ASK_FIELD = "Введите {label} ({lo}–{hi}):"
BK_CONFIRM_CREATE = "Создать бэкап панели сейчас?\n(без конфигов VPN и AZ)"
BK_TASK_QUEUED = "Задача поставлена в очередь"
BK_RESTORE_WARN = (
    "Текущие данные будут перезаписаны. "
    "После восстановления панель будет автоматически перезапущена."
)
BK_INT_INVALID = "Введите целое число от {lo} до {hi} ({label})."
BK_FIELD_LABELS = {
    "bk_days": ("интервал авто-бэкапа, дней", 1, 90),
    "bk_ret": ("число хранимых копий", 1, 30),
}

# --- /settings → Monitor ---

MON_TITLE = "📈 <b>Мониторинг</b>"
MON_BODY = (
    "{title}\n\n"
    "Порог CPU: <code>{cpu}%</code>\n"
    "Порог RAM: <code>{ram}%</code>\n"
    "Интервал: <code>{interval}</code> сек\n"
    "Cooldown: <code>{cooldown}</code> сек"
)
MON_ASK_FIELD = "Введите {label} ({lo}–{hi}):"
MON_INT_INVALID = "Введите целое число от {lo} до {hi} ({label})."
MON_FIELD_LABELS = {
    "mon_cpu": ("порог CPU, %", 1, 100),
    "mon_ram": ("порог RAM, %", 1, 100),
    "mon_int": ("интервал проверки, сек", 10, 3600),
    "mon_cd": ("cooldown, сек", 60, 86400),
}

# --- /settings → AdminNotify ---

AN_TITLE = "🔔 <b>AdminNotify</b>"
AN_BODY = (
    "{title}\n\n"
    "Глоб. TG-уведомления: <b>{notify}</b>\n"
    "Токен бота: {token_icon} {token_state}\n"
    "Включено событий: <b>{enabled}/{total}</b>\n\n"
    "Стр. {page}/{total_pages} — нажмите для переключения:"
)
AN_ASK_TG_ID = "Введите Telegram ID для уведомлений (или отправьте «-» для очистки):"

# --- /cidr ---

CIDR_TITLE = "🗂 <b>CIDR pipeline</b>"
CIDR_BODY = (
    "{title}\n\n"
    "Всего CIDR: <code>{total}</code>\n"
    "Последний refresh: <code>{last_status}</code>\n"
    "Завершён: <code>{last_finished}</code>\n"
    "Активная задача: <code>{active_task}</code>\n"
    "Последняя компиляция: <code>{last_compile}</code>\n"
    "Последний deploy: <code>{last_deploy}</code>"
)
CIDR_NONE = "—"
CIDR_ERROR = "Не удалось получить статус CIDR: {detail}"

# --- /warper ---

WARPER_TITLE = "🌐 <b>AZ-WARP</b>"
WARPER_BODY = (
    "{title}\n\n"
    "Узел: <code>{node_name}</code> ({node_host})\n"
    "Статус: <code>{status}</code>"
)
WARPER_DISABLED = MODULE_DISABLED.format(name="AZ-WARP")
WARPER_ERROR = "Не удалось получить статус AZ-WARP: {detail}"

# --- /nodes ---

NODES_NONE = "—"
NODES_LIST_TITLE = "🖥 <b>VPN-узлы</b>"
NODES_LIST = "{title}\n\nСтр. {page}/{total_pages}, всего: <b>{count}</b>\n★ — активный узел"
NODES_EMPTY = "VPN-узлы не найдены. Добавьте узел в веб-панели."
NODES_NOT_FOUND = "Узел не найден."
NODES_ACTIVE_MARK = " ★"
NODES_LOCAL_MARK = " (локальный)"
NODES_TRANSPORT_LOCAL = "локальный"
NODES_TRANSPORT_MTLS = "mTLS"
NODES_TRANSPORT_HTTP = "HTTP"
NODES_CARD_TITLE = "🖥 <b>Узел</b>"
NODES_CARD = (
    "{title}\n\n"
    "<b>{name}</b>{active_mark}{local_mark}\n"
    "Адрес: <code>{host}:{port}</code>\n"
    "Статус: {status_icon} <code>{status}</code>\n"
    "Транспорт: <code>{transport}</code>\n"
    "Последний контакт: <code>{last_seen}</code>"
)
NODES_LINE_SERVER_IP = "IP сервера: <code>{value}</code>"
NODES_LINE_SERVICES = "Службы: <code>{active}/{total}</code>"
NODES_LINE_AGENT = "Node agent: <code>{value}</code>"
NODES_LINE_AZ = "AntiZapret: <code>{value}</code>"
NODES_LINE_ERROR = "Ошибка: <code>{value}</code>"
