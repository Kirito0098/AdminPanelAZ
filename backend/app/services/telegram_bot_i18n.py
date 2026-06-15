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
    "1. Войдите в панель → раздел Telegram\n"
    "2. Получите код привязки (вкладка «Интерактив»)\n"
    "3. Отправьте боту: <code>/link &lt;код&gt;</code>"
)

UNKNOWN_COMMAND = "Неизвестная команда. Откройте меню или /help"
UNKNOWN_TEXT = "Не понял сообщение.\n\nИспользуйте кнопки меню внизу или откройте главное меню."
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
BTN_MENU_HELP = BTN_HELP
BTN_MENU_HOME = "🏠 Главная"
BTN_MENU_SETTINGS = "⚙️ Настройки"
BTN_MENU_NODES = "🖥 Узлы"
BTN_MENU_CIDR = "🗂 CIDR"
BTN_MENU_WARPER = "🌐 AZ-WARP"

MENU_ACTIONS: dict[str, str] = {
    BTN_MENU_STATUS: "status",
    BTN_MENU_CONFIGS: "configs",
    BTN_MENU_HELP: "help",
    BTN_MENU_HOME: "home",
    BTN_MENU_SETTINGS: "settings",
    BTN_MENU_NODES: "nodes",
    BTN_MENU_CIDR: "cidr",
    BTN_MENU_WARPER: "warper",
}

BOT_COMMANDS: tuple[tuple[str, str], ...] = (
    ("start", "Главное меню"),
    ("help", "Справка по командам"),
    ("link", "Привязка аккаунта"),
    ("status", "Статус панели"),
    ("myconfigs", "Мои VPN-конфиги"),
    ("traffic", "Мой трафик"),
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
    "Добро пожаловать! Привяжите аккаунт командой <code>/link &lt;код&gt;</code>.\n"
    "Код можно получить в панели: раздел Telegram → вкладка «Интерактив»."
)
START_LINKED = (
    "{title}\n\n"
    "👤 <code>{username}</code>\n"
    "🔑 {role}\n\n"
    "Выберите действие — кнопки под сообщением или внизу чата.\n"
    "Справка: /help"
)

# --- /help ---

HELP_TITLE = "❓ <b>Справка</b>"
HELP_SECTION_MAIN = "<b>📌 Основное</b>"
HELP_LINES_MAIN = (
    "• /start — главное меню",
    "• /status — статус панели",
    "• /help — эта справка",
    "• /link &lt;код&gt; — привязка Telegram",
)
HELP_SECTION_CONFIGS = "<b>📁 Конфиги</b>"
HELP_LINES_CONFIGS = (
    "• /myconfigs — ваши конфиги",
    "• /configs — список конфигов",
    "• /config &lt;имя&gt; — выбор протокола и отправка файла",
    "• /traffic — трафик ваших клиентов",
    "• OpenVPN / WireGuard / AmneziaWG — отдельные группы",
)
HELP_SECTION_ADMIN = "<b>⚙️ Администратор</b>"
HELP_LINES_ADMIN = (
    "• /settings — настройки панели",
    "• /nodes — VPN-узлы",
)
HELP_FOOTER = "<i>💡 Подсказка: кнопки внизу чата дублируют команды.</i>"
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
    "📁 Конфигов: <b>{total_configs}</b>\n"
    "🔐 OpenVPN online: <b>{connected_openvpn}</b>\n"
    "🛡️ WireGuard online: <b>{connected_wireguard}</b>\n"
    "🌐 IP сервера: <code>{server_ip}</code>\n\n"
    "🕐 <i>Обновлено: {timestamp}</i>"
)

# --- /configs ---

CONFIGS_LIST = "📁 <b>Конфигурации</b>\n\nСтр. {page}/{total_pages} · всего <b>{count}</b>\n\nВыберите клиента:"
CONFIGS_NONE = "📭 Конфигурации не найдены.\n\nСоздайте клиента в веб-панели или Mini App."

# --- /traffic ---

TRAFFIC_LIST = (
    "📊 <b>Мой трафик</b>\n\n"
    "Стр. {page}/{total_pages} · клиентов <b>{count}</b> · суммарно <b>{total}</b>\n\n"
    "{lines}"
)
TRAFFIC_NONE = "📭 У вас нет конфигураций для отображения трафика."
TRAFFIC_NO_STATS = "📊 Статистика трафика для ваших клиентов ещё не собрана."

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
    "Выберите маршрут:"
)
CONFIG_GROUP_NOT_FOUND = "Группа конфигов не найдена."
CONFIG_FILE_NOT_FOUND = "Файл конфигурации не найден."
BTN_CONFIG_BACK = "◀️ К протоколам"
BTN_CONFIG_PICK_ANOTHER = "📤 Ещё файл"

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
BK_RESTORE_WARN = "Текущие данные будут перезаписаны. Перезапустите панель после восстановления."
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
