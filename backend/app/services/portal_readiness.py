def parse_portal_readiness_trailer(text: str) -> dict:
    """Parse KEY=value lines from script stdout/combined log."""
    kv: dict[str, str] = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or "=" not in line or line.startswith("["):
            continue
        key, _, val = line.partition("=")
        key = key.strip().upper()
        if key in {
            "READY",
            "ISSUES",
            "SUGGESTED_PORTAL_DOMAIN",
            "MIGRATED_TO",
            "ACTIONS_TAKEN",
            "PORTAL_DOMAIN",
            "MESSAGE",
        }:
            kv[key] = val.strip()
    issues = [x for x in kv.get("ISSUES", "").split(",") if x]
    actions = [x for x in kv.get("ACTIONS_TAKEN", "").split(",") if x]
    return {
        "ready": kv.get("READY", "").lower() == "true",
        "issues": issues,
        "suggested_portal_domain": kv.get("SUGGESTED_PORTAL_DOMAIN", ""),
        "migrated_to": kv.get("MIGRATED_TO", ""),
        "actions_taken": actions,
        "portal_domain": kv.get("PORTAL_DOMAIN", ""),
        "message": kv.get("MESSAGE", ""),
    }
