"""Deploy must never read or push files outside LIST_DIR.

``selected_files`` comes straight from the HTTP payload, so the whitelist and
the realpath check are the trust boundary for the deploy stage.
"""

import os

import pytest

from app.services.cidr.pipeline import deploy

TRAVERSAL_NAMES = [
    "../../etc/passwd",
    "/etc/passwd",
    "foo/../../bar-ips.txt",
    # Basename of this one is a known provider, the path part must still reject it.
    "../../cloudflare-ips.txt",
]


class _RecordingAdapter:
    def __init__(self) -> None:
        self.saved: dict[str, str] = {}

    def save_provider_content(self, filename: str, content: str) -> dict:
        self.saved[filename] = content
        return {"filename": filename, "cidr_count": 0}

    def sync_cidr_providers(self) -> dict:
        return {"ok": True}


@pytest.fixture
def list_dir(tmp_path, monkeypatch):
    root = tmp_path / "list"
    root.mkdir()
    monkeypatch.setattr(deploy, "LIST_DIR", str(root))
    return root


def test_traversal_names_are_skipped_and_never_read(list_dir):
    # A deployable artifact exists: an unknown selection must not fall back to it.
    (list_dir / "cloudflare-ips.txt").write_text("1.1.1.0/24\n", encoding="utf-8")
    adapter = _RecordingAdapter()

    result = deploy.push_cidr_artifacts(adapter, TRAVERSAL_NAMES)

    assert result["pushed"] == []
    assert result["failed"] == []
    assert result["skipped"] == TRAVERSAL_NAMES
    assert adapter.saved == {}


def test_traversal_names_in_dict_payload_are_skipped(list_dir):
    adapter = _RecordingAdapter()

    result = deploy.push_cidr_artifacts(
        adapter,
        [{"file": "/etc/passwd"}, {"file": "../cloudflare-ips.txt"}],
    )

    assert result["pushed"] == []
    assert result["failed"] == []
    assert result["skipped"] == ["/etc/passwd", "../cloudflare-ips.txt"]
    assert adapter.saved == {}


def test_known_provider_file_is_read_and_pushed(list_dir):
    content = "# comment\n1.1.1.0/24\n"
    (list_dir / "cloudflare-ips.txt").write_text(content, encoding="utf-8")
    adapter = _RecordingAdapter()

    result = deploy.push_cidr_artifacts(adapter, ["cloudflare-ips.txt"])

    assert result["pushed"] == ["cloudflare-ips.txt"]
    assert result["failed"] == []
    assert result["skipped"] == []
    assert adapter.saved == {"cloudflare-ips.txt": content}


def test_mixed_selection_pushes_known_and_reports_unknown(list_dir):
    (list_dir / "cloudflare-ips.txt").write_text("1.1.1.0/24\n", encoding="utf-8")
    adapter = _RecordingAdapter()

    result = deploy.push_cidr_artifacts(adapter, ["cloudflare-ips.txt", "/etc/passwd"])

    assert result["pushed"] == ["cloudflare-ips.txt"]
    assert result["skipped"] == ["/etc/passwd"]
    assert list(adapter.saved) == ["cloudflare-ips.txt"]


def test_empty_selection_still_deploys_all_artifacts(list_dir):
    (list_dir / "cloudflare-ips.txt").write_text("1.1.1.0/24\n", encoding="utf-8")
    (list_dir / "google-ips.txt").write_text("2.2.2.0/24\n", encoding="utf-8")
    adapter = _RecordingAdapter()

    result = deploy.push_cidr_artifacts(adapter, [])

    assert result["pushed"] == ["cloudflare-ips.txt", "google-ips.txt"]
    assert result["skipped"] == []


def test_symlink_escaping_list_dir_is_not_read(list_dir, tmp_path):
    outside = tmp_path / "outside-ips.txt"
    outside.write_text("6.6.6.0/24\n", encoding="utf-8")
    os.symlink(outside, list_dir / "cloudflare-ips.txt")
    adapter = _RecordingAdapter()

    result = deploy.push_cidr_artifacts(adapter, ["cloudflare-ips.txt"])

    assert result["pushed"] == []
    assert result["failed"] == []
    assert result["skipped"] == ["cloudflare-ips.txt"]
    assert adapter.saved == {}
    # The escaping symlink is not offered as an artifact either.
    assert "cloudflare-ips.txt" not in deploy._list_artifact_filenames()


def test_preview_does_not_read_symlink_outside_list_dir(list_dir, tmp_path):
    from app.services.cidr.pipeline.deploy_preview import _read_controller_content

    outside = tmp_path / "outside-ips.txt"
    outside.write_text("6.6.6.0/24\n", encoding="utf-8")
    os.symlink(outside, list_dir / "cloudflare-ips.txt")

    assert _read_controller_content("cloudflare-ips.txt") == ("", 0)


def test_list_artifact_filenames_returns_only_known_txt_files(list_dir):
    (list_dir / "cloudflare-ips.txt").write_text("1.1.1.0/24\n", encoding="utf-8")
    (list_dir / "custom-ips.txt").write_text("2.2.2.0/24\n", encoding="utf-8")
    (list_dir / "notes.md").write_text("not an artifact", encoding="utf-8")
    (list_dir / "unknown.txt").write_text("not a provider", encoding="utf-8")
    (list_dir / "sub").mkdir()

    assert deploy._list_artifact_filenames() == ["cloudflare-ips.txt", "custom-ips.txt"]
