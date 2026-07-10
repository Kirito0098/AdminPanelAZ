from pathlib import Path

from app.services.node_sync.fingerprints import (
    CONFIG_FP_PREFIX,
    CONFIG_FINGERPRINT_EXCLUDE,
    collect_antizapret_fingerprints,
    collect_config_file_fingerprints,
)


def test_collect_config_file_fingerprints_returns_per_file_hashes(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "include-hosts.txt").write_text("example.com\n", encoding="utf-8")
    (config_dir / "exclude-hosts.txt").write_text("blocked.example\n", encoding="utf-8")
    (config_dir / "warper-include-ips.txt").write_text("10.0.0.1\n", encoding="utf-8")

    result = collect_config_file_fingerprints(config_dir, exclude_names=CONFIG_FINGERPRINT_EXCLUDE)

    assert set(result) == {"include-hosts.txt", "exclude-hosts.txt"}
    assert all(len(digest) == 64 for digest in result.values())


def test_collect_antizapret_fingerprints_includes_aggregate_and_per_file_keys(tmp_path: Path, monkeypatch):
    install_dir = tmp_path / "antizapret"
    config_dir = install_dir / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "include-hosts.txt").write_text("host-a\n", encoding="utf-8")
    (config_dir / "warper-include-ips.txt").write_text("node-local\n", encoding="utf-8")

    monkeypatch.setattr(
        "app.services.node_sync.fingerprints._sha256_directory_glob",
        lambda directory, pattern, exclude_names=None: "aggregate-hash",
    )

    result = collect_antizapret_fingerprints(install_dir)

    assert result[CONFIG_FP_PREFIX] == "aggregate-hash"
    assert f"{CONFIG_FP_PREFIX}/include-hosts.txt" in result
    assert f"{CONFIG_FP_PREFIX}/warper-include-ips.txt" not in result
