from app.services.openvpn_multihome import (
    apply_multihome_to_conf,
    conf_has_bare_multihome,
    maybe_ensure_openvpn_multihome,
    maybe_ensure_node_openvpn_multihome,
    node_wants_openvpn_multihome,
)

SAMPLE = """port 1194
proto udp
dev tun
server 10.28.0.0 255.255.255.0
keepalive 10 60
"""


def test_apply_inserts_after_proto():
    out = apply_multihome_to_conf(SAMPLE, True)
    assert "proto udp\nmultihome\n" in out
    assert conf_has_bare_multihome(out)


def test_apply_remove():
    with_mh = apply_multihome_to_conf(SAMPLE, True)
    out = apply_multihome_to_conf(with_mh, False)
    assert not conf_has_bare_multihome(out)
    assert "proto udp\n" in out
    assert "multihome" not in out


def test_apply_idempotent():
    once = apply_multihome_to_conf(SAMPLE, True)
    twice = apply_multihome_to_conf(once, True)
    assert once == twice
    assert twice.count("multihome") == 1


def test_apply_no_proto_appends():
    body = "dev tun\n"
    out = apply_multihome_to_conf(body, True)
    assert out.endswith("multihome\n")
    assert conf_has_bare_multihome(out)


def test_apply_ignores_commented_multihome_when_enabling():
    body = "proto tcp\n# multihome\n"
    out = apply_multihome_to_conf(body, True)
    assert "proto tcp\nmultihome\n" in out
    assert "# multihome" in out


def test_maybe_ensure_skips_when_disabled():
    class _Adapter:
        def ensure_openvpn_multihome(self, enabled: bool):
            raise AssertionError("should not be called")

    assert maybe_ensure_openvpn_multihome(_Adapter(), enabled=False) is None


def test_maybe_ensure_calls_adapter_when_enabled():
    class _Adapter:
        def __init__(self):
            self.calls: list[bool] = []

        def ensure_openvpn_multihome(self, enabled: bool):
            self.calls.append(enabled)
            return {"success": True, "enabled": enabled}

    adapter = _Adapter()
    result = maybe_ensure_openvpn_multihome(adapter, enabled=True)
    assert result == {"success": True, "enabled": True}
    assert adapter.calls == [True]


def test_maybe_ensure_node_uses_flag():
    class _Node:
        openvpn_multihome = True

    class _Adapter:
        def ensure_openvpn_multihome(self, enabled: bool):
            return {"ok": enabled}

    assert node_wants_openvpn_multihome(_Node()) is True
    assert maybe_ensure_node_openvpn_multihome(_Adapter(), _Node()) == {"ok": True}
