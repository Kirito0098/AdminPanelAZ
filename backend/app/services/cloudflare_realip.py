"""Fetch, parse, validate, and render Cloudflare realip nginx snippet."""

from __future__ import annotations

import hashlib
import ipaddress
from datetime import UTC, datetime
from typing import Protocol

import httpx

CF_IPS_V4_URL = "https://www.cloudflare.com/ips-v4"
CF_IPS_V6_URL = "https://www.cloudflare.com/ips-v6"

_DEFAULT_TIMEOUT = httpx.Timeout(15.0)


class _HttpClient(Protocol):
    def get(self, url: str) -> httpx.Response: ...


def parse_cloudflare_ip_list(text: str) -> list[str]:
    networks: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            ipaddress.ip_network(line, strict=False)
        except ValueError as exc:
            raise ValueError(f"invalid CIDR: {line!r}") from exc
        networks.append(line)
    if not networks:
        raise ValueError("empty Cloudflare IP list")
    return networks


def render_cloudflare_realip_conf(
    ipv4: list[str],
    ipv6: list[str],
    *,
    snapshot_date: str,
) -> str:
    lines = [
        "# Cloudflare IP ranges for ngx_http_realip_module (Telegram webhook only).",
        f"# Source: {CF_IPS_V4_URL} / {CF_IPS_V6_URL}",
        f"# snapshot: {snapshot_date}",
        "",
    ]
    for network in ipv4:
        lines.append(f"set_real_ip_from {network};")
    if ipv4 and ipv6:
        lines.append("")
    for network in ipv6:
        lines.append(f"set_real_ip_from {network};")
    if ipv4 or ipv6:
        lines.append("")
    lines.extend(
        [
            "real_ip_header CF-Connecting-IP;",
            "real_ip_recursive on;",
        ]
    )
    return "\n".join(lines) + "\n"


def _normalize_body(body: str) -> str:
    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def content_hash(body: str) -> str:
    return hashlib.sha256(_normalize_body(body).encode("utf-8")).hexdigest()


def _fetch_text(client: _HttpClient, url: str, label: str) -> str:
    try:
        response = client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"не удалось загрузить {label}: {exc}") from exc
    text = response.text.strip()
    if not text:
        raise RuntimeError(f"пустой ответ от {label}")
    return text


def fetch_cloudflare_realip_conf(
    *,
    client: _HttpClient | None = None,
    snapshot_date: str | None = None,
) -> tuple[str, str]:
    date = snapshot_date or datetime.now(UTC).date().isoformat()
    owns_client = client is None
    http_client: _HttpClient = client or httpx.Client(timeout=_DEFAULT_TIMEOUT)
    try:
        ipv4_text = _fetch_text(http_client, CF_IPS_V4_URL, "Cloudflare IPv4")
        ipv6_text = _fetch_text(http_client, CF_IPS_V6_URL, "Cloudflare IPv6")
        ipv4 = parse_cloudflare_ip_list(ipv4_text)
        ipv6 = parse_cloudflare_ip_list(ipv6_text)
    except ValueError as exc:
        raise RuntimeError(f"некорректный список Cloudflare CIDR: {exc}") from exc
    finally:
        if owns_client:
            http_client.close()  # type: ignore[union-attr]
    body = render_cloudflare_realip_conf(ipv4, ipv6, snapshot_date=date)
    return body, content_hash(body)
