"""DNS resolver choice for the AntiZapret Knot Resolver (`/etc/knot-resolver/kresd.conf`).

AntiZapret keeps the choice in two lines of ``kresd.conf``:

    local antizapret_dns = 1 -- AntiZapret VPN DNS
    local vpn_dns = 2 -- Full VPN DNS

``setup.sh`` rewrites them with ``sed`` while installing and nothing re-applies
``ANTIZAPRET_DNS`` / ``VPN_DNS`` from ``setup`` at runtime (``up.sh`` reads only ``VPN_DNS``
for the DNAT/DoT rules). The panel therefore patches the same two lines and restarts
the resolvers instead of writing setup keys that nothing would pick up.
"""

from __future__ import annotations

import re

from fastapi import HTTPException, status

# Labels follow setup.sh prompts so the panel and the installer describe the same choice.
# Fallback for kresd.conf without the ``upstream()`` function (very old AntiZapret-VPN).
ANTIZAPRET_DNS_OPTIONS: tuple[tuple[str, str], ...] = (
    ("1", "MSK-IX + NSDI + BI.ZONE + TransTeleCom (по умолчанию, для РФ)"),
    ("2", "Cloudflare + Quad9 + ControlD + UltraDNS"),
    ("3", "Яндекс (EDNS Client Subnet)"),
    ("4", "Google (EDNS Client Subnet)"),
    ("5", "AdGuard (блокировка рекламы и фишинга)"),
    ("6", "Comss (доп. проксирование)"),
    ("7", "GeoHide (доп. проксирование)"),
)
VPN_DNS_OPTIONS: tuple[tuple[str, str], ...] = (
    ("1", "Как у AntiZapret (self-hosted)"),
    ("2", "Cloudflare/Quad9 — разрешает свой DNS в vpn-*"),
)
DEFAULT_VPN_DNS = 2

# AntiZapret-VPN 09.11.2026 убрал Comss и сдвинул GeoHide с 7 на 6. Число вариантов
# читаем из установленного kresd.conf: иначе панель либо запишет 7 в новую базу
# (kresd падает в panic('Invalid dns value')), либо спрячет GeoHide на старой.
_DNS_LABELS: dict[str, str] = {
    "russia_dns": "MSK-IX + NSDI + BI.ZONE + TransTeleCom (по умолчанию, для РФ)",
    "world_dns": "Cloudflare + Quad9 + ControlD + UltraDNS",
    "yandex_dns": "Яндекс (EDNS Client Subnet)",
    "google_dns": "Google (EDNS Client Subnet)",
    "adguard_dns": "AdGuard (блокировка рекламы и фишинга)",
    "comss_dns": "Comss (доп. проксирование)",
    "geohide_dns": "GeoHide (доп. проксирование)",
}
_DNS_BRANCH = re.compile(r"dns\s*==\s*(\d+)\s+then\s*\n?\s*return\s+([A-Za-z_][\w.]*)")

_ANTIZAPRET_LINE = re.compile(r"^(local\s+antizapret_dns\s*=\s*)(\d+)([^\n]*)$", re.MULTILINE)
_VPN_LINE = re.compile(r"^(local\s+vpn_dns\s*=\s*)(\d+)([^\n]*)$", re.MULTILINE)


def antizapret_dns_options(content: str | None) -> tuple[tuple[str, str], ...]:
    """Options that the installed ``kresd.conf`` really understands.

    The ``upstream()`` function maps the numbers to resolver sets; parsing it keeps the panel
    in sync with the base instead of hardcoding the menu of one AntiZapret-VPN release.
    """
    branches = {
        int(number): resolver
        for number, resolver in _DNS_BRANCH.findall(content or "")
    }
    if not branches:
        return ANTIZAPRET_DNS_OPTIONS
    return tuple(
        (str(number), _DNS_LABELS.get(resolver, resolver))
        for number, resolver in sorted(branches.items())
    )


def allowed_antizapret_dns(content: str | None) -> tuple[int, ...]:
    return tuple(int(value) for value, _label in antizapret_dns_options(content))


def allowed_dns_hint(values: tuple[int, ...]) -> str:
    if values == tuple(range(1, len(values) + 1)):
        return f"1–{len(values)}"
    return ", ".join(str(value) for value in values)


class KresdDnsChoiceError(ValueError):
    """kresd.conf has no DNS choice lines (AntiZapret too old) or the value is out of range."""


class DnsServersUnsupportedError(HTTPException):
    """The node agent on the node predates /configs/dns-servers."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Обновите node agent панели на узле — выбор DNS-серверов поддерживается с node agent 1.15.0",
        )


def read_dns_choice(content: str) -> tuple[int, int] | None:
    """Return (antizapret_dns, vpn_dns) as written in kresd.conf; None when the lines are absent."""
    antizapret = _ANTIZAPRET_LINE.search(content)
    vpn = _VPN_LINE.search(content)
    if antizapret is None or vpn is None:
        return None
    return int(antizapret.group(2)), int(vpn.group(2))


def effective_vpn_dns(antizapret: int, vpn: int) -> int:
    """Replicate setup.sh: VPN_DNS=1 puts the AntiZapret resolver into full VPN as well.

    setup.sh skips the sed when ANTIZAPRET_DNS=1, because kresd.conf already defaults
    vpn_dns to 2 (Cloudflare/Quad9) — keep that behaviour byte-for-byte.
    """
    if vpn == 1 and antizapret != 1:
        return antizapret
    return DEFAULT_VPN_DNS


def with_dns_choice(content: str, *, antizapret: int, vpn: int) -> str:
    """Patch the two ``local ..._dns`` lines, leaving every other line exactly as it was."""
    allowed = allowed_antizapret_dns(content)
    if antizapret not in allowed:
        raise KresdDnsChoiceError(f"ANTIZAPRET_DNS: допустимо {allowed_dns_hint(allowed)}")
    if vpn not in (1, 2):
        raise KresdDnsChoiceError("VPN_DNS: допустимо 1–2")
    if read_dns_choice(content) is None:
        raise KresdDnsChoiceError(
            "в kresd.conf нет строк local antizapret_dns / local vpn_dns — обновите AntiZapret-VPN на узле"
        )
    vpn_value = effective_vpn_dns(antizapret, vpn)
    updated = _ANTIZAPRET_LINE.sub(lambda m: f"{m.group(1)}{antizapret}{m.group(3)}", content, count=1)
    return _VPN_LINE.sub(lambda m: f"{m.group(1)}{vpn_value}{m.group(3)}", updated, count=1)


def choice_to_setup(antizapret: int, vpn: int) -> dict[str, str]:
    """Setup keys so a later setup.sh run keeps the same choice."""
    return {"ANTIZAPRET_DNS": str(antizapret), "VPN_DNS": str(vpn)}


_SETUP_KEY_LINE = re.compile(r"^(ANTIZAPRET_DNS|VPN_DNS)=.*$", re.MULTILINE)


def with_setup_dns_keys(content: str, *, antizapret: int, vpn: int) -> str:
    """Rewrite ANTIZAPRET_DNS / VPN_DNS in the setup file and append the ones that are missing."""
    wanted = choice_to_setup(antizapret, vpn)
    present = {key for key in wanted if re.search(rf"^{key}=", content, re.MULTILINE)}
    updated = _SETUP_KEY_LINE.sub(lambda m: f"{m.group(1)}={wanted[m.group(1)]}", content) if present else content
    missing = [key for key in ("ANTIZAPRET_DNS", "VPN_DNS") if key not in present]
    if missing:
        base = "" if not updated else updated if updated.endswith("\n") else updated + "\n"
        updated = base + "".join(f"{key}={wanted[key]}\n" for key in missing)
    return updated


def vpn_option_for_choice(antizapret: int, vpn_dns_in_file: int) -> int:
    """Which VPN_DNS option the file's vpn_dns value corresponds to."""
    if vpn_dns_in_file == DEFAULT_VPN_DNS:
        return 2
    if vpn_dns_in_file == antizapret:
        return 1
    return 2
