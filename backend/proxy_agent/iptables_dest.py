"""Pure helpers to detect/rewrite AntiZapret proxy.sh DESTINATION in iptables nat rules.

Heuristic for «installed»:
- DNAT in PREROUTING whose --dport is in AZ_PROXY_DPORTS, or
- POSTROUTING SNAT with ``-d <ip>`` (proxy.sh always SNAT to DESTINATION).

Never invokes proxy.sh — callers apply changes via ``iptables`` subprocess only.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Iterable

# Listen dports from GubernievS/AntiZapret-VPN proxy.sh (TCP and/or UDP).
AZ_PROXY_DPORTS: frozenset[int] = frozenset(
    {
        80,
        443,
        504,
        508,
        540,
        580,
        50080,
        50443,
        51080,
        51443,
        52080,
        52443,
    }
)

_DNAT_RE = re.compile(
    r"--dport\s+(\d+).*?-j\s+DNAT\s+--to-destination\s+(\d{1,3}(?:\.\d{1,3}){3})(?::\d+)?",
    re.IGNORECASE,
)
_DNAT_TO_RE = re.compile(
    r"-j\s+DNAT\s+--to-destination\s+(\d{1,3}(?:\.\d{1,3}){3})(?::\d+)?",
    re.IGNORECASE,
)
_SNAT_DEST_RE = re.compile(
    r"-d\s+(\d{1,3}(?:\.\d{1,3}){3})(?:/\d+)?\s+.*?-j\s+SNAT\b",
    re.IGNORECASE,
)
_RULE_LINE_RE = re.compile(r"^(-A\s+\S+\s+)(.+)$")


def _parse_ipv4(value: str) -> str:
    addr = ipaddress.ip_address(value.strip())
    if addr.version != 4:
        raise ValueError("Ожидается IPv4")
    if addr.is_unspecified or addr.is_multicast or addr.is_loopback:
        raise ValueError("Недопустимый IPv4 для DESTINATION")
    return str(addr)


def validate_destination_ip(value: str) -> str:
    """Validate and normalize DESTINATION IPv4; raise ValueError if bad."""
    return _parse_ipv4(value)


def _iter_rule_lines(rules_text: str) -> Iterable[str]:
    for raw in rules_text.splitlines():
        line = raw.strip()
        if line.startswith("-A "):
            yield line


def detect_proxy_destination(rules_text: str) -> str | None:
    """Return DESTINATION IPv4 from AZ DNAT rules, else from SNAT -d, else None."""
    dnat_ips: list[str] = []
    for line in _iter_rule_lines(rules_text):
        m = _DNAT_RE.search(line)
        if m:
            dport = int(m.group(1))
            ip = m.group(2)
            if dport in AZ_PROXY_DPORTS:
                dnat_ips.append(ip)
                continue
        # DNAT without captured dport still considered if to-destination present
        # and line mentions a known port elsewhere
        if "DNAT" in line.upper():
            dport_m = re.search(r"--dport\s+(\d+)", line)
            to_m = _DNAT_TO_RE.search(line)
            if dport_m and to_m and int(dport_m.group(1)) in AZ_PROXY_DPORTS:
                dnat_ips.append(to_m.group(1))

    if dnat_ips:
        # Majority / first consistent AZ destination
        return dnat_ips[0]

    for line in _iter_rule_lines(rules_text):
        m = _SNAT_DEST_RE.search(line)
        if m:
            return m.group(1)
    return None


def is_proxy_installed(rules_text: str) -> bool:
    """True if AZ-port DNAT or SNAT-to-destination traces are present."""
    for line in _iter_rule_lines(rules_text):
        dport_m = re.search(r"--dport\s+(\d+)", line)
        if dport_m and "DNAT" in line.upper() and int(dport_m.group(1)) in AZ_PROXY_DPORTS:
            return True
        if _SNAT_DEST_RE.search(line):
            return True
    return False


def rewrite_destination_rules(rules_text: str, old_ip: str, new_ip: str) -> str:
    """Return iptables-save-like text with old DESTINATION replaced by new_ip."""
    old = _parse_ipv4(old_ip)
    new = _parse_ipv4(new_ip)
    if old == new:
        return rules_text

    out: list[str] = []
    for raw in rules_text.splitlines():
        line = raw
        if line.strip().startswith("-A ") and old in line:
            # Replace IP in DNAT --to-destination and SNAT -d carefully
            line = re.sub(
                rf"(--to-destination\s+){re.escape(old)}(:\d+)?",
                rf"\g<1>{new}\2",
                line,
            )
            line = re.sub(
                rf"(-d\s+){re.escape(old)}(/\d+)?",
                rf"\g<1>{new}\2",
                line,
            )
        out.append(line)
    return "\n".join(out) + ("\n" if rules_text.endswith("\n") else "")


def _line_to_iptables_args(line: str) -> list[str]:
    """Convert a ``-A CHAIN ...`` save line to iptables argv tokens (no quotes)."""
    # iptables-save uses spaces; --to-destination value has no spaces.
    tokens = line.split()
    if not tokens or tokens[0] != "-A":
        raise ValueError(f"Не правило -A: {line}")
    return tokens


def plan_destination_rewrite(rules_text: str, old_ip: str, new_ip: str) -> list[list[str]]:
    """Build ordered iptables argv list: for each affected rule, -D old then -A new.

    Agent runtime executes these via subprocess; unit tests assert shape only.
    """
    old = _parse_ipv4(old_ip)
    new = _parse_ipv4(new_ip)
    if old == new:
        raise ValueError("Новый DESTINATION совпадает с текущим")

    rewritten = rewrite_destination_rules(rules_text, old, new)
    plan: list[list[str]] = []
    old_lines = [ln for ln in _iter_rule_lines(rules_text) if old in ln]
    new_by_idx = [ln for ln in _iter_rule_lines(rewritten) if new in ln and old not in ln]

    # Pair by position among rewritten peers; fall back to string replace per line
    if len(old_lines) != len(new_by_idx):
        new_by_idx = []
        for ln in old_lines:
            nln = rewrite_destination_rules(ln + "\n", old, new).strip()
            new_by_idx.append(nln)

    for old_line, new_line in zip(old_lines, new_by_idx, strict=False):
        if old_line == new_line:
            continue
        old_args = _line_to_iptables_args(old_line)
        new_args = _line_to_iptables_args(new_line)
        # -D CHAIN ...
        plan.append(["iptables", "-w", "-t", "nat", "-D", *old_args[1:]])
        # -A CHAIN ...
        plan.append(["iptables", "-w", "-t", "nat", "-A", *new_args[1:]])
    return plan
