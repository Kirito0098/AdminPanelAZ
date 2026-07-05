"""Human-readable labels from HTTP User-Agent strings."""

from __future__ import annotations


def format_user_agent_label(raw: str | None, *, login_via: str | None = None) -> str | None:
    if login_via:
        return login_via.strip() or None

    ua = (raw or "").strip()
    if not ua:
        return None

    ua_lower = ua.lower()

    if "iphone" in ua_lower:
        os_label = "iPhone"
    elif "ipad" in ua_lower:
        os_label = "iPad"
    elif "android" in ua_lower:
        os_label = "Android"
    elif "mac os x" in ua_lower or "macintosh" in ua_lower:
        os_label = "macOS"
    elif "windows" in ua_lower:
        os_label = "Windows"
    elif "linux" in ua_lower:
        os_label = "Linux"
    else:
        os_label = None

    if "edg/" in ua_lower or "edge/" in ua_lower:
        browser = "Edge"
    elif "firefox/" in ua_lower:
        browser = "Firefox"
    elif "opr/" in ua_lower or "opera" in ua_lower:
        browser = "Opera"
    elif "chrome/" in ua_lower or "crios/" in ua_lower:
        browser = "Chrome"
    elif "safari/" in ua_lower:
        browser = "Safari"
    else:
        browser = None

    parts = [part for part in (browser, os_label) if part]
    if parts:
        return " · ".join(parts)

    compact = ua.replace("\n", " ").strip()
    if len(compact) > 72:
        return compact[:69] + "..."
    return compact


def is_mobile_user_agent(raw: str | None) -> bool:
    ua = (raw or "").lower()
    return any(token in ua for token in ("iphone", "ipad", "android", "mobile"))


def user_agent_from_request(request) -> str | None:
    ua = (request.headers.get("User-Agent") or "").strip()
    return ua[:255] if ua else None
