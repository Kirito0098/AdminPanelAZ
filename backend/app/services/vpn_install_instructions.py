"""Platform-specific VPN profile install instructions for Telegram messages."""

from __future__ import annotations

from typing import Callable, Literal

InstallPlatform = Literal["ios", "mac", "windows", "android", "linux"]

PLATFORM_LABELS: dict[str, str] = {
    "ios": "iOS",
    "mac": "macOS",
    "windows": "Windows",
    "android": "Android",
    "linux": "Linux",
}

_PROTOCOL_ALIASES = {
    "openvpn": "openvpn",
    "ovpn": "openvpn",
    "wireguard": "wireguard",
    "wg": "wireguard",
    "amneziawg": "amneziawg",
    "awg": "amneziawg",
    "amneziawg2": "amneziawg2",
    "awg2": "amneziawg2",
    "awg 2.0": "amneziawg2",
}


def normalize_protocol(protocol: str) -> str:
    key = (protocol or "").strip().lower()
    return _PROTOCOL_ALIASES.get(key, key)


def _openvpn_ios(client_name: str) -> str:
    return (
        f"<b>📱 Установка OpenVPN на iOS</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите <b>OpenVPN Connect</b> из App Store.\n"
        "2. Откройте файл <code>.ovpn</code> из этого чата (нажмите на документ).\n"
        "3. Выберите «Открыть в OpenVPN» / «Import».\n"
        "4. Разрешите добавление VPN-конфигурации (Face ID / пароль).\n"
        "5. Включите переключатель рядом с профилем для подключения.\n\n"
        "Если импорт не сработал: «Поделиться» → OpenVPN Connect."
    )


def _openvpn_android(client_name: str) -> str:
    return (
        f"<b>📱 Установка OpenVPN на Android</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите <b>OpenVPN Connect</b> из Google Play.\n"
        "2. Нажмите на файл <code>.ovpn</code> в этом чате.\n"
        "3. Выберите OpenVPN Connect для открытия.\n"
        "4. Подтвердите импорт профиля.\n"
        "5. Нажмите «Подключить» (значок ON).\n\n"
        "При запросе разрешите VPN-подключение для приложения."
    )


def _openvpn_mac(client_name: str) -> str:
    return (
        f"<b>💻 Установка OpenVPN на macOS</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите <b>OpenVPN Connect</b> или <b>Tunnelblick</b>.\n"
        "2. Сохраните <code>.ovpn</code> из чата на Mac.\n"
        "3. OpenVPN Connect: File → Import Profile.\n"
        "   Tunnelblick: дважды кликните по файлу.\n"
        "4. Введите пароль macOS при запросе.\n"
        "5. Подключитесь через меню приложения."
    )


def _openvpn_windows(client_name: str) -> str:
    return (
        f"<b>🖥 Установка OpenVPN на Windows</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите <b>OpenVPN Connect</b> с openvpn.net.\n"
        "2. Сохраните <code>.ovpn</code> из чата на компьютер.\n"
        "3. В OpenVPN Connect: «+» → Import file → выберите файл.\n"
        "4. Подтвердите импорт (UAC при необходимости).\n"
        "5. Нажмите «Connect» напротив профиля."
    )


def _openvpn_linux(client_name: str) -> str:
    return (
        f"<b>🐧 Установка OpenVPN на Linux</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите OpenVPN: <code>sudo apt install openvpn</code> (Debian/Ubuntu).\n"
        "2. Сохраните <code>.ovpn</code> из чата, например в <code>~/vpn.ovpn</code>.\n"
        "3. Запуск: <code>sudo openvpn --config ~/vpn.ovpn</code>.\n"
        "4. Или импортируйте профиль в NetworkManager (GUI «Сеть» → VPN → Import).\n"
        "5. Для автозапуска настройте systemd-unit или NM «подключать автоматически»."
    )


def _wireguard_ios(client_name: str) -> str:
    return (
        f"<b>📱 Установка WireGuard на iOS</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите <b>WireGuard</b> из App Store.\n"
        "2. Откройте файл конфига из чата или отсканируйте QR (если есть).\n"
        "3. Нажмите «Добавить туннель» / «Import from file».\n"
        "4. Разрешите добавление VPN (Face ID / пароль).\n"
        "5. Включите туннель переключателем."
    )


def _wireguard_android(client_name: str) -> str:
    return (
        f"<b>📱 Установка WireGuard на Android</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите <b>WireGuard</b> из Google Play.\n"
        "2. «+» → «Сканировать QR» или «Импорт из файла».\n"
        "3. Выберите конфиг из загрузок / из Telegram.\n"
        "4. Сохраните туннель.\n"
        "5. Включите переключатель для подключения."
    )


def _wireguard_mac(client_name: str) -> str:
    return (
        f"<b>💻 Установка WireGuard на macOS</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите <b>WireGuard</b> из Mac App Store.\n"
        "2. «Import tunnel(s) from file» → выберите <code>.conf</code>.\n"
        "3. Разрешите VPN в настройках системы.\n"
        "4. Нажмите «Activate» напротив туннеля.\n"
        "5. Статус «Active» означает успешное подключение."
    )


def _wireguard_windows(client_name: str) -> str:
    return (
        f"<b>🖥 Установка WireGuard на Windows</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите <b>WireGuard</b> с wireguard.com.\n"
        "2. «Import tunnel(s) from file» → выберите <code>.conf</code>.\n"
        "3. Подтвердите установку службы (UAC).\n"
        "4. Нажмите «Activate».\n"
        "5. Иконка в трее покажет активный туннель."
    )


def _wireguard_linux(client_name: str) -> str:
    return (
        f"<b>🐧 Установка WireGuard на Linux</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите: <code>sudo apt install wireguard</code>.\n"
        "2. Сохраните <code>.conf</code> в <code>/etc/wireguard/wg0.conf</code> (нужен root).\n"
        "3. <code>sudo wg-quick up wg0</code> — подключить.\n"
        "4. <code>sudo wg-quick down wg0</code> — отключить.\n"
        "5. Или импортируйте в NetworkManager, если доступен плагин WireGuard."
    )


def _amnezia_ios(client_name: str) -> str:
    return (
        f"<b>📱 Установка AmneziaWG на iOS</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите <b>AmneziaWG</b> из App Store "
        "(в РФ обычно доступно; AmneziaVPN для <code>.conf</code> не обязателен).\n"
        "2. Импортируйте конфиг <code>.conf</code> из этого чата.\n"
        "3. Следуйте шагам мастера в приложении.\n"
        "4. Разрешите VPN-профиль в настройках iOS.\n"
        "5. Подключитесь к добавленному серверу."
    )


def _amnezia_android(client_name: str) -> str:
    return (
        f"<b>📱 Установка AmneziaWG на Android</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите <b>AmneziaWG</b> из Google Play / GitHub "
        "(достаточно для файла <code>.conf</code>).\n"
        "2. «Добавить конфигурацию» → импорт из файла.\n"
        "3. Выберите файл из Telegram / загрузок.\n"
        "4. Подтвердите VPN-разрешение.\n"
        "5. Подключитесь к профилю в приложении."
    )


def _amnezia_mac(client_name: str) -> str:
    return (
        f"<b>💻 Установка AmneziaWG на macOS</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите <b>AmneziaWG</b> "
        "(или клиент с поддержкой AmneziaWG с amnezia.org / GitHub).\n"
        "2. Импортируйте конфигурацию <code>.conf</code> из файла.\n"
        "3. Разрешите VPN в системных настройках.\n"
        "4. Выберите профиль и подключитесь.\n"
        "5. При ошибках проверьте, что файл не повреждён при скачивании."
    )


def _amnezia_windows(client_name: str) -> str:
    return (
        f"<b>🖥 Установка AmneziaWG на Windows</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите <b>AmneziaWG</b> для Windows "
        "(достаточно для файла <code>.conf</code>).\n"
        "2. Импортируйте конфиг из сохранённого файла.\n"
        "3. Подтвердите установку VPN-адаптера.\n"
        "4. Подключитесь через интерфейс AmneziaWG.\n"
        "5. Обычный WireGuard без AmneziaWG не подойдёт."
    )


def _amnezia_linux(client_name: str) -> str:
    return (
        f"<b>🐧 Установка AmneziaWG на Linux</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите <b>AmneziaWG</b> / <b>amneziawg-tools</b> "
        "(или userspace awg).\n"
        "2. Импортируйте <code>.conf</code> в AmneziaWG "
        "либо сохраните для awg-quick.\n"
        "3. Подключение: GUI AmneziaWG или "
        "<code>sudo awg-quick up …</code>.\n"
        "4. Обычный <code>wg-quick</code> без AmneziaWG может не подойти.\n"
        "5. Проверьте права на чтение конфига."
    )


def _awg2_ios(client_name: str) -> str:
    return (
        f"<b>📱 Установка AWG 2.0 на iOS</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите <b>AmneziaWG</b> из App Store "
        "(в РФ обычно доступно; для <code>.conf</code> этого достаточно).\n"
        "2. Откройте файл <code>.conf</code> из этого чата.\n"
        "3. Импортируйте профиль в AmneziaWG.\n"
        "4. Разрешите VPN в настройках iOS (Face ID / пароль).\n"
        "5. Подключитесь к добавленному серверу.\n\n"
        "Нужна свежая версия AmneziaWG с поддержкой протокола 2.0. "
        "Файл <code>.vpn</code> — только в AmneziaVPN."
    )


def _awg2_android(client_name: str) -> str:
    return (
        f"<b>📱 Установка AWG 2.0 на Android</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите <b>AmneziaWG</b> из Google Play / GitHub "
        "(для <code>.conf</code> этого достаточно).\n"
        "2. «Добавить конфигурацию» → импорт из файла.\n"
        "3. Выберите <code>.conf</code> из Telegram / загрузок.\n"
        "4. Подтвердите VPN-разрешение.\n"
        "5. Подключитесь к профилю.\n\n"
        "Нужна свежая версия AmneziaWG с поддержкой протокола 2.0. "
        "Файл <code>.vpn</code> — только в AmneziaVPN."
    )


def _awg2_mac(client_name: str) -> str:
    return (
        f"<b>💻 Установка AWG 2.0 на macOS</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите <b>AmneziaWG</b> "
        "(актуальная версия с поддержкой 2.0).\n"
        "2. Импортируйте <code>.conf</code> из файла в чате.\n"
        "3. Разрешите VPN в системных настройках.\n"
        "4. Выберите профиль и подключитесь.\n"
        "5. Файл <code>.vpn</code> открывайте в AmneziaVPN; "
        "для <code>.conf</code> AmneziaVPN не обязателен."
    )


def _awg2_windows(client_name: str) -> str:
    return (
        f"<b>🖥 Установка AWG 2.0 на Windows</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите <b>AmneziaWG</b> для Windows "
        "(актуальная версия с поддержкой 2.0).\n"
        "2. Сохраните <code>.conf</code> из чата и импортируйте в AmneziaWG.\n"
        "3. Подтвердите установку VPN-адаптера (UAC).\n"
        "4. Подключитесь через интерфейс AmneziaWG.\n"
        "5. Не используйте обычный WireGuard. "
        "Файл <code>.vpn</code> — только в AmneziaVPN."
    )


def _awg2_linux(client_name: str) -> str:
    return (
        f"<b>🐧 Установка AWG 2.0 на Linux</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите <b>AmneziaWG</b> / <b>amneziawg-tools</b> + userspace "
        "(для <code>.conf</code> этого достаточно).\n"
        "2. Файл <code>.conf</code> — AmneziaWG или "
        "<code>sudo awg-quick up …</code>.\n"
        "3. Файл <code>.vpn</code> — импорт в <b>AmneziaVPN</b>.\n"
        "4. Подключитесь через GUI AmneziaWG или awg-quick.\n"
        "5. Обычный <code>wg-quick</code> без AmneziaWG 2.0 не подойдёт."
    )


def _detect_profile_format(filename: str | None, path: str | None) -> str:
    name = (filename or path or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    if name.endswith(".vpn") or "vpnuri" in name:
        return "vpn"
    if name.endswith(".conf"):
        return "conf"
    return "unknown"


def _awg_vpn_file_instruction(
    *,
    platform: InstallPlatform,
    client_name: str,
    is_awg2: bool,
) -> str:
    """Instructions when the delivered file is AmneziaVPN .vpn / vpnuri."""
    label = "AWG 2.0" if is_awg2 else "AmneziaWG"
    heads = {
        "ios": f"<b>📱 Установка {label} на iOS</b>",
        "android": f"<b>📱 Установка {label} на Android</b>",
        "mac": f"<b>💻 Установка {label} на macOS</b>",
        "windows": f"<b>🖥 Установка {label} на Windows</b>",
        "linux": f"<b>🐧 Установка {label} на Linux</b>",
    }
    stores = {
        "ios": "из App Store / сайта amnezia.org",
        "android": "из Google Play / GitHub / amnezia.org",
        "mac": "с amnezia.org",
        "windows": "для Windows с amnezia.org",
        "linux": "(AppImage / пакет с amnezia.org)",
    }
    return (
        f"{heads[platform]}\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        f"1. Установите <b>AmneziaVPN</b> {stores[platform]}.\n"
        "2. Этот файл — формат <code>.vpn</code> (часто <code>vpn://…</code>), "
        "его принимает <b>AmneziaVPN</b>, не AmneziaWG.\n"
        "3. Импортируйте файл из чата в AmneziaVPN.\n"
        "4. Разрешите VPN-подключение в системе.\n"
        "5. Подключитесь к добавленному серверу.\n\n"
        "Если есть файл <code>.conf</code> — его можно открыть в <b>AmneziaWG</b> без AmneziaVPN."
    )


def _profile_format_tip(*, protocol: str, filename: str | None, path: str | None) -> str | None:
    """Hint which app matches .conf vs .vpn (mainly AWG / AWG 2.0)."""
    if protocol not in {"amneziawg2", "amneziawg"}:
        return None
    fmt = _detect_profile_format(filename, path)
    if fmt == "vpn":
        return (
            "📎 Этот файл — формат <b>.vpn</b>.\n"
            "Его нужно открыть в <b>AmneziaVPN</b> "
            "(AmneziaWG принимает нативный <code>.conf</code>)."
        )
    if fmt == "conf":
        return (
            "📎 Этот файл — нативный <b>.conf</b>.\n"
            "Достаточно приложения <b>AmneziaWG</b> (или awg-quick). "
            "AmneziaVPN не обязателен. Обычный WireGuard не подойдёт."
        )
    if protocol == "amneziawg2":
        return (
            "📎 AWG 2.0: <b>.conf</b> — AmneziaWG / awg-quick; "
            "<b>.vpn</b> — только AmneziaVPN."
        )
    return (
        "📎 <b>.conf</b> — AmneziaWG / awg-quick; "
        "<b>.vpn</b> — только AmneziaVPN."
    )


_BUILDERS: dict[tuple[str, str], Callable[[str], str]] = {
    ("openvpn", "ios"): _openvpn_ios,
    ("openvpn", "android"): _openvpn_android,
    ("openvpn", "mac"): _openvpn_mac,
    ("openvpn", "windows"): _openvpn_windows,
    ("openvpn", "linux"): _openvpn_linux,
    ("wireguard", "ios"): _wireguard_ios,
    ("wireguard", "android"): _wireguard_android,
    ("wireguard", "mac"): _wireguard_mac,
    ("wireguard", "windows"): _wireguard_windows,
    ("wireguard", "linux"): _wireguard_linux,
    ("amneziawg", "ios"): _amnezia_ios,
    ("amneziawg", "android"): _amnezia_android,
    ("amneziawg", "mac"): _amnezia_mac,
    ("amneziawg", "windows"): _amnezia_windows,
    ("amneziawg", "linux"): _amnezia_linux,
    ("amneziawg2", "ios"): _awg2_ios,
    ("amneziawg2", "android"): _awg2_android,
    ("amneziawg2", "mac"): _awg2_mac,
    ("amneziawg2", "windows"): _awg2_windows,
    ("amneziawg2", "linux"): _awg2_linux,
}


def build_install_instruction_message(
    *,
    protocol: str,
    platform: InstallPlatform,
    client_name: str,
    filename: str | None = None,
    path: str | None = None,
) -> str | None:
    proto = normalize_protocol(protocol)
    fmt = _detect_profile_format(filename, path)

    if proto in {"amneziawg", "amneziawg2"} and fmt == "vpn":
        message = _awg_vpn_file_instruction(
            platform=platform,
            client_name=client_name,
            is_awg2=proto == "amneziawg2",
        )
        tip = _profile_format_tip(protocol=proto, filename=filename, path=path)
        return f"{message}\n\n{tip}" if tip else message

    builder = _BUILDERS.get((proto, platform))
    if not builder:
        return None
    message = builder(client_name)
    tip = _profile_format_tip(protocol=proto, filename=filename, path=path)
    if tip:
        return f"{message}\n\n{tip}"
    return message
