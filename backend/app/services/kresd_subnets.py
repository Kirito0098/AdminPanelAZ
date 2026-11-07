"""Подсети клиентов AntiZapret: kresd.conf, proxy.py и services.env AZ-AWG2.

``ALTERNATIVE_CLIENT_IP`` / ``ALTERNATIVE_FAKE_IP`` читают только ``up.sh`` / ``parse.sh`` /
``down.sh`` (правила iptables и профили клиентов). ``kresd.conf`` (view:addr по подсетям
клиентов) генерирует ``setup.sh``, а ``proxy.py`` держит ``--fake-cidr`` в своём default.
Одна запись в ``setup`` их не меняет, поэтому панель правит файлы сама — иначе клиенты
получат новые адреса, а резолвер и fake-IP останутся на старых.
"""

from __future__ import annotations

import re

CLIENT_PREFIX_ALTERNATIVE = "172"  # ALTERNATIVE_CLIENT_IP=y
CLIENT_PREFIX_DEFAULT = "10"  # ALTERNATIVE_CLIENT_IP=n
FAKE_PREFIX_ALTERNATIVE = "198.18"  # ALTERNATIVE_FAKE_IP=y
FAKE_PREFIX_DEFAULT = "10.30"  # ALTERNATIVE_FAKE_IP=n (IP.30)

# x.29.* — AntiZapret VPN, x.28.* — полный VPN; третья группа — второй октет.
_CLIENT_SUBNET_RE = re.compile(r"\b(?:172|10)\.(29|28)\.(\d+)\b")
_FAKE_CIDR_RE = re.compile(r'(--fake-cidr",\s*default=")[0-9.]+/\d+"')
_AWG_ENV_RE = {
    "AZ_SUBNET": re.compile(r"^AZ_SUBNET=.*$", re.MULTILINE),
    "VPN_SUBNET": re.compile(r"^VPN_SUBNET=.*$", re.MULTILINE),
    "AZ_DNS": re.compile(r"^AZ_DNS=.*$", re.MULTILINE),
    "VPN_DNS": re.compile(r"^VPN_DNS=.*$", re.MULTILINE),
}


def client_prefix(alternative: bool) -> str:
    return CLIENT_PREFIX_ALTERNATIVE if alternative else CLIENT_PREFIX_DEFAULT


def with_client_subnets(content: str, *, alternative: bool) -> str:
    """Переписать подсети клиентов под выбранный режим; остальные строки не трогаем."""
    prefix = client_prefix(alternative)
    return _CLIENT_SUBNET_RE.sub(lambda m: f"{prefix}.{m.group(1)}.{m.group(2)}", content)


def fake_pool(alternative: bool) -> str:
    return FAKE_PREFIX_ALTERNATIVE if alternative else FAKE_PREFIX_DEFAULT


def with_fake_cidr(content: str, *, alternative: bool) -> str:
    """``--fake-cidr`` в proxy.py: default заменяется на fake-пул выбранного режима."""
    pool = f"{fake_pool(alternative)}.0.0/15"
    if not _FAKE_CIDR_RE.search(content):
        return content
    return _FAKE_CIDR_RE.sub(lambda m: f'{m.group(1)}{pool}"', content, count=1)


def with_awg_services_env(content: str, *, alternative: bool) -> str:
    """Подсети и DNS интерфейсов AZ-AWG2 (services.env) под выбранный режим."""
    prefix = client_prefix(alternative)
    wanted = {
        "AZ_SUBNET": f"{prefix}.29.9",
        "VPN_SUBNET": f"{prefix}.28.9",
        "AZ_DNS": f"{prefix}.29.8.1",
        "VPN_DNS": f"{prefix}.29.8.1",
    }
    updated = content
    for key, pattern in _AWG_ENV_RE.items():
        updated = pattern.sub(f"{key}={wanted[key]}", updated, count=1)
    return updated
