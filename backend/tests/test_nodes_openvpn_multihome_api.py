"""Panel API helpers for OpenVPN multihome toggle (mocked adapter)."""

from unittest.mock import MagicMock

from app.schemas import NodeOpenVpnMultihomeBody, NodeOpenVpnMultihomeResponse


def _put_multihome_apply(adapter_factory, enabled: bool) -> tuple[bool | None, list[str]]:
    """Mirror PUT handler apply path: ensure + collect warnings / on_disk."""
    warnings: list[str] = []
    on_disk: bool | None = None
    try:
        adapter = adapter_factory()
        result = adapter.ensure_openvpn_multihome(enabled)
        if isinstance(result, dict):
            if "on_disk" in result:
                on_disk = bool(result.get("on_disk"))
            if result.get("success") is False:
                warnings.append("ensure_openvpn_multihome вернул success=false")
    except Exception as exc:  # noqa: BLE001
        detail = getattr(exc, "detail", None) or str(exc)
        warnings.append(f"Флаг сохранён, но применить на узле не удалось: {detail}")
    return on_disk, warnings


def test_put_calls_ensure():
    adapter = MagicMock()
    adapter.ensure_openvpn_multihome.return_value = {
        "success": True,
        "on_disk": True,
        "enabled": True,
    }
    on_disk, warnings = _put_multihome_apply(lambda: adapter, True)
    adapter.ensure_openvpn_multihome.assert_called_once_with(True)
    assert on_disk is True
    assert warnings == []


def test_put_ensure_failure_yields_warning():
    adapter = MagicMock()
    adapter.ensure_openvpn_multihome.side_effect = RuntimeError("agent down")
    on_disk, warnings = _put_multihome_apply(lambda: adapter, False)
    assert on_disk is None
    assert warnings and "agent down" in warnings[0]


def test_response_schema_defaults():
    body = NodeOpenVpnMultihomeBody()
    assert body.enabled is False
    resp = NodeOpenVpnMultihomeResponse(enabled=True)
    assert resp.on_disk is None
    assert resp.warnings == []
