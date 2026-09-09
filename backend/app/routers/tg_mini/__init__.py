"""Telegram Mini App API + static React UI."""

from __future__ import annotations

from fastapi import APIRouter

from app.auth import create_access_token
from app.services.admin_notify import admin_notify_service
from app.services.feature_guards import get_feature_service
from app.services.ip_restriction import ip_restriction_service
from app.services.notify_time import get_client_timezone_from_request

from .auth import router as auth_router
from .auth import tg_auth
from .configs import mini_config_files, mini_configs, mini_qr_link, mini_send_config, router as configs_router
from .dashboard import mini_dashboard, router as dashboard_router
from .helpers import (
    SendConfigV2Request,
    TelegramAuthRequest,
    _STATIC_DIR,
    _get_accessible_config,
    _get_bot_token,
    _get_setting,
    _get_tg_node_or_404,
    _qr_download_service,
    _send_config_file,
    _serialize_tg_node,
    _set_setting,
    _static_index,
    _verify_telegram_init_data,
    settings,
)
from .nodes import mini_activate_node, mini_get_node, mini_list_nodes, mini_node_health, router as nodes_router
from .settings import (
    check_bot_delivery,
    mini_get_admin_notify,
    mini_get_telegram_settings,
    mini_settings,
    mini_test_admin_notify,
    mini_test_telegram,
    mini_update_admin_notify,
    mini_update_telegram_settings,
    mini_visible_vpn_profiles,
    router as settings_router,
)
from .static import mini_app_asset, mini_app_page
from .status import mini_awg2_status, mini_cidr_status, mini_warper_status, router as status_router

router = APIRouter(prefix="/tg-mini", tags=["tg-mini"])
router.include_router(nodes_router)
router.include_router(status_router)
router.include_router(auth_router)
router.include_router(dashboard_router)
router.include_router(configs_router)
router.include_router(settings_router)
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
    "_qr_download_service",
    "_send_config_file",
    "_serialize_tg_node",
    "_set_setting",
    "_static_index",
    "_verify_telegram_init_data",
    "admin_notify_service",
    "check_bot_delivery",
    "create_access_token",
    "get_client_timezone_from_request",
    "get_feature_service",
    "ip_restriction_service",
    "mini_activate_node",
    "mini_app_asset",
    "mini_app_page",
    "mini_awg2_status",
    "mini_cidr_status",
    "mini_config_files",
    "mini_configs",
    "mini_dashboard",
    "mini_get_admin_notify",
    "mini_get_node",
    "mini_get_telegram_settings",
    "mini_list_nodes",
    "mini_node_health",
    "mini_qr_link",
    "mini_send_config",
    "mini_settings",
    "mini_test_admin_notify",
    "mini_test_telegram",
    "mini_update_admin_notify",
    "mini_update_telegram_settings",
    "mini_visible_vpn_profiles",
    "mini_warper_status",
    "router",
    "settings",
    "tg_auth",
]
