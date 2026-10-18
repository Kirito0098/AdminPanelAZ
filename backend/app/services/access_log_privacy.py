"""Mask portal / one-time download tokens in uvicorn access log lines."""

from __future__ import annotations

import logging
import re

_TOKEN_PATH_RE = re.compile(
    r"((?:/p(?:/u)?/|/api/public/(?:qr-download|portal)/|/api/telegram/webhook/))([^/?\s\"']+)"
)


def mask_token_paths(message: str) -> str:
    return _TOKEN_PATH_RE.sub(r"\1***", message or "")


class TokenPathAccessLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = mask_token_paths(str(record.getMessage()))
            record.args = ()
        except Exception:
            pass
        return True


def install_uvicorn_access_log_filter() -> None:
    filt = TokenPathAccessLogFilter()
    for name in ("uvicorn.access", "uvicorn"):
        logging.getLogger(name).addFilter(filt)
