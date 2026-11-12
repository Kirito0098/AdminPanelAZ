"""Telegram Mini App API + static React UI."""

from __future__ import annotations

from fastapi import APIRouter

from app.auth import create_access_token, create_tg_mini_token
from app.services.admin_notify import admin_notify_service
from app.services.feature_guards import get_feature_service
from app.services.ip_restriction import ip_restriction_service
from app.services.notify_time import get_client_timezone_from_request

from .auth import router as auth_router
from .auth import tg_auth
from .configs import mini_config_files, mini_configs, mini_send_config, router as configs_router
from .me_configs import router as me_configs_router
from .me_portal import router as me_portal_router
from .me_redeem import router as me_redeem_router
from .messages import router as messages_router
from .helpers import (
    SendConfigV2Request,
    TelegramAuthRequest,
    _STATIC_DIR,
    _get_accessible_config,
    _get_bot_token,
    _get_setting,
    _get_tg_node_or_404,
    _send_config_file,
    _serialize_tg_node,
    _set_setting,
    _static_index,
    _verify_telegram_init_data,
    settings,
)
from .nodes import mini_activate_node, mini_list_nodes, router as nodes_router
from .public import mini_public_config, router as public_router
from .settings import (
    mini_get_admin_notify,
    mini_get_telegram_settings,
    mini_settings,
    mini_test_admin_notify,
    mini_test_telegram,
    mini_update_admin_notify,
    mini_update_telegram_settings,
    router as settings_router,
)
from .static import mini_app_asset, mini_app_page

router = APIRouter(prefix="/tg-mini", tags=["tg-mini"])
router.include_router(nodes_router)
router.include_router(auth_router)
router.include_router(configs_router)
router.include_router(me_configs_router)
router.include_router(me_portal_router)
router.include_router(me_redeem_router)
router.include_router(messages_router)
router.include_router(settings_router)
router.include_router(public_router)
router.add_api_route("/assets/{file_path:path}", mini_app_asset, include_in_schema=False, methods=["GET"])
router.add_api_route("", mini_app_page, methods=["GET"])

__all__ = [
    "SendConfigV2Request",
    "TelegramAuthRequest",
    "_STATIC_DIR",
    "_get_accessible_config",
    "_get_bot_token",
    "_get_setting",
    "_get_tg_node_or_404",
    "_send_config_file",
    "_serialize_tg_node",
    "_set_setting",
    "_static_index",
    "_verify_telegram_init_data",
    "admin_notify_service",
    "create_access_token",
    "create_tg_mini_token",
    "get_client_timezone_from_request",
    "get_feature_service",
    "ip_restriction_service",
    "mini_activate_node",
    "mini_app_asset",
    "mini_app_page",
    "mini_config_files",
    "mini_configs",
    "me_configs_router",
    "mini_get_admin_notify",
    "mini_get_telegram_settings",
    "mini_list_nodes",
    "mini_public_config",
    "mini_send_config",
    "mini_settings",
    "mini_test_admin_notify",
    "mini_test_telegram",
    "mini_update_admin_notify",
    "mini_update_telegram_settings",
    "messages_router",
    "router",
    "settings",
    "tg_auth",
]
