"""Nginx impact preview: dedicated vhost, subpath snippet, foreign locations, StatusOpenVPN, no nginx."""

from __future__ import annotations

import pytest

from app.services.nginx_impact import build_nginx_impact

PANEL = "panel.arbitrary.test"
PORTAL = "portal.arbitrary.test"


@pytest.fixture(autouse=True)
def nginx_dirs(tmp_path, monkeypatch):
    enabled = tmp_path / "nginx" / "sites-enabled"
    available = tmp_path / "nginx" / "sites-available"
    conf_d = tmp_path / "nginx" / "conf.d"
    for directory in (enabled, available, conf_d):
        directory.mkdir(parents=True)
    monkeypatch.setenv("NGINX_SITES_ENABLED_DIR", str(enabled))
    monkeypatch.setenv("NGINX_SITES_AVAILABLE_DIR", str(available))
    monkeypatch.setenv("NGINX_CONF_D_DIR", str(conf_d))
    monkeypatch.setenv("STATUS_OPENVPN_SETUP", str(tmp_path / "no-status-setup"))
    return {"root": tmp_path, "enabled": enabled, "available": available, "conf_d": conf_d}


def write_vhost(nginx_dirs, name: str, text: str):
    path = nginx_dirs["enabled"] / name
    path.write_text(text, encoding="utf-8")
    return path


def impact(nginx_dirs, panel: str = PANEL, portal: str = "") -> dict:
    return build_nginx_impact(project_root=nginx_dirs["root"], panel_domain=panel, portal_domain=portal)


PANEL_VHOST = """# AdminPanelAZ — Nginx reverse proxy
server {
    listen 443 ssl;
    server_name panel.arbitrary.test;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location ^~ /api/telegram/webhook/ {
        proxy_pass http://127.0.0.1:8000;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
    }
}
"""

STATUS_VHOST = """# Created by StatusOpenVPN
server {
    listen 443 ssl;
    server_name status.arbitrary.test;

    location /status/ {
        proxy_pass http://127.0.0.1:1234;
        proxy_set_header X-Script-Name /status;
    }
}
"""


def test_missing_nginx(nginx_dirs, monkeypatch, tmp_path):
    missing = tmp_path / "missing"
    monkeypatch.setenv("NGINX_SITES_ENABLED_DIR", str(missing / "enabled"))
    monkeypatch.setenv("NGINX_SITES_AVAILABLE_DIR", str(missing / "available"))
    monkeypatch.setenv("NGINX_CONF_D_DIR", str(missing / "conf.d"))

    result = impact(nginx_dirs)

    assert result["nginx_seen"] is False
    assert result["integration_mode"] == "unknown"
    assert result["panel_vhost"] is None
    assert result["vhosts"] == []
    assert result["foreign_locations"] == []
    assert result["global_changes"] == []
    assert result["warnings"] == []
    assert result["status_openvpn"] is None


def test_panel_and_leaf_vhosts_are_parsed(nginx_dirs):
    write_vhost(nginx_dirs, "panel", PANEL_VHOST)
    portal_text = PANEL_VHOST.replace(PANEL, PORTAL).replace("Nginx reverse proxy", "client portal")
    write_vhost(nginx_dirs, "portal", portal_text)
    write_vhost(nginx_dirs, "unrelated", "server {\n    server_name blog.arbitrary.test;\n    location / { return 200; }\n}\n")

    result = impact(nginx_dirs, portal=PORTAL)

    roles = {(row["host"], row["role"]) for row in result["vhosts"]}
    assert (PANEL, "panel") in roles
    assert (PORTAL, "portal") in roles
    assert ("blog.arbitrary.test", "other") in roles
    assert result["integration_mode"] == "dedicated_vhost"
    assert result["panel_vhost"].endswith("sites-enabled/panel")
    assert result["foreign_locations"] == []
    assert result["warnings"] == []


def test_separate_status_subdomain_is_not_foreign(nginx_dirs):
    write_vhost(nginx_dirs, "panel", PANEL_VHOST)
    write_vhost(nginx_dirs, "status", STATUS_VHOST)

    result = impact(nginx_dirs)

    roles = {(row["host"], row["role"]) for row in result["vhosts"]}
    assert (PANEL, "panel") in roles
    assert ("status.arbitrary.test", "statusopenvpn") in roles
    assert result["foreign_locations"] == []
    assert result["warnings"] == []
    status = result["status_openvpn"]
    assert status["detected"] is True
    assert status["in_nginx"] is True
    assert status["outside_nginx"] is False
    assert status["domain"] == "status.arbitrary.test"
    assert status["path"] == "/status/"
    assert "status.arbitrary.test" in status["detail"]


def test_panel_vhost_with_status_location_is_foreign(nginx_dirs):
    write_vhost(
        nginx_dirs,
        "panel",
        PANEL_VHOST.replace(
            "    location / {\n        proxy_pass http://127.0.0.1:8000;",
            "    location /status/ {\n"
            "        proxy_pass http://127.0.0.1:1234;\n"
            "        proxy_set_header X-Script-Name /status;\n"
            "    }\n\n"
            "    location / {\n        proxy_pass http://127.0.0.1:8000;",
        ),
    )

    result = impact(nginx_dirs)

    assert result["integration_mode"] == "dedicated_vhost"
    assert result["foreign_locations"] == [
        {"path": "/status/", "project": "StatusOpenVPN", "target": "http://127.0.0.1:1234"}
    ]
    assert any("/status/" in warning and "StatusOpenVPN" in warning for warning in result["warnings"])
    assert result["status_openvpn"]["in_nginx"] is True
    assert result["status_openvpn"]["outside_nginx"] is False


def test_panel_vhost_status_proxy_by_port_only(nginx_dirs):
    write_vhost(
        nginx_dirs,
        "panel",
        PANEL_VHOST.replace(
            "    location / {",
            "    location /status/ {\n        proxy_pass http://127.0.0.1:1234;\n    }\n\n    location / {",
        ),
    )

    result = impact(nginx_dirs)

    assert [item["project"] for item in result["foreign_locations"]] == ["StatusOpenVPN"]


def test_subpath_snippet_in_status_openvpn_vhost(nginx_dirs):
    write_vhost(
        nginx_dirs,
        "status",
        """# Created by StatusOpenVPN
server {
    listen 443 ssl;
    server_name status.arbitrary.test;

    location /status/ {
        proxy_pass http://127.0.0.1:1234;
        proxy_set_header X-Script-Name /status;
    }

    location /panel/ {
        include snippets/adminpanelaz-arbitrary_test-panel.conf;
    }
}
""",
    )

    result = impact(nginx_dirs, panel="arbitrary.test")

    assert result["integration_mode"] == "subpath_snippet"
    assert result["panel_snippet_includes"] == ["snippets/adminpanelaz-arbitrary_test-panel.conf"]
    assert result["panel_vhost"].endswith("sites-enabled/status")
    assert result["vhosts"][0]["role"] == "statusopenvpn"
    assert all(row["will_change"] is False for row in result["vhosts"])
    assert any("не должен переписывать" in warning for warning in result["warnings"])
    assert any("StatusOpenVPN" in warning for warning in result["warnings"])
    assert result["status_openvpn"]["in_nginx"] is True


def test_subpath_snippet_in_foreign_vhost(nginx_dirs):
    write_vhost(
        nginx_dirs,
        "shared",
        """# Some other project
server {
    listen 443 ssl;
    server_name shared.arbitrary.test;

    location /blog/ {
        proxy_pass http://127.0.0.1:9000;
    }

    location /az/ {
        include snippets/adminpanelaz-shared_arbitrary_test-az.conf;
    }
}
""",
    )

    result = impact(nginx_dirs, panel="shared.arbitrary.test")

    assert result["integration_mode"] == "subpath_snippet"
    assert result["panel_snippet_includes"] == ["snippets/adminpanelaz-shared_arbitrary_test-az.conf"]
    assert result["vhosts"][0]["role"] == "other"
    assert result["vhosts"][0]["same_domain"] is True
    assert result["vhosts"][0]["note"] == "домен панели занят чужим vhost"
    assert result["vhosts"][0]["will_change"] is False
    assert result["foreign_locations"] == []
    assert any("шаг nginx не должен переписывать" in warning for warning in result["warnings"])


def test_sites_available_backups_are_ignored(nginx_dirs):
    write_vhost(nginx_dirs, "panel", PANEL_VHOST)
    (nginx_dirs["available"] / "panel.bak-20260101").write_text(
        PANEL_VHOST.replace("panel.arbitrary.test", "old.arbitrary.test"), encoding="utf-8"
    )

    result = impact(nginx_dirs)

    assert [row["host"] for row in result["vhosts"]] == [PANEL]
    assert result["integration_mode"] == "dedicated_vhost"


def test_http_and_https_blocks_share_one_row(nginx_dirs):
    write_vhost(
        nginx_dirs,
        "panel",
        PANEL_VHOST
        + """server {
    listen 80;
    server_name panel.arbitrary.test;
    location / { return 301 https://$host$request_uri; }
}
""",
    )

    result = impact(nginx_dirs)

    assert [row["host"] for row in result["vhosts"]] == [PANEL]
    assert [row["role"] for row in result["vhosts"]] == ["panel"]


def test_global_changes(nginx_dirs):
    write_vhost(nginx_dirs, "panel", PANEL_VHOST)
    (nginx_dirs["conf_d"] / "adminpanelaz-server-names-hash.conf").write_text(
        "server_names_hash_bucket_size 128;\n", encoding="utf-8"
    )
    (nginx_dirs["conf_d"] / "adminpanelaz-privacy-log.conf").write_text(
        "log_format adminpanelaz_privacy '$remote_addr';\n", encoding="utf-8"
    )
    (nginx_dirs["enabled"] / "00-adminpanelaz-default-deny").write_text(
        "server { listen 443 ssl default_server; server_name _; }\n", encoding="utf-8"
    )

    result = impact(nginx_dirs)

    assert result["global_changes"] == ["server_names_hash", "privacy-log", "default-deny"]


def test_status_openvpn_outside_nginx(nginx_dirs, monkeypatch):
    setup = nginx_dirs["root"] / "web" / "setup"
    setup.parent.mkdir()
    setup.write_text('DOMAIN="status.arbitrary.test"\nHTTPS_ENABLED=true\n', encoding="utf-8")
    monkeypatch.setenv("STATUS_OPENVPN_SETUP", str(setup))

    result = impact(nginx_dirs)

    assert result["status_openvpn"]["detected"] is True
    assert result["status_openvpn"]["in_nginx"] is False
    assert result["status_openvpn"]["outside_nginx"] is True
    assert result["status_openvpn"]["domain"] == "status.arbitrary.test"
    assert result["status_openvpn"]["path"] is None
    assert "не видит" in result["status_openvpn"]["detail"]


@pytest.mark.parametrize(
    ("panel", "status"),
    [
        ("panel.alpha.test", "status.alpha.test"),
        ("alpha.test", "status.alpha.test"),
        ("panel.beta.example", "status.beta.example"),
    ],
)
def test_no_hardcoded_domains(nginx_dirs, panel, status):
    write_vhost(
        nginx_dirs,
        "panel",
        f"""# AdminPanelAZ — Nginx reverse proxy
server {{
    server_name {panel};
    location / {{
        proxy_pass http://127.0.0.1:8000;
    }}
}}
""",
    )
    write_vhost(
        nginx_dirs,
        "status",
        f"""# Created by StatusOpenVPN
server {{
    server_name {status};
    location /status/ {{
        proxy_pass http://127.0.0.1:1234;
        proxy_set_header X-Script-Name /status;
    }}
}}
""",
    )

    result = impact(nginx_dirs, panel=panel)

    assert result["panel_domain"] == panel
    assert result["integration_mode"] == "dedicated_vhost"
    assert result["vhosts"][0]["role"] == "panel"
    assert result["vhosts"][1]["role"] == "statusopenvpn"
    assert result["foreign_locations"] == []
    assert result["warnings"] == []


def test_bare_status_location_is_reported_not_silently_safe(nginx_dirs):
    write_vhost(nginx_dirs, "panel", PANEL_VHOST)
    write_vhost(
        nginx_dirs,
        "legacy",
        "server {\n    server_name legacy.arbitrary.test;\n    location /status/ { return 200; }\n}\n",
    )

    result = impact(nginx_dirs)

    assert result["status_openvpn"]["in_nginx"] is True
    assert result["status_openvpn"]["outside_nginx"] is False
    assert "проверьте вручную" in result["status_openvpn"]["detail"]
