"""Site diagnostics tests — adapted from AdminAntizapret for AdminPanelAZ paths."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import app.services.site_diagnostics as site_diagnostics
from app.services.site_diagnostics import (
    CheckResult,
    DiagnosticsContext,
    decode_journal_line,
    report_to_dict,
    run_site_diagnostics,
)


class DecodeJournalLineTests(unittest.TestCase):
    def test_address_already_in_use(self):
        hint = decode_journal_line("Error: [Errno 98] Address already in use", app_port="8000")
        self.assertIsNotNone(hint)
        self.assertIn("8000", hint)

    def test_import_error(self):
        hint = decode_journal_line("ModuleNotFoundError: No module named 'fastapi'")
        self.assertIsNotNone(hint)
        self.assertIn("requirements.txt", hint)

    def test_unknown_line_returns_none(self):
        self.assertIsNone(decode_journal_line("Started uvicorn normally"))


class RunSiteDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.install_dir = self.tmp.name
        backend = os.path.join(self.install_dir, "backend")
        data_dir = os.path.join(backend, "data")
        venv_bin = os.path.join(backend, ".venv", "bin")
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(venv_bin, exist_ok=True)

        self.ctx = DiagnosticsContext(
            install_dir=self.install_dir,
            service_name="adminpanelaz-test",
            venv_path=os.path.join(backend, ".venv"),
        )

        with open(os.path.join(backend, ".env"), "w", encoding="utf-8") as fh:
            fh.write("SECRET_KEY=abc\nBACKEND_PORT=8000\nBIND=127.0.0.1\n")

        uvicorn = os.path.join(venv_bin, "uvicorn")
        with open(uvicorn, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\n")
        os.chmod(uvicorn, 0o755)

        with open(os.path.join(self.install_dir, "start.sh"), "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\n")
        os.chmod(os.path.join(self.install_dir, "start.sh"), 0o755)

        main_py = os.path.join(backend, "app", "main.py")
        os.makedirs(os.path.dirname(main_py), exist_ok=True)
        with open(main_py, "w", encoding="utf-8") as fh:
            fh.write("# test\n")

        db_path = os.path.join(data_dir, "adminpanel.db")
        with open(db_path, "wb") as fh:
            fh.write(b"sqlite")

    def tearDown(self):
        self.tmp.cleanup()

    def _fake_run(self, mapping):
        def runner(args: list[str], timeout: float) -> subprocess.CompletedProcess:
            key = " ".join(args)
            stdout, stderr, code = mapping.get(key, ("", "", 1))
            return subprocess.CompletedProcess(args, code, stdout, stderr)

        return runner

    def test_missing_unit_reports_fail(self):
        real_isfile = site_diagnostics.os.path.isfile

        def isfile(path: str) -> bool:
            if path.endswith(".service"):
                return False
            return real_isfile(path)

        with patch.object(site_diagnostics.os.path, "isfile", side_effect=isfile):
            report = run_site_diagnostics(
                self.ctx,
                run_cmd=self._fake_run(
                    {
                        f"systemctl is-enabled {self.ctx.service_name}": ("enabled", "", 0),
                        f"systemctl is-active {self.ctx.service_name}": ("inactive", "", 3),
                    }
                ),
            )
        titles = [r.title for r in report.results]
        self.assertTrue(any("не найден" in t for t in titles))
        self.assertTrue(report.has_failures())

    def test_active_service_and_files_ok(self):
        unit_path = f"/etc/systemd/system/{self.ctx.service_name}.service"
        real_isfile = site_diagnostics.os.path.isfile

        def isfile(path: str) -> bool:
            if path == unit_path:
                return True
            return real_isfile(path)

        with patch.object(site_diagnostics.os.path, "isfile", side_effect=isfile):
            report = run_site_diagnostics(
                self.ctx,
                run_cmd=self._fake_run(
                    {
                        f"systemctl is-enabled {self.ctx.service_name}": ("enabled", "", 0),
                        f"systemctl is-active {self.ctx.service_name}": ("active\n", "", 0),
                        f"journalctl -u {self.ctx.service_name} -n 30 --no-pager -o cat": (
                            "Listening at http://127.0.0.1:8000\n",
                            "",
                            0,
                        ),
                        "ss -tlnp": (
                            "LISTEN 0 128 127.0.0.1:8000 0.0.0.0:* users:((\"uvicorn\",pid=1))\n",
                            "",
                            0,
                        ),
                        "curl -sf --max-time 3 http://127.0.0.1:8000/api/health": ("", "", 0),
                        "iptables -L INPUT -n": ("", "", 0),
                        "ipset version": ("v7\n", "", 0),
                    }
                ),
            )

        self.assertGreater(report.ok_count, 0)
        fw_ok = [r for r in report.results if "iptables" in r.title.lower() and r.status == "ok"]
        self.assertEqual(len(fw_ok), 1)
        self.assertFalse(
            any(r.status == "fail" and "adminpanel.db" in r.title for r in report.results)
        )

    @patch("app.services.site_diagnostics.shutil.which", return_value=None)
    def test_missing_firewall_tools_warns(self, _which):
        unit_path = f"/etc/systemd/system/{self.ctx.service_name}.service"
        real_isfile = site_diagnostics.os.path.isfile

        def isfile(path: str) -> bool:
            if path == unit_path:
                return True
            return real_isfile(path)

        with patch.object(site_diagnostics.os.path, "isfile", side_effect=isfile):
            report = run_site_diagnostics(
                self.ctx,
                run_cmd=self._fake_run(
                    {
                        f"systemctl is-enabled {self.ctx.service_name}": ("enabled", "", 0),
                        f"systemctl is-active {self.ctx.service_name}": ("active", "", 0),
                        f"journalctl -u {self.ctx.service_name} -n 30 --no-pager -o cat": ("", "", 0),
                        "ss -tlnp": ("", "", 0),
                    }
                ),
            )
        fw_warns = [r for r in report.results if "iptables" in r.title.lower() and r.status == "warn"]
        self.assertEqual(len(fw_warns), 1)
        self.assertIn("apt install", fw_warns[0].hint_ru)

    def test_format_check_result_fields(self):
        item = CheckResult("warn", "Тест", detail="деталь", hint_ru="подсказка")
        self.assertEqual(item.status, "warn")
        self.assertEqual(item.detail, "деталь")
