from app.services.node_sync.fingerprints import CONFIG_FP_PREFIX
from app.services.node_sync.verify import (
    _config_files_diff,
    _enrich_config_fingerprints,
    _fingerprint_mismatches,
)


class _StubAdapter:
    def __init__(self, file_hashes: dict[str, str] | None = None):
        self._file_hashes = file_hashes or {}

    def get_config_file_fingerprints(self) -> dict[str, str]:
        return dict(self._file_hashes)


def test_config_files_diff_asymmetric_does_not_mark_only_primary():
    primary_fp = {
        CONFIG_FP_PREFIX: "agg-primary",
        f"{CONFIG_FP_PREFIX}/include-hosts.txt": "hash-a",
        f"{CONFIG_FP_PREFIX}/exclude-hosts.txt": "hash-b",
    }
    replica_fp = {
        CONFIG_FP_PREFIX: "agg-replica",
    }

    diff = _config_files_diff(primary_fp, replica_fp)

    assert diff is not None
    assert diff["changed_files"] == []
    assert diff["only_primary"] == []
    assert diff["only_replica"] == []
    assert "реплике" in diff["detail"]


def test_enrich_config_fingerprints_adds_missing_per_file_keys():
    adapter = _StubAdapter({"include-hosts.txt": "hash-a"})
    fp = {CONFIG_FP_PREFIX: "agg"}

    enriched = _enrich_config_fingerprints(fp, adapter)

    assert enriched[f"{CONFIG_FP_PREFIX}/include-hosts.txt"] == "hash-a"
    assert enriched[CONFIG_FP_PREFIX] == "agg"


def test_enrich_config_fingerprints_skips_when_per_file_already_present():
    adapter = _StubAdapter({"other.txt": "hash-other"})
    fp = {
        CONFIG_FP_PREFIX: "agg",
        f"{CONFIG_FP_PREFIX}/include-hosts.txt": "hash-a",
    }

    enriched = _enrich_config_fingerprints(fp, adapter)

    assert enriched == fp


def test_config_files_diff_after_enrichment_shows_changed_files():
    primary_fp = {
        CONFIG_FP_PREFIX: "agg-primary",
        f"{CONFIG_FP_PREFIX}/include-hosts.txt": "hash-a",
    }
    replica_fp = {CONFIG_FP_PREFIX: "agg-replica"}
    adapter = _StubAdapter({"include-hosts.txt": "hash-b"})

    enriched_replica = _enrich_config_fingerprints(replica_fp, adapter)
    diff = _config_files_diff(primary_fp, enriched_replica)

    assert diff is not None
    assert diff["changed_files"] == ["include-hosts.txt"]
    assert diff["only_primary"] == []
    assert "detail" not in diff


def test_config_files_diff_lists_changed_and_missing_files():
    primary_fp = {
        CONFIG_FP_PREFIX: "agg-primary",
        f"{CONFIG_FP_PREFIX}/include-hosts.txt": "hash-a",
        f"{CONFIG_FP_PREFIX}/exclude-hosts.txt": "hash-b",
        f"{CONFIG_FP_PREFIX}/only-primary.txt": "hash-c",
    }
    replica_fp = {
        CONFIG_FP_PREFIX: "agg-replica",
        f"{CONFIG_FP_PREFIX}/include-hosts.txt": "hash-a-changed",
        f"{CONFIG_FP_PREFIX}/exclude-hosts.txt": "hash-b",
        f"{CONFIG_FP_PREFIX}/only-replica.txt": "hash-d",
    }

    diff = _config_files_diff(primary_fp, replica_fp)

    assert diff is not None
    assert diff["changed_files"] == ["include-hosts.txt"]
    assert diff["only_primary"] == ["only-primary.txt"]
    assert diff["only_replica"] == ["only-replica.txt"]


def test_fingerprint_mismatches_groups_config_into_single_entry():
    primary_fp = {
        CONFIG_FP_PREFIX: "agg-primary",
        f"{CONFIG_FP_PREFIX}/include-hosts.txt": "hash-a",
        "easyrsa3/pki/ca.crt": "ca-primary",
    }
    replica_fp = {
        CONFIG_FP_PREFIX: "agg-replica",
        f"{CONFIG_FP_PREFIX}/include-hosts.txt": "hash-b",
        "easyrsa3/pki/ca.crt": "ca-primary",
    }

    mismatches = _fingerprint_mismatches(primary_fp, replica_fp)

    assert len(mismatches) == 1
    assert mismatches[0]["path"] == CONFIG_FP_PREFIX
    assert mismatches[0]["changed_files"] == ["include-hosts.txt"]
    assert mismatches[0]["primary"] == "agg-primary"
    assert mismatches[0]["replica"] == "agg-replica"


def test_fingerprint_mismatches_keeps_non_config_entries_separate():
    primary_fp = {
        CONFIG_FP_PREFIX: "agg-primary",
        f"{CONFIG_FP_PREFIX}/include-hosts.txt": "hash-a",
        "easyrsa3/pki/ca.crt": "ca-primary",
    }
    replica_fp = {
        CONFIG_FP_PREFIX: "agg-replica",
        f"{CONFIG_FP_PREFIX}/include-hosts.txt": "hash-b",
        "easyrsa3/pki/ca.crt": "ca-replica",
    }

    mismatches = _fingerprint_mismatches(primary_fp, replica_fp)

    assert len(mismatches) == 2
    paths = {item["path"] for item in mismatches}
    assert paths == {CONFIG_FP_PREFIX, "easyrsa3/pki/ca.crt"}
    assert all(not item["path"].startswith(f"{CONFIG_FP_PREFIX}/") for item in mismatches)
