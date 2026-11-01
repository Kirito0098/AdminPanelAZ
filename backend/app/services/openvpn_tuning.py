"""OpenVPN server tuning that setup.sh applies with sed: ``duplicate-cn`` and detailed logs.

AntiZapret stores both switches as commented lines in ``/etc/openvpn/server/*.conf``
(``#verb 4``, ``#log-append …``, ``#status …``, ``#duplicate-cn``), so the panel toggles
exactly those lines and restarts the enabled units instead of rewriting the whole file.
"""

from __future__ import annotations

import re

from fastapi import HTTPException, status

_DUPLICATE = re.compile(r"^[#;]?[^\S\n]*duplicate-cn[^\S\n]*$", re.MULTILINE)
_LOG_LINES = re.compile(
    r"^([#;]?)[^\S\n]*(verb[^\S\n]+\d+|log-append[^\S\n]+\S+|status[^\S\n]+\S+([^\S\n]+\d+)?)[^\S\n]*$",
    re.MULTILINE,
)
_TUN_MTU = re.compile(r"^tun-mtu[^\S\n]+(\d+)[^\S\n]*$", re.MULTILINE)
_WG_MTU = re.compile(r"^MTU[^\S\n]*=[^\S\n]*(\d+)[^\S\n]*$", re.MULTILINE)
_DISABLE_DCO = re.compile(r"^disable-dco[^\S\n]*$", re.MULTILINE)
_DATA_CIPHERS = re.compile(r'^data-ciphers\s+"([^"]*)"', re.MULTILINE)
_DATA_CIPHERS_LINE = re.compile(r"^data-ciphers[^\n]*\n?", re.MULTILINE)

MTU_MIN = 1280
MTU_MAX = 1420
DCO_CIPHERS = "AES-128-GCM:AES-256-GCM:CHACHA20-POLY1305"
DCO_CIPHERS_WITH_CBC = f"{DCO_CIPHERS}:AES-128-CBC:AES-192-CBC:AES-256-CBC"


class OpenVpnTuningError(ValueError):
    """The server config has no line to toggle (hand-edited or unknown OpenVPN layout)."""


class OpenVpnTuningUnsupportedError(HTTPException):
    """The node agent on the node predates /openvpn/tuning."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Обновите node agent панели на узле — настройки OpenVPN поддерживаются с node agent 1.16.0",
        )


def duplicate_cn_enabled(content: str) -> bool | None:
    """None — строки нет вовсе (ручной конфиг)."""
    match = _DUPLICATE.search(content)
    if match is None:
        return None
    return not match.group(0).lstrip().startswith(("#", ";"))


def logs_enabled(content: str) -> bool | None:
    """Подробные логи включены, когда раскомментированы verb/log-append/status."""
    matches = _LOG_LINES.findall(content)
    if not matches:
        return None
    return all(not marker for marker, _line, *_rest in matches)


def tun_mtu(content: str) -> int | None:
    match = _TUN_MTU.search(content)
    return int(match.group(1)) if match else None


def wireguard_mtu(content: str) -> int | None:
    match = _WG_MTU.search(content)
    return int(match.group(1)) if match else None


def dco_mode(content: str) -> str:
    """'off' — есть disable-dco; 'on' — AEAD-only data-ciphers без disable-dco; иначе 'unknown'."""
    if _DISABLE_DCO.search(content):
        return "off"
    ciphers = _DATA_CIPHERS.search(content)
    if ciphers is None:
        return "unknown"
    names = {item.strip().upper() for item in ciphers.group(1).split(":") if item.strip()}
    return "on" if names and not any(name.endswith("-CBC") for name in names) else "off"


def with_duplicate_cn(content: str, enabled: bool) -> str:
    """Включить/выключить duplicate-cn, остальные строки не меняются."""
    if _DUPLICATE.search(content) is None:
        raise OpenVpnTuningError("в конфиге нет строки duplicate-cn — поправьте файл вручную")
    return _DUPLICATE.sub("duplicate-cn" if enabled else "#duplicate-cn", content, count=1)


def with_logs(content: str, enabled: bool) -> str:
    """Раскомментировать/закомментировать verb, log-append и status."""
    if _LOG_LINES.search(content) is None:
        raise OpenVpnTuningError("в конфиге нет строк verb/log-append/status — поправьте файл вручную")

    def _replace(match: re.Match[str]) -> str:
        marker, line = match.group(1), match.group(2)
        return line if enabled else f"#{line}"

    return _LOG_LINES.sub(_replace, content)


def validate_mtu(mtu: int) -> int:
    if not MTU_MIN <= int(mtu) <= MTU_MAX:
        raise OpenVpnTuningError(f"MTU: допустимо {MTU_MIN}–{MTU_MAX}")
    return int(mtu)


def with_tun_mtu(content: str, mtu: int) -> str:
    """Как setup.sh: заменить `tun-mtu` в server conf, остальной файл не трогать."""
    value = validate_mtu(mtu)
    if _TUN_MTU.search(content) is None:
        raise OpenVpnTuningError("в конфиге нет строки tun-mtu — поправьте файл вручную")
    return _TUN_MTU.sub(f"tun-mtu {value}", content, count=1)


def with_wireguard_mtu(content: str, mtu: int) -> str:
    """Как setup.sh: заменить `MTU =` в шаблоне WireGuard."""
    value = validate_mtu(mtu)
    if _WG_MTU.search(content) is None:
        raise OpenVpnTuningError("в шаблоне WireGuard нет строки MTU — поправьте файл вручную")
    return _WG_MTU.sub(f"MTU = {value}", content, count=1)


def with_dco(content: str, enabled: bool) -> str:
    """Повторяет openvpn-dco.sh: убрать прежние data-ciphers/disable-dco и дописать нужный набор."""
    cleaned = _DISABLE_DCO.sub("", _DATA_CIPHERS_LINE.sub("", content)).rstrip("\n")
    if enabled:
        return f'{cleaned}\ndata-ciphers "{DCO_CIPHERS}"\n'
    return f'{cleaned}\ndata-ciphers "{DCO_CIPHERS_WITH_CBC}"\ndisable-dco\n'
