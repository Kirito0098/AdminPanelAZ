"""Mask portal / one-time download tokens in uvicorn access log lines."""

from __future__ import annotations

import logging
import re

_TOKEN_PATH_RE = re.compile(
    r"((?:/p(?:/u)?/|/api/public/(?:qr-download|portal)/|/api/telegram/webhook/))([^/?\s\"']+)"
)

# uvicorn.access logs '%s - "%s %s HTTP/%s" %d': client, method, full_path, http_version, status_code.
_ACCESS_LOG_ARGS = 5


def mask_token_paths(message: str) -> str:
    return _TOKEN_PATH_RE.sub(r"\1***", message or "")


class TokenPathAccessLogFilter(logging.Filter):
    """Mask tokens inside the path, keeping the record shape uvicorn's AccessFormatter unpacks."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == "uvicorn.access":
            args = record.args
            if isinstance(args, tuple) and len(args) == _ACCESS_LOG_ARGS and isinstance(args[2], str):
                record.args = (*args[:2], mask_token_paths(args[2]), *args[3:])
            return True
        try:
            record.msg = mask_token_paths(record.getMessage())
            record.args = ()
        except (TypeError, ValueError):
            pass
        return True


def install_uvicorn_access_log_filter() -> None:
    filt = TokenPathAccessLogFilter()
    for name in ("uvicorn.access", "uvicorn"):
        logging.getLogger(name).addFilter(filt)
