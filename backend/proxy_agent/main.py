"""Lightweight AntiZapret proxy agent — runs on RU proxy hosts (port 9101).

Never installs or runs proxy.sh. DESTINATION edits use iptables only.
"""

from __future__ import annotations

import ipaddress
import os
import secrets
import subprocess
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from proxy_agent import PROXY_AGENT_VERSION
from proxy_agent.conntrack_maps import parse_conntrack_mappings
from proxy_agent.iptables_dest import (
    IptablesApplyError,
    apply_iptables_plan,
    detect_proxy_destination,
    is_proxy_installed,
    plan_destination_rewrite,
    validate_destination_ip,
)

PROXY_AGENT_API_KEY = os.environ.get("PROXY_AGENT_API_KEY", "change-me-proxy-agent-key")
PROXY_AGENT_PORT = int(os.environ.get("PROXY_AGENT_PORT", "9101"))
PROXY_AGENT_MODE = os.environ.get("PROXY_AGENT_MODE", "prod").strip().lower()
PROXY_AGENT_ALLOWED_IPS = [
    ip.strip() for ip in os.environ.get("PROXY_AGENT_ALLOWED_IPS", "").split(",") if ip.strip()
]
PROXY_AGENT_MTLS_ENABLED = os.environ.get("PROXY_AGENT_MTLS_ENABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
}
PROXY_AGENT_MTLS_SERVER_CERT = os.environ.get(
    "PROXY_AGENT_MTLS_SERVER_CERT", "/etc/adminpanelaz/mtls/agent.crt"
)
PROXY_AGENT_MTLS_SERVER_KEY = os.environ.get(
    "PROXY_AGENT_MTLS_SERVER_KEY", "/etc/adminpanelaz/mtls/agent.key"
)
PROXY_AGENT_MTLS_CA_CERT = os.environ.get(
    "PROXY_AGENT_MTLS_CA_CERT", "/etc/adminpanelaz/mtls/ca.crt"
)
_DEFAULT_PROXY_KEY = "change-me-proxy-agent-key"


def _validate_api_key_or_exit() -> None:
    if PROXY_AGENT_MODE != "prod":
        return
    if not PROXY_AGENT_API_KEY or PROXY_AGENT_API_KEY == _DEFAULT_PROXY_KEY or len(PROXY_AGENT_API_KEY) < 24:
        raise SystemExit(
            "В production задайте PROXY_AGENT_API_KEY (минимум 24 случайных символа). "
            "Пример: openssl rand -hex 32"
        )


_validate_api_key_or_exit()

app = FastAPI(title="AntiZapret Proxy Agent", version=PROXY_AGENT_VERSION)


class ProxyAgentIpAllowlistMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not PROXY_AGENT_ALLOWED_IPS:
            return await call_next(request)
        client_ip = request.client.host if request.client else ""
        if client_ip.startswith("::ffff:"):
            client_ip = client_ip[7:]
        try:
            addr = ipaddress.ip_address(client_ip)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ запрещён") from None
        for entry in PROXY_AGENT_ALLOWED_IPS:
            try:
                if "/" in entry:
                    if addr in ipaddress.ip_network(entry, strict=False):
                        return await call_next(request)
                elif addr == ipaddress.ip_address(entry):
                    return await call_next(request)
            except ValueError:
                continue
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ запрещён с вашего IP")


app.add_middleware(ProxyAgentIpAllowlistMiddleware)


def verify_api_key(x_node_key: str = Header(..., alias="X-Node-Key")) -> None:
    """Auth header name matches node_agent; value checked against PROXY_AGENT_API_KEY."""
    if not x_node_key or not secrets.compare_digest(x_node_key, PROXY_AGENT_API_KEY):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный API-ключ узла")


class DestinationBody(BaseModel):
    destination_ip: str = Field(..., min_length=7, max_length=64)


def _run_iptables_save_nat() -> str:
    try:
        proc = subprocess.run(
            ["iptables-save", "-t", "nat"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"iptables-save недоступен: {exc}",
        ) from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"iptables-save ошибка: {err}",
        )
    return proc.stdout or ""


def _apply_iptables_plan(plan: list[list[str]]) -> None:
    try:
        apply_iptables_plan(plan)
    except IptablesApplyError as exc:
        detail = str(exc)
        if exc.rollback_errors:
            detail = f"{detail}; rollback: {'; '.join(exc.rollback_errors)}"
        code = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if "недоступен" in detail
            else status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        raise HTTPException(status_code=code, detail=detail) from exc


def _status_from_rules(rules_text: str) -> dict:
    installed = is_proxy_installed(rules_text)
    dest = detect_proxy_destination(rules_text)
    detail = None
    if not installed:
        detail = "Правила AntiZapret proxy (DNAT на известные порты / SNAT) не найдены"
    elif not dest:
        detail = "Прокси-правила есть, но DESTINATION IP не определён"
    return {
        "installed": installed,
        "destination_ip": dest,
        "detail": detail,
    }


@app.get("/health")
def health(_: None = Depends(verify_api_key)):
    return {"ok": True, "version": PROXY_AGENT_VERSION}


@app.get("/proxy/status")
def proxy_status(_: None = Depends(verify_api_key)):
    rules = _run_iptables_save_nat()
    return _status_from_rules(rules)


@app.put("/proxy/destination")
def proxy_destination(payload: DestinationBody, _: None = Depends(verify_api_key)):
    try:
        new_ip = validate_destination_ip(payload.destination_ip)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    rules = _run_iptables_save_nat()
    old_ip = detect_proxy_destination(rules)
    if not old_ip:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Текущий DESTINATION не найден в nat-правилах (proxy.sh установлен?)",
        )
    if old_ip == new_ip:
        return _status_from_rules(rules)

    try:
        plan = plan_destination_rewrite(rules, old_ip, new_ip)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нет правил для замены DESTINATION",
        )
    _apply_iptables_plan(plan)
    # Persist if netfilter-persistent available (best-effort)
    try:
        subprocess.run(
            ["netfilter-persistent", "save"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return _status_from_rules(_run_iptables_save_nat())


@app.get("/proxy/mappings")
def proxy_mappings(_: None = Depends(verify_api_key)):
    """Best-effort conntrack mappings; empty list if conntrack unavailable."""
    try:
        proc = subprocess.run(
            ["conntrack", "-L"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"mappings": []}
    if proc.returncode != 0:
        return {"mappings": []}
    return {"mappings": parse_conntrack_mappings(proc.stdout or "")}


def _uvicorn_ssl_kwargs() -> dict:
    if not PROXY_AGENT_MTLS_ENABLED:
        return {}
    cert = Path(PROXY_AGENT_MTLS_SERVER_CERT)
    key = Path(PROXY_AGENT_MTLS_SERVER_KEY)
    ca = Path(PROXY_AGENT_MTLS_CA_CERT)
    if not all(p.is_file() for p in (cert, key, ca)):
        return {}
    return {
        "ssl_certfile": str(cert),
        "ssl_keyfile": str(key),
        "ssl_ca_certs": str(ca),
        "ssl_cert_reqs": 2,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "proxy_agent.main:app",
        host="0.0.0.0",
        port=PROXY_AGENT_PORT,
        reload=False,
        **_uvicorn_ssl_kwargs(),
    )
