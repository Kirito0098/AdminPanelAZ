"""CIDR parsing and normalization."""
import ipaddress
from datetime import datetime, timezone

from app.services.cidr.pipeline.constants import (
    CIDR_V4_SCAN_PATTERN,
    _BGP_TOOLS_RAW_ALLOC_IPV4_PATTERN,
)


def _normalize_cidrs(values):
    cidrs = set()
    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        try:
            network = ipaddress.ip_network(raw, strict=False)
        except ValueError:
            continue
        if network.version != 4:
            continue
        if network.prefixlen == 0:
            continue
        cidrs.add(str(network))
    return sorted(cidrs)

def _normalize_single_cidr(raw):
    normalized = _normalize_cidrs([raw])
    return normalized[0] if normalized else None


def _extract_bgp_tools_ipv4(text_data):
    """BGP.tools scan with full-page fallback (DB pipeline — no geo filter)."""
    raw = text_data or ""
    lowered = raw.lower()
    raw_marker = lowered.find("raw allocations")
    if raw_marker < 0:
        return CIDR_V4_SCAN_PATTERN.findall(raw)

    additional_links_marker = lowered.find("additional links", raw_marker)
    scoped = raw[raw_marker:additional_links_marker] if additional_links_marker > raw_marker else raw[raw_marker:]

    candidates = []
    for match in _BGP_TOOLS_RAW_ALLOC_IPV4_PATTERN.finditer(scoped):
        block = match.group(1)
        if block:
            candidates.extend(CIDR_V4_SCAN_PATTERN.findall(block))
    return candidates


def _render_file_content(file_name, cidrs, source_name):
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    # Агрегируем смежные/поглощённые блоки перед записью
    try:
        parsed = [ipaddress.ip_network(c, strict=False) for c in cidrs if c]
        aggregated = [str(n) for n in ipaddress.collapse_addresses(parsed)]
    except (ValueError, TypeError):
        aggregated = list(cidrs)
    lines = [
        f"# Auto-generated CIDR list for {file_name}",
        f"# Source: {source_name}",
        f"# Generated at: {generated_at}",
        "",
    ]
    lines.extend(aggregated)
    return "\n".join(lines) + "\n"

