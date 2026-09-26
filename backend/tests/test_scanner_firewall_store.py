"""Scanner bans reach ipset/iptables; the firewall itself is simulated."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from app.services import scanner_firewall_store as store_module
from app.services import site_diagnostics
from app.services.scanner_firewall_store import IPSET_V4, IPSET_V6, ScannerFirewallStore, check_scanner_firewall


class _FakeFirewall:
    """Just enough ipset/iptables semantics to catch the failures seen on real hosts."""

    def __init__(self):
        self.sets: dict[str, dict] = {}
        self.rules: set[tuple[str, str]] = set()
        self.calls: list[list[str]] = []

    def legacy_set(self, name: str, family: str) -> None:
        self.sets[name] = {"family": family, "timeout": False, "entries": {}}

    def __call__(self, args, timeout=None):
        self.calls.append(list(args))
        tool, *rest = args
        handler = self._ipset if tool == "ipset" else self._iptables
        rc, out = handler(tool, rest)
        return subprocess.CompletedProcess(args, rc, out if rc == 0 else "", "" if rc == 0 else out)

    def _ipset(self, _tool, rest):
        cmd, name = rest[0], rest[1] if len(rest) > 1 else ""
        if cmd == "list":
            name = rest[2]
            if name not in self.sets:
                return 1, "The set with the given name does not exist"
            item = self.sets[name]
            header = f"family {item['family']} hashsize 4096 maxelem 65536"
            if item["timeout"]:
                header += " timeout 0"
            return 0, f"Name: {name}\nType: hash:ip\nHeader: {header} bucketsize 12\n"
        if cmd == "create":
            family = rest[rest.index("family") + 1]
            has_timeout = "timeout" in rest
            if name in self.sets:
                same = self.sets[name]["timeout"] == has_timeout and self.sets[name]["family"] == family
                return (0, "") if "-exist" in rest and same else (1, "set with the same name already exists")
            self.sets[name] = {"family": family, "timeout": has_timeout, "entries": {}}
            return 0, ""
        if cmd == "destroy":
            if name not in self.sets:
                return 1, "does not exist"
            if any(rule_set == name for _, rule_set in self.rules):
                return 1, "Set cannot be destroyed: it is in use by a kernel component"
            del self.sets[name]
            return 0, ""
        if cmd == "swap":
            other = rest[2]
            self.sets[name], self.sets[other] = self.sets[other], self.sets[name]
            return 0, ""
        if cmd == "add":
            item = self.sets.get(name)
            if item is None:
                return 1, "does not exist"
            if "timeout" in rest and not item["timeout"]:
                return 1, "Timeout cannot be used: set was created without timeout support"
            item["entries"][rest[2]] = int(rest[rest.index("timeout") + 1]) if "timeout" in rest else 0
            return 0, ""
        if cmd == "del":
            self.sets.get(name, {}).get("entries", {}).pop(rest[2], None)
            return 0, ""
        return 1, f"unexpected ipset {rest}"

    def _iptables(self, tool, rest):
        action, name = rest[0], rest[rest.index("--match-set") + 1]
        if action == "-C":
            return (0, "") if (tool, name) in self.rules else (1, "Bad rule")
        if action == "-I":
            wanted = "inet" if tool == "iptables" else "inet6"
            if name not in self.sets or self.sets[name]["family"] != wanted:
                return 2, f"The protocol family of set {name} is not applicable."
            self.rules.add((tool, name))
            return 0, ""
        return 1, f"unexpected {tool} {rest}"


@pytest.fixture
def firewall():
    return _FakeFirewall()


@pytest.fixture
def make_store(tmp_path, firewall):
    def make(**kwargs):
        kwargs.setdefault("firewall_enabled", True)
        kwargs.setdefault("dry_run", False)
        kwargs.setdefault("excluded_networks", lambda: [])
        return ScannerFirewallStore(tmp_path / "scanner_blocks.json", runner=firewall, **kwargs)

    return make


def test_fresh_host_gets_timeout_sets_and_a_rule_per_family(make_store, firewall):
    assert make_store().ensure_firewall_infrastructure() is True

    assert firewall.sets[IPSET_V4]["timeout"] and firewall.sets[IPSET_V4]["family"] == "inet"
    assert firewall.sets[IPSET_V6]["timeout"] and firewall.sets[IPSET_V6]["family"] == "inet6"
    assert firewall.rules == {("iptables", IPSET_V4), ("ip6tables", IPSET_V6)}


def test_ensure_is_idempotent(make_store, firewall):
    store = make_store()
    store.ensure_firewall_infrastructure()
    firewall.calls.clear()

    store.ensure_firewall_infrastructure()

    assert not [c for c in firewall.calls if c[1] in ("create", "swap", "-I")]


def test_legacy_sets_without_timeout_are_replaced_in_place(make_store, firewall):
    firewall.legacy_set(IPSET_V4, "inet")
    firewall.legacy_set(IPSET_V6, "inet6")
    firewall.rules.add(("iptables", IPSET_V4))
    firewall.sets[f"{IPSET_V4}_tmp"] = {"family": "inet", "timeout": False, "entries": {}}

    make_store().ensure_firewall_infrastructure()

    assert firewall.sets[IPSET_V4]["timeout"] and firewall.sets[IPSET_V6]["timeout"]
    assert firewall.rules == {("iptables", IPSET_V4), ("ip6tables", IPSET_V6)}
    assert set(firewall.sets) == {IPSET_V4, IPSET_V6}


@pytest.mark.parametrize(("ip", "ipset_name"), [("203.0.113.9", None), ("8.8.4.4", IPSET_V4), ("2a00:1450::1", IPSET_V6)])
def test_ban_reaches_the_firewall_with_a_timeout(make_store, firewall, ip, ipset_name):
    firewall.legacy_set(IPSET_V4, "inet")
    store = make_store()

    ban = store.register_ban(ip, reason="rate_limit", short_ban_seconds=600, now=1000.0)

    assert store.is_banned(ip, now=1001.0)
    if ipset_name is None:
        assert ban["firewall"] is False
        assert not any(ip in item["entries"] for item in firewall.sets.values())
    else:
        assert ban["firewall"] is True
        assert firewall.sets[ipset_name]["entries"] == {ip: 600}


@pytest.mark.parametrize(
    "ip",
    ["127.0.0.1", "::1", "10.29.0.5", "192.168.1.2", "172.16.0.1", "100.64.0.1", "fe80::1", "fd00::1", "0.0.0.0"],
)
def test_non_public_addresses_are_banned_in_the_panel_only(make_store, firewall, ip):
    store = make_store()

    ban = store.register_ban(ip, reason="rate_limit", short_ban_seconds=600, now=1000.0)

    assert store.is_banned(ip, now=1001.0)
    assert ban["firewall"] is False
    assert not [c for c in firewall.calls if c[:2] == ["ipset", "add"]]


def test_trusted_proxies_and_cloudflare_are_never_dropped(make_store, firewall, monkeypatch):
    monkeypatch.setattr(store_module, "_trusted_proxy_ips", lambda: {"8.8.8.8"})
    store = make_store(excluded_networks=lambda: [store_module.ipaddress.ip_network("104.16.0.0/13")])

    for ip in ("8.8.8.8", "104.18.3.4"):
        assert store.register_ban(ip, reason="rate_limit", short_ban_seconds=600, now=1000.0)["firewall"] is False
    assert store.register_ban("1.1.1.1", reason="rate_limit", short_ban_seconds=600, now=1000.0)["firewall"] is True

    assert firewall.sets[IPSET_V4]["entries"] == {"1.1.1.1": 600}


def test_cloudflare_ranges_are_read_from_the_realip_snippet(tmp_path, monkeypatch):
    (tmp_path / "cloudflare-realip.conf").write_text(
        "# Cloudflare\nset_real_ip_from 173.245.48.0/20;\nset_real_ip_from 2400:cb00::/32;\nreal_ip_header CF-Connecting-IP;\n"
    )
    monkeypatch.setenv("NGINX_SNIPPETS_DIR", str(tmp_path))

    assert [str(n) for n in store_module.cloudflare_networks()] == ["173.245.48.0/20", "2400:cb00::/32"]

    monkeypatch.setenv("NGINX_SNIPPETS_DIR", str(tmp_path / "missing"))
    assert store_module.cloudflare_networks() == []


def test_sync_restores_active_bans_after_migration(tmp_path, make_store, firewall, monkeypatch):
    monkeypatch.setattr(store_module.time, "time", lambda: 1000.0)
    store = make_store()
    store.register_ban("8.8.4.4", reason="rate_limit", short_ban_seconds=600, now=1000.0)
    store.register_ban("9.9.9.9", reason="rate_limit", short_ban_seconds=60, now=100.0)
    fresh = _FakeFirewall()
    fresh.legacy_set(IPSET_V4, "inet")
    restarted = ScannerFirewallStore(
        tmp_path / "scanner_blocks.json", runner=fresh, firewall_enabled=True, dry_run=False, excluded_networks=lambda: []
    )
    monkeypatch.setattr(store_module.time, "time", lambda: 1100.0)

    restarted.sync_firewall_from_store()

    assert fresh.sets[IPSET_V4]["entries"] == {"8.8.4.4": 500}


@pytest.mark.parametrize("options", [{"firewall_enabled": False}, {"dry_run": True}])
def test_disabled_or_dry_run_runs_no_commands(make_store, firewall, options):
    store = make_store(**options)

    store.ensure_firewall_infrastructure()
    store.register_ban("8.8.4.4", reason="rate_limit", short_ban_seconds=600, now=1000.0)

    assert firewall.calls == []


def test_health_reports_a_ready_firewall(make_store, firewall):
    make_store().ensure_firewall_infrastructure()

    assert check_scanner_firewall(run_cmd=firewall) == []


def test_health_reports_what_blocks_bans(firewall):
    firewall.legacy_set(IPSET_V4, "inet")
    firewall.rules.add(("iptables", IPSET_V4))

    issues = check_scanner_firewall(run_cmd=firewall)

    assert issues == [
        f"набор {IPSET_V4} создан без поддержки timeout — баны в него не добавляются",
        f"набор {IPSET_V6} не создан",
        f"нет правила ip6tables INPUT DROP для {IPSET_V6}",
    ]


_NETNS_SCRIPT = r"""
import subprocess, sys
from app.services.scanner_firewall_store import IPSET_V4, IPSET_V6, ScannerFirewallStore, check_scanner_firewall

run = lambda *args: subprocess.run(list(args), capture_output=True, text=True)
run("ipset", "create", IPSET_V4, "hash:ip", "family", "inet", "hashsize", "4096", "maxelem", "65536")
run("iptables", "-I", "INPUT", "-m", "set", "--match-set", IPSET_V4, "src", "-j", "DROP")
store = ScannerFirewallStore(sys.argv[1], firewall_enabled=True, dry_run=False, excluded_networks=lambda: [])
assert check_scanner_firewall()[0].endswith("баны в него не добавляются")
assert store.register_ban("8.8.4.4", reason="t", short_ban_seconds=600)["firewall"] is True
assert store.register_ban("2a00:1450::1", reason="t", short_ban_seconds=600)["firewall"] is True
assert check_scanner_firewall() == [], check_scanner_firewall()
assert "8.8.4.4 timeout" in run("ipset", "list", IPSET_V4).stdout
assert "2a00:1450::1 timeout" in run("ipset", "list", IPSET_V6).stdout
assert run("iptables", "-S", "INPUT").stdout.count(IPSET_V4) == 1
assert IPSET_V6 in run("ip6tables", "-S", "INPUT").stdout
print("NETNS-OK")
"""


def test_real_ipset_and_iptables_in_an_isolated_network_namespace(tmp_path):
    import os
    import shutil
    import sys

    if os.geteuid() != 0 or not all(shutil.which(tool) for tool in ("unshare", "ipset", "iptables", "ip6tables")):
        pytest.skip("needs root, unshare, ipset and iptables")
    backend_root = store_module.Path(store_module.__file__).resolve().parents[2]
    result = subprocess.run(
        ["unshare", "--net", sys.executable, "-c", _NETNS_SCRIPT, str(tmp_path / "blocks.json")],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=backend_root,
        env={**os.environ, "PYTHONPATH": str(backend_root)},
    )

    assert "NETNS-OK" in result.stdout, result.stdout + result.stderr


def _ready_tools():
    return SimpleNamespace(fully_ready=True, operational_detail="iptables и ipset отвечают")


def test_diagnostics_warns_when_scanner_bans_cannot_work(monkeypatch, firewall):
    firewall.legacy_set(IPSET_V4, "inet")
    monkeypatch.setattr(site_diagnostics, "check_firewall_tools", lambda run_cmd: _ready_tools())
    report = SimpleNamespace(results=[], current_category="firewall")
    monkeypatch.setattr(site_diagnostics, "_append_result", lambda rep, result: rep.results.append(result))

    site_diagnostics._check_firewall_tools(report, firewall)

    assert [r.status for r in report.results] == ["ok", "warn"]
    assert report.results[1].title == "Баны сканеров в firewall"
    assert "без поддержки timeout" in report.results[1].detail


def test_diagnostics_confirms_working_scanner_bans(monkeypatch, make_store, firewall):
    make_store().ensure_firewall_infrastructure()
    monkeypatch.setattr(site_diagnostics, "check_firewall_tools", lambda run_cmd: _ready_tools())
    report = SimpleNamespace(results=[], current_category="firewall")
    monkeypatch.setattr(site_diagnostics, "_append_result", lambda rep, result: rep.results.append(result))

    site_diagnostics._check_firewall_tools(report, firewall)

    assert [(r.status, r.title) for r in report.results] == [("ok", "iptables и ipset"), ("ok", "Баны сканеров в firewall")]


@pytest.mark.parametrize("options", [{"firewall_enabled": False}, {"dry_run": True}])
def test_diagnostics_skips_scanner_bans_when_the_firewall_is_off(monkeypatch, firewall, options):
    for name, value in options.items():
        monkeypatch.setattr(store_module.scanner_firewall_store, name, value)
    monkeypatch.setattr(site_diagnostics, "check_firewall_tools", lambda run_cmd: _ready_tools())
    report = SimpleNamespace(results=[], current_category="firewall")
    monkeypatch.setattr(site_diagnostics, "_append_result", lambda rep, result: rep.results.append(result))

    site_diagnostics._check_firewall_tools(report, firewall)

    assert [r.title for r in report.results] == ["iptables и ipset"]
    assert firewall.calls == []
