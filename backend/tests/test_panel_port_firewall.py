from app.services.panel_port_firewall import CHAIN_V4, COMMENT_JUMP_V4, IPSET_ALLOW_V4, PanelPortFirewall


def test_sync_fails_without_drop_when_allow_rule_not_added(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(args: list[str]) -> tuple[bool, str]:
        calls.append(args)
        if args[:3] == ["iptables", "-A", CHAIN_V4] and args[-1] == "RETURN":
            return False, "iptables: Resource temporarily unavailable"
        if args[:2] == ["iptables", "-C"]:
            return False, ""
        return True, ""

    monkeypatch.setattr(PanelPortFirewall, "_run_command", staticmethod(fake_run))
    fw = PanelPortFirewall(firewall_enabled=True, dry_run=False)

    assert fw.sync(["203.0.113.5"], port=8000) is False
    assert ["iptables", "-A", CHAIN_V4, "-j", "DROP"] not in calls
    assert not any(c[:3] == ["iptables", "-I", "INPUT"] for c in calls)


def test_disable_keeps_ipset_when_jump_not_removed(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(args: list[str]) -> tuple[bool, str]:
        calls.append(args)
        if args == ["iptables", "-S", "INPUT"]:
            return True, f"-A INPUT -p tcp --dport 8000 -m comment --comment {COMMENT_JUMP_V4} -j {CHAIN_V4}"
        if args[:3] == ["iptables", "-D", "INPUT"]:
            return False, "iptables: Resource temporarily unavailable"
        return True, ""

    monkeypatch.setattr(PanelPortFirewall, "_run_command", staticmethod(fake_run))
    fw = PanelPortFirewall(firewall_enabled=True, dry_run=False)

    assert fw.disable(port=8000) is False
    assert ["ipset", "flush", IPSET_ALLOW_V4] not in calls
