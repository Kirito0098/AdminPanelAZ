"""Import smoke: uvicorn runs ``app.main:app``, so a broken import anywhere in the
import chain kills the process and nginx answers 502 for every request."""

from __future__ import annotations

import importlib


def test_app_main_imports_and_tg_mini_reexports_used_helpers() -> None:
    main = importlib.import_module("app.main")

    assert main.app is not None

    # Модули tg_mini вызывают эти хелперы через `root.*`, поэтому пакет обязан их
    # реэкспортировать: удаление импорта из helpers.py ломало старт панели (502).
    tg_mini = importlib.import_module("app.routers.tg_mini")
    for name in ("_get_setting", "_set_setting"):
        assert callable(getattr(tg_mini, name)), f"app.routers.tg_mini.{name} is used through root.*"
