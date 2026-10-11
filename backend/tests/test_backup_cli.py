import json
import os
import types
from pathlib import Path

from fastapi import HTTPException


def _load_cli():
    import importlib.util

    cli_path = Path(__file__).resolve().parents[2] / "scripts" / "backup-cli.py"
    spec = importlib.util.spec_from_file_location("backup_cli_restore", cli_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_restore_applies_sqlite_then_local_overlays(tmp_path, monkeypatch, capsys):
    module = _load_cli()
    order: list[str] = []
    az_root = tmp_path / "resolved-az"
    install_dir = tmp_path / "panel"
    (install_dir / "backend").mkdir(parents=True)
    (install_dir / "backend" / ".env").write_text(
        f"ANTIZAPRET_PATH={az_root}\n",
        encoding="utf-8",
    )
    payload = {
        "restored": ["db", "configs", "awg2"],
        "file_name": "panel.tar.gz",
        "configs": {"include-hosts.txt": "x\n"},
        "_files": {"awg2": b"ov"},
    }

    class Mgr:
        db_path = install_dir / "backend" / "data" / "adminpanel.db"
        env_path = install_dir / "backend" / ".env"

        def load_restore_payload(self, name, *, allow_absolute_path=False):
            order.append("load")
            return payload

        def apply_restore_payload(self, data):
            order.append("sqlite")
            return {"file_name": data["file_name"], "restored": data["restored"]}

    monkeypatch.setattr(module, "_build_manager", lambda _install: Mgr())
    monkeypatch.setattr(module, "_service_control", lambda action, **kw: order.append(action))
    monkeypatch.setattr(
        module,
        "apply_backup_overlays",
        lambda data, mode, db=None, config_root=None: order.append(f"overlays:{mode}:{config_root}"),
    )
    args = types.SimpleNamespace(install_dir=str(install_dir), backup_name="panel.tar.gz")
    assert module.cmd_restore(args) == 0
    assert order == [
        "stop",
        "load",
        "sqlite",
        f"overlays:local:{az_root / 'config'}",
        "start",
    ]
    out = capsys.readouterr().out
    assert "panel.tar.gz" in out
    assert "Push full" in out
    assert "Примен" in out


def test_cli_restore_sqlite_failure_still_starts(tmp_path, monkeypatch):
    module = _load_cli()
    order: list[str] = []

    class Mgr:
        def load_restore_payload(self, name, *, allow_absolute_path=False):
            raise HTTPException(status_code=400, detail="нет архива")

        def apply_restore_payload(self, data):
            raise AssertionError("should not apply")

    monkeypatch.setattr(module, "_build_manager", lambda _install: Mgr())
    monkeypatch.setattr(module, "_service_control", lambda action, **kw: order.append(action))
    args = types.SimpleNamespace(install_dir=str(tmp_path), backup_name="missing.tar.gz")
    assert module.cmd_restore(args) == 1
    assert order == ["stop", "start"]


def test_cli_include_configs_help_mentions_antizapret_path(capsys):
    module = _load_cli()
    try:
        module.main(["create", "--help"])
    except SystemExit as exc:
        assert exc.code == 0
    out = capsys.readouterr().out
    assert "ANTIZAPRET_PATH" in out


def test_cli_restore_allows_absolute_archive_path(tmp_path, monkeypatch):
    module = _load_cli()
    seen: list[tuple[str, bool]] = []

    class Mgr:
        db_path = tmp_path / "adminpanel.db"
        env_path = tmp_path / ".env"

        def load_restore_payload(self, name, *, allow_absolute_path=False):
            seen.append((name, allow_absolute_path))
            return {"restored": ["db"], "file_name": name, "configs": {}, "_files": {}}

        def apply_restore_payload(self, data):
            return {"file_name": data["file_name"], "restored": data["restored"]}

    monkeypatch.setattr(module, "_build_manager", lambda _install: Mgr())
    monkeypatch.setattr(module, "_service_control", lambda action, **kw: None)
    monkeypatch.setattr(module, "apply_backup_overlays", lambda data, mode, db=None, config_root=None: None)
    monkeypatch.setattr(
        "app.services.client_portal.sync_portal_domain_after_restore",
        lambda **_kw: {},
    )
    archive = str(tmp_path / "elsewhere" / "adminpanelaz_1.tar.gz")
    args = types.SimpleNamespace(install_dir=str(tmp_path), backup_name=archive)

    assert module.cmd_restore(args) == 0
    assert seen == [(archive, True)]


def _panel_with_backups(tmp_path: Path) -> tuple[Path, Path]:
    backups = tmp_path / "backups"
    backups.mkdir()
    install = tmp_path / "panel"
    (install / "backend").mkdir(parents=True)
    (install / "backend" / ".env").write_text(f"BACKUP_ROOT={backups}\n", encoding="utf-8")
    return install, backups


def _write_archive(root: Path, name: str, mtime: int, meta: dict | None) -> None:
    archive = root / name
    archive.write_bytes(b"x" * 1024)
    if meta is not None:
        (root / name.replace(".tar.gz", ".json")).write_text(json.dumps(meta), encoding="utf-8")
    os.utime(archive, (mtime, mtime))


def test_cli_list_prints_archives_newest_first(tmp_path, capsys):
    module = _load_cli()
    install, backups = _panel_with_backups(tmp_path)
    _write_archive(
        backups,
        "adminpanelaz_old.tar.gz",
        1_700_000_000,
        {"created_at": "2023-11-14T22:13:20Z", "components": ["db", "env"]},
    )
    _write_archive(
        backups,
        "adminpanelaz_new.tar.gz",
        1_800_000_000,
        {"created_at": "2027-01-15T08:00:00Z", "components": ["db", "env", "configs"]},
    )

    assert module.main(["--install-dir", str(install), "list"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "adminpanelaz_new.tar.gz\t2027-01-15T08:00:00Z\t1024\tdb,env,configs",
        "adminpanelaz_old.tar.gz\t2023-11-14T22:13:20Z\t1024\tdb,env",
    ]


def test_cli_list_without_metadata_uses_mtime(tmp_path, capsys):
    module = _load_cli()
    install, backups = _panel_with_backups(tmp_path)
    _write_archive(backups, "adminpanelaz_upload.tar.gz", 1_700_000_000, None)

    assert module.main(["--install-dir", str(install), "list"]) == 0
    assert capsys.readouterr().out == "adminpanelaz_upload.tar.gz\t2023-11-14T22:13:20Z\t1024\t\n"


def test_cli_list_empty_prints_nothing(tmp_path, capsys):
    module = _load_cli()
    install, _backups = _panel_with_backups(tmp_path)

    assert module.main(["--install-dir", str(install), "list"]) == 0
    assert capsys.readouterr().out == ""


def test_cli_list_reports_error(tmp_path, monkeypatch, capsys):
    module = _load_cli()

    class Mgr:
        def list_backups(self):
            raise PermissionError("нет доступа")

    monkeypatch.setattr(module, "_build_manager", lambda _install: Mgr())
    assert module.main(["--install-dir", str(tmp_path), "list"]) == 1
    assert "ERROR: нет доступа" in capsys.readouterr().err


def _create_with(module, monkeypatch, tmp_path, *extra: str) -> dict:
    seen: dict = {}

    class Mgr:
        def list_backups(self):
            return [{}] * 5

        def create_backup(self, **kwargs):
            seen.update(kwargs)
            return {"file_path": "/backups/adminpanelaz_new.tar.gz"}

    monkeypatch.setattr(module, "_build_manager", lambda _install: Mgr())
    monkeypatch.setattr(module, "_service_control", lambda action, **kw: None)
    assert module.main(["--install-dir", str(tmp_path), "create", *extra]) == 0
    return seen


def test_cli_create_no_prune_keeps_every_archive(tmp_path, monkeypatch, capsys):
    module = _load_cli()
    seen = _create_with(module, monkeypatch, tmp_path, "--no-prune")
    assert seen["retention"] == 6
    assert capsys.readouterr().out.strip() == "/backups/adminpanelaz_new.tar.gz"


def test_cli_create_default_keeps_five(tmp_path, monkeypatch):
    module = _load_cli()
    seen = _create_with(module, monkeypatch, tmp_path)
    assert seen["retention"] == 5
