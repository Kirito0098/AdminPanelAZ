"""Tests for mtime-cached CIDR line counting."""

from pathlib import Path

from app.services.cidr.line_counts import (
    clear_line_count_cache,
    count_nonempty_lines,
    count_nonempty_lines_in_text,
    remember_line_count,
)
from app.services.cidr.service import CidrRoutingService


def test_count_nonempty_lines_in_text_skips_blank_and_comments():
    text = "# comment\n\n1.2.3.0/24\n  \n#x\n5.6.7.0/16\n"
    assert count_nonempty_lines_in_text(text) == 2


def test_count_nonempty_lines_cache_avoids_reread(tmp_path: Path, monkeypatch):
    clear_line_count_cache()
    path = tmp_path / "list.txt"
    path.write_text("# c\n10.0.0.0/8\n11.0.0.0/8\n", encoding="utf-8")

    opens: list[str] = []
    real_open = Path.open

    def tracking_open(self, *args, **kwargs):
        opens.append(str(self))
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)

    assert count_nonempty_lines(path) == 2
    assert len(opens) == 1
    assert count_nonempty_lines(path) == 2
    assert len(opens) == 1

    path.write_text("1.1.1.0/24\n", encoding="utf-8")
    opens_after_write = len(opens)
    assert count_nonempty_lines(path) == 1
    assert len(opens) == opens_after_write + 1


def test_remember_line_count_seeds_cache(tmp_path: Path, monkeypatch):
    clear_line_count_cache()
    path = tmp_path / "seeded.txt"
    path.write_text("1.1.1.0/24\n2.2.2.0/24\n", encoding="utf-8")
    remember_line_count(path, 2)

    opens: list[str] = []
    real_open = Path.open

    def tracking_open(self, *args, **kwargs):
        opens.append(str(self))
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)
    assert count_nonempty_lines(path) == 2
    assert opens == []


def test_overview_uses_cached_counts(tmp_path: Path, monkeypatch):
    clear_line_count_cache()
    az = tmp_path / "antizapret"
    lists = tmp_path / "lists"
    (az / "config").mkdir(parents=True)
    (az / "result").mkdir(parents=True)
    lists.mkdir()
    (lists / "cloudflare-ips.txt").write_text(
        "# cf\n1.1.1.0/24\n1.0.0.0/24\n",
        encoding="utf-8",
    )

    svc = CidrRoutingService(az, lists)
    opens: list[str] = []
    real_open = Path.open

    def tracking_open(self, *args, **kwargs):
        opens.append(str(self))
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)

    first = svc.get_overview()
    cf = next(p for p in first["providers"] if p["filename"] == "cloudflare-ips.txt")
    assert cf["cidr_count"] == 2
    first_opens = len(opens)

    second = svc.get_overview()
    cf2 = next(p for p in second["providers"] if p["filename"] == "cloudflare-ips.txt")
    assert cf2["cidr_count"] == 2
    assert len(opens) == first_opens
