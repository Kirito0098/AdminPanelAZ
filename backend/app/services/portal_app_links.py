"""Ссылки на приложения в клиентском портале (Fider #41).

Хранится только то, что админ переопределил: ``{"openvpn": {"android": "https://…"}}``.
Пустая ячейка означает «официальная ссылка проекта» — фронт подставляет своё
значение по умолчанию, база остаётся чистой.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.models import AppSetting

logger = logging.getLogger(__name__)

SETTING_KEY = "portal_app_links"

PROTOCOLS: tuple[str, ...] = ("openvpn", "wireguard", "amneziawg", "amneziawg2")
PLATFORMS: tuple[str, ...] = ("windows", "android", "ios", "mac", "linux")
MAX_URL_LENGTH = 500

AppLinks = dict[str, dict[str, str]]


def normalize_app_links(raw: object) -> tuple[AppLinks, list[str]]:
    """Оставить только известные протоколы/платформы и валидные http(s)-ссылки."""
    links: AppLinks = {}
    warnings: list[str] = []
    if not isinstance(raw, dict):
        return links, warnings
    for protocol, platforms in raw.items():
        if protocol not in PROTOCOLS:
            warnings.append(f"неизвестный протокол: {protocol}")
            continue
        if not isinstance(platforms, dict):
            warnings.append(f"{protocol}: ожидался объект платформ")
            continue
        for platform, url in platforms.items():
            if platform not in PLATFORMS:
                warnings.append(f"{protocol}: неизвестная платформа {platform}")
                continue
            value = (url or "").strip() if isinstance(url, str) else ""
            if not value:
                continue
            if len(value) > MAX_URL_LENGTH:
                warnings.append(f"{protocol}/{platform}: ссылка длиннее {MAX_URL_LENGTH} символов")
                continue
            if not (value.startswith("https://") or value.startswith("http://")):
                warnings.append(f"{protocol}/{platform}: ссылка должна начинаться с http:// или https://")
                continue
            links.setdefault(protocol, {})[platform] = value
    return links, warnings


def get_portal_app_links(db: Session) -> AppLinks:
    row = db.query(AppSetting).filter(AppSetting.key == SETTING_KEY).first()
    if row is None or not row.value:
        return {}
    try:
        data = json.loads(row.value)
    except (TypeError, ValueError):
        logger.warning("portal_app_links: битый JSON в настройках, игнорируем")
        return {}
    links, _warnings = normalize_app_links(data)
    return links


def set_portal_app_links(db: Session, raw: object) -> tuple[AppLinks, list[str]]:
    links, warnings = normalize_app_links(raw)
    value = json.dumps(links, ensure_ascii=False) if links else ""
    row = db.query(AppSetting).filter(AppSetting.key == SETTING_KEY).first()
    if row is None:
        db.add(AppSetting(key=SETTING_KEY, value=value))
    else:
        row.value = value
    db.commit()
    return links, warnings
