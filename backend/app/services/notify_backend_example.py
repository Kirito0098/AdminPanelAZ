"""Example notify backend — demonstrates register_notify_backend usage."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def example_logging_notify_backend(
    *,
    event_type: str,
    text: str,
    recipients,
    **kwargs,
) -> None:
    logger.info(
        "Example notify backend: event=%s recipients=%d chars=%d",
        event_type,
        len(recipients),
        len(text),
    )
