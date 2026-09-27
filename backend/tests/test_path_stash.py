"""Moving paths aside so a replace can be rolled back."""

from __future__ import annotations

import pytest

from app.services.path_stash import stashed


def _siblings(path):
    return sorted(p.name for p in path.parent.iterdir())


def test_success_discards_the_old_content(tmp_path):
    target = tmp_path / "dir"
    (target / "sub").mkdir(parents=True)
    (target / "sub" / "old.txt").write_text("old")
    single = tmp_path / "file.conf"
    single.write_text("old")

    with stashed([target, single]):
        assert not target.exists()
        assert not single.exists()
        target.mkdir()
        (target / "new.txt").write_text("new")

    assert (target / "new.txt").read_text() == "new"
    assert not (target / "sub").exists()
    assert not single.exists()
    assert _siblings(target) == ["dir"]


def test_failure_puts_the_old_content_back(tmp_path):
    target = tmp_path / "dir"
    target.mkdir()
    (target / "old.txt").write_text("old")
    single = tmp_path / "file.conf"
    single.write_text("old")
    absent = tmp_path / "absent"

    with pytest.raises(RuntimeError):
        with stashed([target, single, absent]):
            target.mkdir()
            (target / "partial.txt").write_text("partial")
            single.write_text("partial")
            absent.mkdir()
            raise RuntimeError("copy failed")

    assert sorted(p.name for p in target.iterdir()) == ["old.txt"]
    assert single.read_text() == "old"
    assert not absent.exists()
    assert _siblings(target) == ["dir", "file.conf"]


def test_failure_before_anything_was_written(tmp_path):
    target = tmp_path / "dir"
    target.mkdir()
    (target / "old.txt").write_text("old")

    with pytest.raises(ValueError):
        with stashed([target]):
            raise ValueError

    assert (target / "old.txt").read_text() == "old"
    assert _siblings(target) == ["dir"]


def test_stash_failure_restores_already_moved_paths(tmp_path, monkeypatch):
    first = tmp_path / "first"
    first.write_text("1")
    second = tmp_path / "second"
    second.write_text("2")

    import app.services.path_stash as mod

    real_rename = mod.os.rename
    calls = 0

    def flaky_rename(src, dst):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("rename failed")
        return real_rename(src, dst)

    monkeypatch.setattr(mod.os, "rename", flaky_rename)
    with pytest.raises(OSError):
        with stashed([first, second]):
            pytest.fail("body must not run when stashing failed")

    monkeypatch.setattr(mod.os, "rename", real_rename)
    assert first.read_text() == "1"
    assert second.read_text() == "2"
    assert _siblings(first) == ["first", "second"]


def test_symlink_is_moved_not_followed(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "keep.txt").write_text("keep")
    link = tmp_path / "link"
    link.symlink_to(real)

    with stashed([link]):
        assert not link.exists() and not link.is_symlink()

    assert (real / "keep.txt").read_text() == "keep"


def test_dangling_symlink_is_stashed_and_restored(tmp_path):
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "missing")

    with pytest.raises(RuntimeError):
        with stashed([link]):
            assert not link.is_symlink()
            link.write_text("partial")
            raise RuntimeError

    assert link.is_symlink()
    assert not (tmp_path / "missing").exists()
    assert _siblings(link) == ["link"]
