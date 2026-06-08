"""Public route-file downloads and OpenVPN folder groups (AdminAntizapret parity)."""

from __future__ import annotations

# Router slug → result file key in RESULT_FILES (cidr/constants.py)
PUBLIC_ROUTE_ROUTERS: dict[str, str] = {
    "keenetic": "keenetic_wg",
    "mikrotik": "mikrotik_wg",
    "tplink": "tplink_ovpn",
}

DEFAULT_OPENVPN_GROUP = r"GROUP_UDP\TCP"

# OpenVPN profile variant labels (antizapret.py search_dirs) per group
OPENVPN_GROUP_VARIANTS: dict[str, frozenset[str]] = {
    r"GROUP_UDP\TCP": frozenset({"antizapret", "vpn"}),
    "GROUP_UDP": frozenset({"antizapret-udp", "vpn-udp"}),
    "GROUP_TCP": frozenset({"antizapret-tcp", "vpn-tcp"}),
}

OPENVPN_GROUP_LABELS: dict[str, str] = {
    r"GROUP_UDP\TCP": "UDP+TCP",
    "GROUP_UDP": "UDP",
    "GROUP_TCP": "TCP",
}
