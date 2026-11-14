"""OpenVPN server tuning (duplicate-cn, detailed logs) and the install-state snapshot."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.schemas import (
    OpenVpnDcoUpdate,
    OpenVpnMtuUpdate,
    OpenVpnPatchUpdate,
    OpenVpnProtocolsUpdate,
    OpenVpnTuningStateOut,
    OpenVpnTuningUpdate,
)
from app.services.action_log import log_action
from app.services.node_manager import get_active_adapter, get_active_node, get_adapter_for_node
from app.services.node_sync.groups import (
    find_sync_group_for_primary,
    get_replica_nodes,
    is_auto_sync_enabled,
    require_ha_primary_for_config_ops,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/openvpn-tuning", tags=["openvpn-tuning"])


def _proxy_node_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Выберите VPN-узел: у прокси-узла нет OpenVPN",
    )


_SETUP_TUNING_ENVS = ("OPENVPN_DUPLICATE", "OPENVPN_LOG")


def _setup_tuning_updates(duplicate: bool, logs: bool) -> dict[str, str]:
    """Ключи setup AntiZapret: их читает установщик, поэтому переустановка повторит выбор панели."""
    return {
        "OPENVPN_DUPLICATE": "y" if duplicate else "n",
        "OPENVPN_LOG": "y" if logs else "n",
    }


def _write_setup_tuning(adapter, duplicate: bool, logs: bool) -> list[str]:
    """Best-effort: без записи setup следующий setup.sh вернёт значения по умолчанию."""
    try:
        adapter.update_antizapret_settings(_setup_tuning_updates(duplicate, logs))
    except Exception as exc:  # noqa: BLE001 — конфиги уже изменены, это только страховка на переустановку
        logger.warning("openvpn tuning: setup keys not written: %s", exc)
        return [
            "Ключи OPENVPN_DUPLICATE / OPENVPN_LOG в setup не записаны — "
            "повторный setup.sh вернёт свои значения"
        ]
    return []


def _store_tuning_intent(db: Session, duplicate: bool, logs: bool) -> None:
    """Запомнить выбор панели на активном узле и репликах HA."""
    active = get_active_node(db)
    active.openvpn_duplicate_cn = bool(duplicate)
    active.openvpn_detailed_logs = bool(logs)
    group = find_sync_group_for_primary(db, active.id)
    if group is not None and is_auto_sync_enabled(group):
        for replica in get_replica_nodes(db, group):
            replica.openvpn_duplicate_cn = bool(duplicate)
            replica.openvpn_detailed_logs = bool(logs)
    db.commit()


def _resolved(desired_duplicate, desired_logs, state: dict) -> tuple[bool, bool]:
    """Желаемое значение: намерение панели, иначе то, что уже лежит в конфиге."""
    duplicate = desired_duplicate
    if duplicate is None:
        duplicate = state.get("duplicate_cn") == "on"
    logs = desired_logs
    if logs is None:
        logs = state.get("logs") == "on"
    return bool(duplicate), bool(logs)


def _intent_fields(node, state: dict) -> dict:
    duplicate_desired = node.openvpn_duplicate_cn
    logs_desired = node.openvpn_detailed_logs
    in_sync = True
    if duplicate_desired is not None:
        in_sync = in_sync and state.get("duplicate_cn") == ("on" if duplicate_desired else "off")
    if logs_desired is not None:
        in_sync = in_sync and state.get("logs") == ("on" if logs_desired else "off")
    return {
        "duplicate_cn_desired": duplicate_desired,
        "logs_desired": logs_desired,
        "in_sync": in_sync,
    }


def _restore_tuning(adapter, node, state: dict) -> dict:
    """setup.sh / обновление AntiZapret вернули стоковые conf — вернуть выбор панели."""
    duplicate, logs = _resolved(node.openvpn_duplicate_cn, node.openvpn_detailed_logs, state)
    adapter.apply_openvpn_tuning(duplicate=duplicate, logs=logs)
    return adapter.get_openvpn_tuning()


@router.get("", response_model=OpenVpnTuningStateOut)
def get_openvpn_tuning(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    try:
        state = adapter.get_openvpn_tuning()
    except NotImplementedError as exc:
        raise _proxy_node_error() from exc
    if not _intent_fields(node, state)["in_sync"]:
        try:
            state = _restore_tuning(adapter, node, state)
        except Exception as exc:  # noqa: BLE001 — состояние показываем как есть, с предупреждением
            logger.warning("openvpn tuning self-heal failed: %s", exc)
            state = {
                **state,
                "warnings": [
                    *(state.get("warnings") or []),
                    f"Выбор панели не удалось вернуть на диск: {exc}. Нажмите «Сохранить» ещё раз.",
                ],
            }
    return OpenVpnTuningStateOut(**{**state, **_intent_fields(node, state)})


@router.put("", response_model=OpenVpnTuningStateOut)
def apply_openvpn_tuning(
    payload: OpenVpnTuningUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    require_ha_primary_for_config_ops(db)
    adapter = get_active_adapter(db)
    try:
        result = adapter.apply_openvpn_tuning(duplicate=payload.duplicate, logs=payload.logs)
    except NotImplementedError as exc:
        raise _proxy_node_error() from exc

    result["warnings"] = [
        *(result.get("warnings") or []),
        *_write_setup_tuning(get_active_adapter(db), payload.duplicate, payload.logs),
        *_replicate_to_replicas(
            db,
            lambda adapter: (
                adapter.apply_openvpn_tuning(duplicate=payload.duplicate, logs=payload.logs),
                adapter.update_antizapret_settings(
                    _setup_tuning_updates(payload.duplicate, payload.logs)
                ),
            ),
        ),
    ]
    _store_tuning_intent(db, payload.duplicate, payload.logs)
    log_action(
        db,
        action="openvpn_tuning",
        user_id=current_user.id,
        username=current_user.username,
        details=(
            f"duplicate={payload.duplicate};logs={payload.logs};"
            f"restarted={','.join(result.get('restarted') or [])}"
        ),
    )
    return OpenVpnTuningStateOut(**result)


def _replicate_to_replicas(db: Session, apply_to_replica) -> list[str]:
    """Применить то же изменение на репликах HA: server conf у каждого узла свой."""
    from app.services.node_manager import get_active_node

    group = find_sync_group_for_primary(db, get_active_node(db).id)
    if group is None or not is_auto_sync_enabled(group):
        return []
    warnings: list[str] = []
    for replica in get_replica_nodes(db, group):
        try:
            apply_to_replica(get_adapter_for_node(replica))
        except HTTPException as exc:
            warnings.append(f"Реплика «{replica.name}»: {exc.detail}")
        except Exception as exc:  # best-effort: одна реплика не должна ломать ответ панели
            logger.warning("openvpn tuning: реплика %s (%s): %s", replica.id, replica.name, exc)
            warnings.append(f"Реплика «{replica.name}»: {exc}")
    return warnings


@router.put("/mtu", response_model=OpenVpnTuningStateOut)
def apply_mtu(
    payload: OpenVpnMtuUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    require_ha_primary_for_config_ops(db)
    try:
        result = get_active_adapter(db).apply_mtu(
            openvpn_mtu=payload.openvpn, wireguard_mtu=payload.wireguard
        )
    except NotImplementedError as exc:
        raise _proxy_node_error() from exc

    result["warnings"] = [
        *(result.get("warnings") or []),
        *_replicate_to_replicas(
            db,
            lambda adapter: adapter.apply_mtu(openvpn_mtu=payload.openvpn, wireguard_mtu=payload.wireguard),
        ),
    ]
    log_action(
        db,
        action="openvpn_mtu",
        user_id=current_user.id,
        username=current_user.username,
        details=(
            f"openvpn={payload.openvpn or '—'};wireguard={payload.wireguard or '—'};"
            f"restarted={','.join(result.get('restarted') or [])}"
        ),
    )
    return OpenVpnTuningStateOut(**result)


@router.put("/dco", response_model=OpenVpnTuningStateOut)
def apply_dco(
    payload: OpenVpnDcoUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    require_ha_primary_for_config_ops(db)
    try:
        result = get_active_adapter(db).apply_dco(payload.enabled)
    except NotImplementedError as exc:
        raise _proxy_node_error() from exc

    result["warnings"] = [
        *(result.get("warnings") or []),
        *_replicate_to_replicas(db, lambda adapter: adapter.apply_dco(payload.enabled)),
    ]
    log_action(
        db,
        action="openvpn_dco",
        user_id=current_user.id,
        username=current_user.username,
        details=f"enabled={payload.enabled};restarted={','.join(result.get('restarted') or [])}",
    )
    return OpenVpnTuningStateOut(**result)


@router.put("/protocols", response_model=OpenVpnTuningStateOut)
def apply_protocols(
    payload: OpenVpnProtocolsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    require_ha_primary_for_config_ops(db)
    try:
        result = get_active_adapter(db).apply_protocols(payload.units)
    except NotImplementedError as exc:
        raise _proxy_node_error() from exc

    log_action(
        db,
        action="openvpn_protocols",
        user_id=current_user.id,
        username=current_user.username,
        details=";".join(f"{unit}={enabled}" for unit, enabled in payload.units.items()),
    )
    return OpenVpnTuningStateOut(**result)


@router.post("/patch", response_model=OpenVpnTuningStateOut)
def apply_openvpn_patch(
    payload: OpenVpnPatchUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    require_ha_primary_for_config_ops(db)
    try:
        result = get_active_adapter(db).apply_openvpn_patch(payload.algorithm)
    except NotImplementedError as exc:
        raise _proxy_node_error() from exc

    log_action(
        db,
        action="openvpn_patch",
        user_id=current_user.id,
        username=current_user.username,
        details=f"algorithm={payload.algorithm}",
    )
    return OpenVpnTuningStateOut(**result)
