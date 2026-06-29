"""Group and label VPN profile files for Telegram bot config picker."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.profile_download_name import AZ_PROFILE_DIR, enrich_profile_files

GROUP_ORDER = ("ovpn", "wg", "awg")
GROUP_META: dict[str, tuple[str, str]] = {
    "ovpn": ("🔐", "OpenVPN"),
    "wg": ("🛡️", "WireGuard"),
    "awg": ("🌀", "AmneziaWG"),
}


@dataclass(frozen=True)
class ProfileFileEntry:
    index: int
    file: dict[str, str]


@dataclass(frozen=True)
class ProfileFileGroup:
    key: str
    emoji: str
    title: str
    files: list[ProfileFileEntry]


def protocol_group_key(protocol: str) -> str:
    value = (protocol or "").strip().lower()
    if value == "openvpn":
        return "ovpn"
    if value == "wireguard":
        return "wg"
    if value == "amneziawg":
        return "awg"
    return "other"


def is_az_profile(*, variant: str, path: str) -> bool:
    if "antizapret" in (variant or ""):
        return True
    return bool(AZ_PROFILE_DIR.search((path or "").replace("\\", "/")))


def file_route_label(*, variant: str, path: str) -> str:
    return "AZ" if is_az_profile(variant=variant, path=path) else "VPN"


def file_variant_suffix(*, protocol: str, variant: str, path: str) -> str:
    proto = (protocol or "").lower()
    normalized = f"{variant} {path}".lower()
    if proto == "openvpn":
        if "udp" in normalized:
            return "UDP"
        if "tcp" in normalized:
            return "TCP"
    return ""


def file_compact_label(file_item: dict[str, str], *, index: int | None = None) -> str:
    route = file_route_label(variant=file_item.get("variant", ""), path=file_item.get("path", ""))
    suffix = file_variant_suffix(
        protocol=file_item.get("protocol", ""),
        variant=file_item.get("variant", ""),
        path=file_item.get("path", ""),
    )
    proto = (file_item.get("protocol") or "").lower()
    if suffix:
        detail = suffix
    elif proto == "openvpn":
        detail = "базовый"
    else:
        detail = route
    label = f"{route} · {detail}"
    if index is None:
        return label
    return f"{index}. {label}"


def file_preview_line(index: int, file_item: dict[str, str]) -> str:
    route = file_route_label(variant=file_item.get("variant", ""), path=file_item.get("path", ""))
    suffix = file_variant_suffix(
        protocol=file_item.get("protocol", ""),
        variant=file_item.get("variant", ""),
        path=file_item.get("path", ""),
    )
    download_name = file_item.get("download_filename") or file_item.get("filename") or "—"
    route_mark = "🇷🇺" if route == "AZ" else "🌍"
    tag = f"{route} · {suffix}" if suffix else route
    return f"{index}. {route_mark} {tag} — <code>{download_name}</code>"


def file_button_label(file_item: dict[str, str], *, index: int | None = None) -> str:
    return file_compact_label(file_item, index=index)


def file_caption(*, client_name: str, file_item: dict[str, str]) -> str:
    group_key = protocol_group_key(file_item.get("protocol", ""))
    emoji, title = GROUP_META.get(group_key, ("📄", "Конфиг"))
    route = file_route_label(variant=file_item.get("variant", ""), path=file_item.get("path", ""))
    suffix = file_variant_suffix(
        protocol=file_item.get("protocol", ""),
        variant=file_item.get("variant", ""),
        path=file_item.get("path", ""),
    )
    download_name = file_item.get("download_filename") or file_item.get("filename") or client_name
    route_line = f"{route} · {suffix}" if suffix else route
    return f"{emoji} <b>{title}</b> · {route_line}\n<code>{client_name}</code>\n{download_name}"


def build_profile_file_groups(client_name: str, files: list[dict[str, str]]) -> list[ProfileFileGroup]:
    enriched = enrich_profile_files(client_name, files)
    grouped: dict[str, list[ProfileFileEntry]] = {}
    for index, file_item in enumerate(enriched):
        key = protocol_group_key(file_item.get("protocol", ""))
        grouped.setdefault(key, []).append(ProfileFileEntry(index=index, file=file_item))

    result: list[ProfileFileGroup] = []
    for key in GROUP_ORDER:
        entries = grouped.get(key)
        if not entries:
            continue
        emoji, title = GROUP_META[key]
        result.append(ProfileFileGroup(key=key, emoji=emoji, title=title, files=entries))
    for key, entries in grouped.items():
        if key in GROUP_ORDER:
            continue
        result.append(ProfileFileGroup(key=key, emoji="📄", title=key.upper(), files=entries))
    return result


def find_group(groups: list[ProfileFileGroup], key: str) -> ProfileFileGroup | None:
    for group in groups:
        if group.key == key:
            return group
    return None
