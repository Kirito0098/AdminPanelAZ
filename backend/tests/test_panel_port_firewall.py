"""iptables whitelist for panel port (BACKEND_PORT)."""

from unittest.mock import patch

from app.services.panel_port_firewall import (
    CHAIN_V4,
    COMMENT_JUMP_V4,
    IPSET_ALLOW_V4,
    PanelPortFirewall,
)


def test_sync_dry_run_accepts_entries():
    fw = PanelPortFirewall(firewall_enabled=True, dry_run=True)
    assert fw.sync(["10.0.0.1", "192.168.0.0/24"], port=8000)
    assert fw._active_port == 8000


def test_disable_dry_run():
    fw = PanelPortFirewall(dry_run=True)
    fw.sync(["10.0.0.1"], port=8000)
    assert fw.disable()


@patch.object(PanelPortFirewall, "_run_command", return_value=(True, ""))
def test_sync_calls_ipset_and_jump(run_mock):
    fw = PanelPortFirewall(firewall_enabled=True, dry_run=False)
    assert fw.sync(["203.0.113.10", "10.0.0.0/8"], port=8000)

    args_list = [call.args[0] for call in run_mock.call_args_list]
    joined = [" ".join(args) for args in args_list]
    assert any("ipset" in line and IPSET_ALLOW_V4 in line for line in joined)
    assert any(CHAIN_V4 in line for line in joined)
    assert any(COMMENT_JUMP_V4 in line for line in joined)
    assert any("--dport" in line and "8000" in line for line in joined)


def test_ipv6_entries_ignored():
    fw = PanelPortFirewall(dry_run=True)
    entries = fw._ipv4_entries(["10.0.0.1", "2001:db8::1"])
    assert entries == ["10.0.0.1/32"]


@patch.object(PanelPortFirewall, "_run_command", return_value=(True, ""))
def test_sync_does_not_create_ipv6_chain(run_mock):
    fw = PanelPortFirewall(firewall_enabled=True, dry_run=False)
    fw.sync(["10.0.0.1", "2001:db8::1"], port=8000)
    args_list = [call.args[0] for call in run_mock.call_args_list]
    joined = [" ".join(args) for args in args_list]
    assert not any("ip6tables" in line and " -N " in line for line in joined)
    assert not any("aa-panel-port-jump-v6" in line for line in joined)
