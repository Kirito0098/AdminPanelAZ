from pathlib import Path

from app.paths import BACKEND_ROOT, get_cidr_list_dir, resolve_backend_path
from app.services.cidr.pipeline.constants import LIST_DIR


def test_backend_root_points_at_backend_package_parent():
    assert BACKEND_ROOT.name == "backend"
    assert (BACKEND_ROOT / "app" / "main.py").is_file()


def test_cidr_list_dir_matches_pipeline_constant():
    assert str(get_cidr_list_dir()) == LIST_DIR
    assert get_cidr_list_dir() == resolve_backend_path("data/cidr/list")


def test_migrate_legacy_cidr_list_dir_copies_missing_files(tmp_path, monkeypatch):
    target_dir = tmp_path / "data" / "cidr" / "list"
    legacy_dir = tmp_path / "app" / "data" / "cidr" / "list"
    legacy_dir.mkdir(parents=True)
    legacy_dir.joinpath("aws.txt").write_text("10.0.0.0/8\n", encoding="utf-8")

    monkeypatch.setattr("app.services.cidr.pipeline.list_migration.get_cidr_list_dir", lambda: target_dir)
    monkeypatch.setattr("app.services.cidr.pipeline.list_migration._LEGACY_LIST_DIR", legacy_dir)

    from app.services.cidr.pipeline.list_migration import migrate_legacy_cidr_list_dir

    migrated = migrate_legacy_cidr_list_dir()
    assert migrated == 1
    assert (target_dir / "aws.txt").read_text(encoding="utf-8") == "10.0.0.0/8\n"


def test_env_file_path_is_under_backend_root():
    from app.services.cidr.pipeline.constants import ENV_FILE_PATH

    assert Path(ENV_FILE_PATH).parent == BACKEND_ROOT
