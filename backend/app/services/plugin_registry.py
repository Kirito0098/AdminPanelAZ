"""Minimal hook registry for optional extensions (notify backends, etc.)."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

HookHandler = Callable[..., Any]


class HookRegistry:
    def __init__(self) -> None:
        self._hooks: dict[str, list[tuple[str, HookHandler]]] = defaultdict(list)

    def register(self, hook_point: str, name: str, handler: HookHandler) -> None:
        handlers = self._hooks[hook_point]
        if any(existing_name == name for existing_name, _ in handlers):
            raise ValueError(f"Hook {hook_point!r}/{name!r} already registered")
        handlers.append((name, handler))

    def list_handlers(self, hook_point: str) -> list[str]:
        return [name for name, _ in self._hooks.get(hook_point, [])]

    def call(self, hook_point: str, **kwargs: Any) -> None:
        for name, handler in self._hooks.get(hook_point, []):
            try:
                handler(**kwargs)
            except Exception:
                logger.warning("Hook %s/%s failed", hook_point, name, exc_info=True)

    def clear(self, hook_point: str | None = None) -> None:
        if hook_point is None:
            self._hooks.clear()
        else:
            self._hooks.pop(hook_point, None)


hook_registry = HookRegistry()
