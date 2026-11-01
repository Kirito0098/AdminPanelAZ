"""AntiZapret setup parameters schema (ported from AdminAntizapret 1.9.0)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

ANTIZAPRET_PARAMS = [
    {
        "key": "route_all",
        "env": "ROUTE_ALL",
        "type": "flag",
        "default": "n",
        "html_id": "route-all-toggle",
        "title": "Всех доменов, кроме .ru",
        "description": "Перенаправляет весь трафик через antizapret, кроме российских доменов (.ru, .рф) и исключений из exclude-hosts.txt",
    },
    {
        "key": "discord_include",
        "env": "DISCORD_INCLUDE",
        "type": "flag",
        "default": "n",
        "html_id": "discord-toggle",
        "title": "Discord",
        "description": "Перенаправляет трафик Discord через antizapret, включая голосовые каналы и обмен сообщениями",
    },
    {
        "key": "cloudflare_include",
        "env": "CLOUDFLARE_INCLUDE",
        "type": "flag",
        "default": "n",
        "html_id": "cloudflare-toggle",
        "title": "Cloudflare",
        "description": "Перенаправляет трафик Cloudflare через antizapret, включая сайты и сервисы, использующие Cloudflare для защиты от DDoS-атак",
    },
    {
        "key": "telegram_include",
        "env": "TELEGRAM_INCLUDE",
        "type": "flag",
        "default": "n",
        "html_id": "telegram-toggle",
        "title": "Telegram",
        "description": "Перенаправляет трафик Telegram через Antizapret, включая обмен сообщениями, каналы и группы",
    },
    {
        "key": "ANTIZAPRET_ADBLOCK",
        "env": "ANTIZAPRET_ADBLOCK",
        "type": "flag",
        "default": "n",
        "html_id": "ANTIZAPRET_ADBLOCK-toggle",
        "title": "AdBlock for Antizapret",
        "description": "Блокировка рекламы, трекеров, вредоносных программ и фишинговых веб-сайтов в AntiZapret VPN (antizapret-*) на основе правил AdGuard и OISD",
    },
    {
        "key": "VPN_ADBLOCK",
        "env": "VPN_ADBLOCK",
        "type": "flag",
        "default": "n",
        "html_id": "VPN_ADBLOCK-toggle",
        "title": "AdBlock for VPN",
        "description": "Блокировка рекламы, трекеров, вредоносных программ и фишинговых веб-сайтов в полном VPN (vpn-*) на основе правил AdGuard и OISD",
    },
    {
        "key": "whatsapp_include",
        "env": "WHATSAPP_INCLUDE",
        "type": "flag",
        "default": "n",
        "html_id": "whatsapp-toggle",
        "title": "WhatsApp",
        "description": "Перенаправляет трафик WhatsApp через Antizapret, включая обмен сообщениями, звонки и медиафайлы.",
    },
    {
        "key": "roblox_include",
        "env": "ROBLOX_INCLUDE",
        "type": "flag",
        "default": "n",
        "html_id": "roblox-toggle",
        "title": "Roblox",
        "description": "Перенаправляет трафик Roblox через Antizapret, включая игровой контент, платежи и социальные функции.",
    },
    {
        "key": "OPENVPN_BACKUP_TCP",
        "env": "OPENVPN_BACKUP_TCP",
        "type": "flag",
        "default": "n",
        "html_id": "OPENVPN_BACKUP_TCP-toggle",
        "title": "TCP",
        "description": "Включает резервные порты OpenVPN TCP (80,443,504,508) для обхода блокировок провайдеров, если стандартный порт заблокирован.",
    },
    {
        "key": "OPENVPN_BACKUP_UDP",
        "env": "OPENVPN_BACKUP_UDP",
        "type": "flag",
        "default": "n",
        "html_id": "OPENVPN_BACKUP_UDP-toggle",
        "title": "UDP",
        "description": "Включает резервные порты OpenVPN UDP (80,443,504,508) для обхода блокировок провайдеров, если стандартный порт заблокирован.",
    },
    {
        "key": "WIREGUARD_BACKUP",
        "env": "WIREGUARD_BACKUP",
        "param_label": "WIREGUARD_BACKUP_TCP",
        "type": "flag",
        "default": "n",
        "html_id": "WIREGUARD_540_580-toggle",
        "title": "WireGuard/AmneziaWG",
        "description": "Включает резервные порты WireGuard/AmneziaWG (540,580) для обхода блокировок провайдеров, если стандартный порт заблокирован.",
    },
    {
        "key": "ANTIZAPRET_WARP",
        "env": "ANTIZAPRET_WARP",
        "type": "choice",
        "default": "1",
        "html_id": "ANTIZAPRET_WARP-select",
        "title": "Cloudflare WARP for Antizapret",
        "description": "Исходящий трафик AntiZapret VPN (antizapret-*) через встроенный Cloudflare WARP AntiZapret. Список WARP — ваш config/include-warp-hosts.txt (Редактор файлов → WARP) плюс STUN/TURN-серверы из списка AntiZapret; исключения — exclude-warp-hosts.txt",
        "options": [
            {"value": "1", "label": "None — не использовать"},
            {"value": "2", "label": "All — весь трафик (домены и IP)"},
            {"value": "3", "label": "Domain — домены AntiZapret и списка WARP"},
            {"value": "4", "label": "Custom — только домены списка WARP"},
        ],
        # Старый AntiZapret-VPN: y/n. Режимы 3/4 в y/n не выражаются.
        "legacy_flag": {"y": "2", "n": "1"},
    },
    {
        "key": "VPN_WARP",
        "env": "VPN_WARP",
        "type": "choice",
        "default": "1",
        "html_id": "VPN_WARP-select",
        "title": "Cloudflare WARP for VPN outbound",
        "description": "Исходящий трафик полного VPN (vpn-*) через встроенный Cloudflare WARP AntiZapret. Режим Custom — только домены из config/include-warp-hosts.txt (минус exclude-warp-hosts.txt); нужен AntiZapret-VPN с 26.10.2026",
        "options": [
            {"value": "1", "label": "None — не использовать"},
            {"value": "2", "label": "All — весь трафик (домены и IP)"},
            {"value": "3", "label": "Custom — только домены списка WARP"},
        ],
        # Старый AntiZapret-VPN: y/n. Режим 3 в y/n не выражается — панель откажет с просьбой обновить AntiZapret.
        "legacy_flag": {"y": "2", "n": "1"},
    },
    {
        "key": "WARP_PROTECTION",
        "env": "WARP_PROTECTION",
        "type": "flag",
        "default": "n",
        "html_id": "WARP_PROTECTION-toggle",
        "title": "WARP protection",
        "description": "Блокировать трафик AntiZapret VPN и полного VPN, если встроенный WARP не подключился (иначе — выход напрямую)",
    },
    {
        "key": "WARP_MTU",
        "env": "WARP_MTU",
        "type": "number",
        "default": "",
        # AntiZapret up.sh uses ${WARP_MTU:-1280}: an empty value means 1280.
        "placeholder": "1280",
        "min": 576,
        "max": 1500,
        "html_id": "WARP_MTU-input",
        "title": "MTU WARP",
        "description": "MTU интерфейсов встроенного WARP. Пусто — 1280. Уменьшайте, если через WARP не открываются часть сайтов или обрываются загрузки",
    },
    {
        "key": "DNS_WARP",
        "env": "DNS_WARP",
        "type": "flag",
        "default": "n",
        # AntiZapret до 26.10.2026 хранил этот флаг как 1/2 — такие значения панель не перезаписывает.
        "legacy_numeric_flag": {"1": "n", "2": "y"},
        # Числовые ANTIZAPRET_WARP / VPN_WARP есть только в новом setup: иначе y/n никто не прочитает.
        "numeric_markers": ("ANTIZAPRET_WARP", "VPN_WARP"),
        "html_id": "DNS_WARP-toggle",
        "title": "DNS через Cloudflare WARP",
        "description": "Весь исходящий DNS уходит через встроенный WARP — включите, если выбранные DNS-серверы заблокированы или недоступны с этого сервера. Нужен AntiZapret-VPN с 26.10.2026: на старом setup (DNS_WARP=1|2) панель значение не меняет",
    },
    {
        "key": "ssh_protection",
        "env": "SSH_PROTECTION",
        "type": "flag",
        "default": "n",
        "html_id": "ssh_protection-toggle",
        "title": "Защита от брутфорса SSH",
        "description": "Включить защиту от перебора паролей SSH (не более 3 новых подключений в час с одного IP)",
    },
    {
        "key": "attack_protection",
        "env": "ATTACK_PROTECTION",
        "type": "flag",
        "default": "n",
        "html_id": "attack_protection-toggle",
        "title": "Защита от атак",
        "description": "Блокирует подозрительную сетевую активность: превышение лимита подключений и попытки подключения по нетипичным портам.",
    },
    {
        "key": "scan_protection",
        "env": "SCAN_PROTECTION",
        "type": "flag",
        "default": "n",
        "html_id": "scan_protection-toggle",
        "title": "Scan protection",
        "description": "Скрывает сервер от простого сканирования: отключает ответ на ping и на запросы к закрытым портам.",
    },
    {
        "key": "torrent_guard",
        "env": "TORRENT_GUARD",
        "type": "flag",
        "default": "n",
        "html_id": "torrent_guard-toggle",
        "title": "Torrent Guard",
        "description": "Torrent Guard — если хостер запрещает торренты или присылает жалобы, эта опция поможет: при обнаружении торрент-трафика VPN будет блокироваться на 1 минуту",
    },
    {
        "key": "restrict_forward",
        "env": "RESTRICT_FORWARD",
        "param_label": "restrict_forward",
        "type": "flag",
        "default": "n",
        "html_id": "restrict_forward-toggle",
        "title": "Ограничение форвардинга",
        "description": "Трафик клиентов AntiZapret VPN только к адресам из config/forward-ips.txt и result/route-ips.txt: остальное блокируется. Сами списки AntiZapret применяет всегда — флаг включает запрет на остальные адреса",
    },
    {
        "key": "client_isolation",
        "env": "CLIENT_ISOLATION",
        "type": "flag",
        "default": "y",
        "html_id": "client_isolation-toggle",
        "title": "Изоляция клиентов и сервера",
        "description": "Блокирует входящие соединения с клиентских адресов на сервер и к другим клиентам, кроме DNS (порт 53). С 31.10.2026 AntiZapret больше не блокирует форвардинг между клиентами",
    },
    {
        "key": "clear_hosts",
        "env": "CLEAR_HOSTS",
        "type": "flag",
        "default": "n",
        "html_id": "clear-hosts-toggle",
        "title": "Очистка хостов: казино, VPN и прокси",
        "description": "При авто-обновлении списков удаляет домены казино и букмекеров, а также все домены со словами vpn и proxy — в том числе из вашего include-hosts.txt. Сокращает список и нагрузку.",
    },
    {"key": "openvpn_host", "env": "OPENVPN_HOST", "type": "string", "default": "", "html_id": "openvpn-host-input"},
    {"key": "wireguard_host", "env": "WIREGUARD_HOST", "type": "string", "default": "", "html_id": "wireguard-host-input"},
]

KNOWN_SETTING_KEYS = frozenset(p["key"] for p in ANTIZAPRET_PARAMS)

# up.sh читает эти ключи при старте службы antizapret: запись в setup без
# `systemctl restart antizapret` не меняет ни iptables, ни WARP-интерфейсы.
RUNTIME_RESTART_KEYS: frozenset[str] = frozenset(
    {
        "ssh_protection",
        "attack_protection",
        "scan_protection",
        "torrent_guard",
        "restrict_forward",
        "client_isolation",
        "ANTIZAPRET_WARP",
        "VPN_WARP",
        "WARP_PROTECTION",
        "WARP_MTU",
        "DNS_WARP",
        "OPENVPN_BACKUP_TCP",
        "OPENVPN_BACKUP_UDP",
        "WIREGUARD_BACKUP",
    }
)


def needs_antizapret_restart(updates: Mapping[str, Any]) -> bool:
    """Whether the saved setup keys only take effect after restarting the antizapret unit."""
    return bool(RUNTIME_RESTART_KEYS.intersection(updates))

# Setup keys excluded from HA auto-replication (node-local only).
# ANTIZAPRET_WARP / VPN_WARP are built-in AntiZapret Cloudflare WARP flags (not AZ-WARP /
# Warper) and must replicate with the rest of setup so both nodes route the same way.
ANTIZAPRET_HA_SETTING_EXCLUDE: frozenset[str] = frozenset()


def filter_ha_replicable_settings(updates: dict[str, Any]) -> dict[str, Any]:
    """Drop node-local setup keys; keep shared AntiZapret config including WARP flags."""
    return {key: value for key, value in updates.items() if key not in ANTIZAPRET_HA_SETTING_EXCLUDE}
