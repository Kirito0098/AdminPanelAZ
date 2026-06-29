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
        "1. Установите <b>AmneziaVPN</b> из App Store.\n"
        "2. Импортируйте конфиг из файла (полученного из чата).\n"
        "3. Следуйте шагам мастера в приложении.\n"
        "4. Разрешите VPN-профиль в настройках iOS.\n"
        "5. Подключитесь к добавленному серверу."
    )


def _amnezia_android(client_name: str) -> str:
    return (
        f"<b>📱 Установка AmneziaWG на Android</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите <b>AmneziaVPN</b> из Google Play.\n"
        "2. «Добавить конфигурацию» → импорт из файла.\n"
        "3. Выберите файл из Telegram / загрузок.\n"
        "4. Подтвердите VPN-разрешение.\n"
        "5. Подключитесь к профилю в приложении."
    )


def _amnezia_mac(client_name: str) -> str:
    return (
        f"<b>💻 Установка AmneziaWG на macOS</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите <b>AmneziaVPN</b> с сайта amnezia.org.\n"
        "2. Импортируйте конфигурацию из файла.\n"
        "3. Разрешите VPN в системных настройках.\n"
        "4. Выберите профиль и подключитесь.\n"
        "5. При ошибках проверьте, что файл не повреждён при скачивании."
    )


def _amnezia_windows(client_name: str) -> str:
    return (
        f"<b>🖥 Установка AmneziaWG на Windows</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите <b>AmneziaVPN</b> для Windows.\n"
        "2. Импортируйте конфиг из сохранённого файла.\n"
        "3. Подтвердите установку VPN-адаптера.\n"
        "4. Подключитесь через интерфейс Amnezia.\n"
        "5. Для AmneziaWG используйте только официальное приложение Amnezia."
    )


def _amnezia_linux(client_name: str) -> str:
    return (
        f"<b>🐧 Установка AmneziaWG на Linux</b>\n"
        f"Профиль: <code>{client_name}</code>\n\n"
        "1. Установите <b>AmneziaVPN</b> (AppImage / пакет с amnezia.org).\n"
        "2. Импортируйте конфиг из файла.\n"
        "3. Либо используйте awg/wg-quick, если профиль совместим с WireGuard.\n"
        "4. Подключение: через GUI Amnezia или <code>sudo wg-quick up …</code>.\n"
        "5. Проверьте права на чтение конфига."
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
}


def build_install_instruction_message(
    *,
    protocol: str,
    platform: InstallPlatform,
    client_name: str,
) -> str | None:
    proto = normalize_protocol(protocol)
    builder = _BUILDERS.get((proto, platform))
    if not builder:
        return None
    return builder(client_name)
