#!/usr/bin/env python3
"""Аварийное управление IP-whitelist панели (если заблокировали себя в UI)."""

from __future__ import annotations

import argparse
import ipaddress
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
os.chdir(BACKEND)
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.database import SessionLocal  # noqa: E402
from app.services.panel_port_firewall import panel_port_firewall  # noqa: E402
from app.services.security import SecurityService  # noqa: E402


def _print_status(settings: dict) -> None:
    ip_on = bool(settings.get("ip_restriction_enabled"))
    fw_on = bool(settings.get("whitelist_firewall"))
    fw_active = bool(settings.get("whitelist_firewall_active"))
    allowed = settings.get("allowed_ips") or []
    temp = settings.get("temp_whitelist") or []

    print(f"IP-ограничение:           {'вкл' if ip_on else 'выкл'}")
    print(f"Firewall whitelist (флаг): {'вкл' if fw_on else 'выкл'}")
    print(f"Firewall whitelist (актив): {'да' if fw_active else 'нет'}")
    print(f"Постоянных IP:            {len(allowed)}")
    if allowed:
        print(f"  {', '.join(allowed)}")
    print(f"Временных IP:             {len(temp)}")
    for row in temp:
        print(f"  {row.get('ip')} (ещё ~{row.get('hours')} ч., до {row.get('expires_at')})")


def cmd_status(_: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        settings = SecurityService().get_settings(db)
        _print_status(settings)
    finally:
        db.close()
    return 0


def cmd_disable(_: argparse.Namespace) -> int:
    db = SessionLocal()
    service = SecurityService()
    try:
        before = service.get_settings(db)
        service.update_settings(
            db,
            {
                "ip_restriction_enabled": False,
                "whitelist_firewall": False,
            },
        )
        # Сразу снять iptables/ipset через тот же путь, что и UI
        fw_ok = bool(service.sync_whitelist_port_firewall(db))
        try:
            # На случай если sync вернул False из‑за applicable=false — всё равно снять jump
            panel_port_firewall.disable()
            fw_ok = True
        except Exception as exc:  # noqa: BLE001 — CLI recovery must continue
            print(f"Предупреждение: не удалось снять правила firewall: {exc}", file=sys.stderr)
            if os.geteuid() != 0:
                print(
                    "Подсказка: для снятия iptables запустите от root: "
                    "sudo ./scripts/disable-ip-whitelist.sh disable",
                    file=sys.stderr,
                )

        after = service.get_settings(db)
        print("IP-whitelist отключён.")
        print(
            f"  было: ограничение={'вкл' if before.get('ip_restriction_enabled') else 'выкл'}, "
            f"fw={'вкл' if before.get('whitelist_firewall') else 'выкл'}"
        )
        print(
            f"  стало: ограничение={'вкл' if after.get('ip_restriction_enabled') else 'выкл'}, "
            f"fw={'вкл' if after.get('whitelist_firewall') else 'выкл'}"
        )
        if fw_ok:
            print("Правила AA_PANEL_WHITELIST / ipset сняты (если были).")
        print(
            "Можно открывать панель с любого IP. "
            "После входа снова включите whitelist в UI при необходимости."
        )
    finally:
        db.close()
    return 0


def cmd_add_ip(args: argparse.Namespace) -> int:
    ip = (args.ip or "").strip()
    try:
        ipaddress.ip_network(ip, strict=False)
    except ValueError:
        print(f"Ошибка: некорректный IP или CIDR: {ip}", file=sys.stderr)
        return 1

    db = SessionLocal()
    service = SecurityService()
    try:
        settings = service.get_settings(db)
        allowed = list(settings.get("allowed_ips") or [])
        if ip in allowed:
            print(f"IP {ip} уже в постоянном whitelist.")
        else:
            allowed.append(ip)
            service.update_settings(db, {"allowed_ips": allowed})
            print(f"IP {ip} добавлен в постоянный whitelist.")

        if args.enable and not settings.get("ip_restriction_enabled"):
            service.update_settings(db, {"ip_restriction_enabled": True})
            print("IP-ограничение включено.")

        service.sync_whitelist_port_firewall(db)
        _print_status(service.get_settings(db))
    finally:
        db.close()
    return 0


def cmd_temp_ip(args: argparse.Namespace) -> int:
    ip = (args.ip or "").strip()
    hours = int(args.hours)
    if hours < 1 or hours > 168:
        print("Ошибка: --hours должен быть от 1 до 168", file=sys.stderr)
        return 1

    db = SessionLocal()
    service = SecurityService()
    try:
        settings = service.get_settings(db)
        if not settings.get("ip_restriction_enabled"):
            print(
                "Предупреждение: IP-ограничение сейчас выключено — temp whitelist не влияет, "
                "пока ограничение не включено.",
                file=sys.stderr,
            )
        service.add_temp_whitelist(db, ip, hours)
        service.sync_whitelist_port_firewall(db)
        print(f"IP {ip} добавлен во временный whitelist на {hours} ч.")
        _print_status(service.get_settings(db))
    except ValueError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Аварийное отключение / правка IP-whitelist AdminPanelAZ (SSH recovery)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="Показать текущие настройки whitelist")
    p_status.set_defaults(func=cmd_status)

    p_disable = sub.add_parser(
        "disable",
        help="Выключить IP-ограничение и firewall whitelist (разблокировать доступ)",
    )
    p_disable.set_defaults(func=cmd_disable)

    p_add = sub.add_parser("add-ip", help="Добавить IP/CIDR в постоянный whitelist")
    p_add.add_argument("ip", help="IP или CIDR, например 203.0.113.10 или 192.168.1.0/24")
    p_add.add_argument(
        "--enable",
        action="store_true",
        help="Также включить IP-ограничение (если было выключено)",
    )
    p_add.set_defaults(func=cmd_add_ip)

    p_temp = sub.add_parser("temp-ip", help="Добавить IP во временный whitelist")
    p_temp.add_argument("ip", help="IPv4/IPv6 адрес (без CIDR)")
    p_temp.add_argument("--hours", type=int, default=24, help="Срок в часах (1–168, по умолчанию 24)")
    p_temp.set_defaults(func=cmd_temp_ip)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
