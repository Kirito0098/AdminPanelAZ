import inspect
import sqlite3
from pathlib import Path

from unittest.mock import MagicMock

from app.services import backup_scheduler, lifespan_workers
from app.services.backup_manager import BackupManager
from app.services.backup_scheduler import collect_backup_config_contents, run_backup_scheduler_loop


def test_scheduler_loop_accepts_cidr_db_path():
    params = inspect.signature(run_backup_scheduler_loop).parameters
    assert "cidr_db_path" in params


def test_lifespan_passes_cidr_db_path_into_scheduler():
    source = inspect.getsource(lifespan_workers.spawn_background_tasks)
    assert "resolve_cidr_db_path" in source
    assert "cidr_db_path=" in source


def test_cli_build_manager_sets_cidr_db_path(tmp_path: Path, monkeypatch):
    install = tmp_path / "panel"
    backend = install / "backend"
    (backend / "data" / "cidr").mkdir(parents=True)
    (backend / ".env").write_text("BACKUP_ROOT=" + str(tmp_path / "backups") + "\n", encoding="utf-8")
    sqlite3.connect(backend / "data" / "adminpanel.db").close()
    sqlite3.connect(backend / "data" / "cidr" / "cidr.db").close()

    import importlib.util

    cli_path = Path(__file__).resolve().parents[2] / "scripts" / "backup-cli.py"
    spec = importlib.util.spec_from_file_location("backup_cli_under_test", cli_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    manager = module._build_manager(str(install))
    assert manager.cidr_db_path is not None
    assert manager.cidr_db_path == (backend / "data" / "cidr" / "cidr.db").resolve()


def test_collect_backup_config_contents_reads_adapter(monkeypatch):
    adapter = MagicMock()
    adapter.read_config_file.side_effect = lambda name: f"{name}-data"
    monkeypatch.setattr(backup_scheduler, "get_active_adapter", lambda _db: adapter)
    contents = collect_backup_config_contents(MagicMock())
    assert contents is not None
    assert contents["include-hosts.txt"] == "include-hosts.txt-data"
    assert set(contents) == set(BackupManager.CONFIG_FILES)


def test_cli_include_configs_reads_antizapret_home(tmp_path: Path, monkeypatch):
    config_dir = tmp_path / "az" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "include-hosts.txt").write_text("foo.example\n", encoding="utf-8")
    monkeypatch.setenv("ANTIZAPRET_HOME", str(tmp_path / "az"))

    import importlib.util

    cli_path = Path(__file__).resolve().parents[2] / "scripts" / "backup-cli.py"
    spec = importlib.util.spec_from_file_location("backup_cli_configs", cli_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    contents = module._load_config_contents(True)
    assert contents is not None
    assert contents["include-hosts.txt"] == "foo.example\n"
    assert module._load_config_contents(False) is None
