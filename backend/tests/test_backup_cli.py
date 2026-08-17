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
        def load_restore_payload(self, name):
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
        def load_restore_payload(self, name):
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
