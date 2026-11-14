"""Access-log filter must mask tokens without breaking uvicorn's AccessFormatter."""

from __future__ import annotations

import logging

from uvicorn.logging import AccessFormatter

from app.services.access_log_privacy import TokenPathAccessLogFilter


def _access_record(full_path: str) -> logging.LogRecord:
    """A record shaped exactly like uvicorn.access emits it."""
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=(("203.0.113.7", 4242), "GET", full_path, "1.1", 200),
        exc_info=None,
    )


def test_filter_masks_token_and_keeps_access_formatter_working():
    formatter = AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False)
    filt = TokenPathAccessLogFilter()

    token_record = _access_record("/p/secret-token")
    filt.filter(token_record)
    line = formatter.format(token_record)

    assert "/p/***" in line
    assert "secret-token" not in line

    plain_record = _access_record("/api/health")
    filt.filter(plain_record)
    assert "GET /api/health HTTP/1.1" in formatter.format(plain_record)
