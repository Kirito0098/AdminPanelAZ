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


def _ipv4_in_line(line: str, ip: str) -> bool:
    """True if ``ip`` appears as a full IPv4 token (not a prefix of another IP)."""
    return bool(re.search(rf"(?<!\d){re.escape(ip)}(?!\d)", line))


def rewrite_destination_rules(rules_text: str, old_ip: str, new_ip: str) -> str:
    """Return iptables-save-like text with old DESTINATION replaced by new_ip."""
    old = _parse_ipv4(old_ip)
    new = _parse_ipv4(new_ip)
    if old == new:
        return rules_text

    # (?!\d) end-boundary: replacing 10.0.0.1 must not touch 10.0.0.10
    out: list[str] = []
    for raw in rules_text.splitlines():
        line = raw
        if line.strip().startswith("-A ") and _ipv4_in_line(line, old):
            line = re.sub(
                rf"(--to-destination\s+){re.escape(old)}(?!\d)(:\d+)?",
                rf"\g<1>{new}\2",
                line,
            )
            line = re.sub(
                rf"(-d\s+){re.escape(old)}(?!\d)(/\d+)?",
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
    old_lines = [ln for ln in _iter_rule_lines(rules_text) if _ipv4_in_line(ln, old)]
    new_by_idx = [
        ln
        for ln in _iter_rule_lines(rewritten)
        if _ipv4_in_line(ln, new) and not _ipv4_in_line(ln, old)
    ]

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


def invert_iptables_argv(argv: list[str]) -> list[str]:
    """Flip ``-D`` ↔ ``-A`` for rollback of a successful step."""
    out = list(argv)
    for i, tok in enumerate(out):
        if tok == "-D":
            out[i] = "-A"
            return out
        if tok == "-A":
            out[i] = "-D"
            return out
    raise ValueError(f"Нет -A/-D в команде: {argv}")


class IptablesApplyError(RuntimeError):
    """Raised when a plan step fails (after best-effort rollback of prior steps)."""

    def __init__(self, message: str, *, rollback_errors: list[str] | None = None):
        super().__init__(message)
        self.rollback_errors = rollback_errors or []


def apply_iptables_plan(
    plan: list[list[str]],
    *,
    runner=None,
    timeout: float = 30,
) -> None:
    """Execute ``-D``/``-A`` plan; on mid-plan failure, best-effort rollback of applied steps.

    Rollback runs inverted argv in reverse order (``-A``→``-D``, ``-D``→``-A``).
    ``runner`` defaults to ``subprocess.run`` (injectable for tests).
    """
    import subprocess as _subprocess

    run = runner or _subprocess.run
    applied: list[list[str]] = []

    for argv in plan:
        try:
            proc = run(argv, check=False, capture_output=True, text=True, timeout=timeout)
        except (FileNotFoundError, _subprocess.TimeoutExpired) as exc:
            _rollback_applied(applied, run=run, timeout=timeout)
            raise IptablesApplyError(f"iptables недоступен: {exc}") from exc

        rc = getattr(proc, "returncode", 0)
        if rc != 0:
            err = (getattr(proc, "stderr", None) or getattr(proc, "stdout", None) or "").strip()
            err = err or f"exit {rc}"
            rollback_errors = _rollback_applied(applied, run=run, timeout=timeout)
            raise IptablesApplyError(
                f"Не удалось применить iptables ({' '.join(argv)}): {err}",
                rollback_errors=rollback_errors,
            )
        applied.append(argv)


def _rollback_applied(
    applied: list[list[str]],
    *,
    run,
    timeout: float,
) -> list[str]:
    """Best-effort reverse of successful steps. Returns non-fatal rollback error strings."""
    import subprocess as _subprocess

    errors: list[str] = []
    for argv in reversed(applied):
        try:
            inv = invert_iptables_argv(argv)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        try:
            proc = run(inv, check=False, capture_output=True, text=True, timeout=timeout)
        except (FileNotFoundError, _subprocess.TimeoutExpired) as exc:
            errors.append(f"{' '.join(inv)}: {exc}")
            continue
        if getattr(proc, "returncode", 0) != 0:
            err = (getattr(proc, "stderr", None) or getattr(proc, "stdout", None) or "").strip()
            errors.append(f"{' '.join(inv)}: {err or proc.returncode}")
    return errors
