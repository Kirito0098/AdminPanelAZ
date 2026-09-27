"""Panel update pulls the checked-out branch from its upstream, never another branch."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.services.node_update import check_git_updates, git_pull


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _commit(repo: Path, name: str) -> str:
    (repo / name).write_text(name, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", name)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repos(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    upstream = tmp_path / "upstream"
    _git(tmp_path, "clone", "-q", str(origin), str(upstream))
    _commit(upstream, "base")
    _git(upstream, "push", "-q", "origin", "HEAD:main")
    _git(upstream, "checkout", "-q", "-b", "release/9.9.9")
    _commit(upstream, "release-work")
    _git(upstream, "push", "-q", "origin", "release/9.9.9")

    panel = tmp_path / "panel"
    _git(tmp_path, "clone", "-q", str(origin), str(panel))
    _git(panel, "checkout", "-q", "-b", "release/9.9.9", "--track", "origin/release/9.9.9")
    return upstream, panel


def test_release_branch_is_not_reset_to_main(repos):
    upstream, panel = repos
    before = _git(panel, "rev-parse", "HEAD")
    _git(upstream, "checkout", "-q", "main")
    _commit(upstream, "hotfix")
    _git(upstream, "push", "-q", "origin", "main")

    result = git_pull(panel)

    assert result["success"] is True
    assert _git(panel, "rev-parse", "--abbrev-ref", "HEAD") == "release/9.9.9"
    assert _git(panel, "rev-parse", "HEAD") == before


def test_release_branch_fast_forwards_from_its_upstream(repos):
    upstream, panel = repos
    new_head = _commit(upstream, "more-release-work")
    _git(upstream, "push", "-q", "origin", "release/9.9.9")

    result = git_pull(panel)

    assert result["success"] is True
    assert _git(panel, "rev-parse", "HEAD") == new_head


def test_rewritten_upstream_resets_to_the_same_branch(repos):
    upstream, panel = repos
    _git(upstream, "reset", "-q", "--hard", "HEAD~1")
    rewritten = _commit(upstream, "rewritten-release")
    _git(upstream, "push", "-q", "-f", "origin", "release/9.9.9")

    result = git_pull(panel)

    assert result["success"] is True
    assert result["method"] == "reset"
    assert "origin/release/9.9.9" in result["output"]
    assert _git(panel, "rev-parse", "HEAD") == rewritten


UNPUSHED_MESSAGE = "В локальной ветке есть коммиты, которых нет на сервере git"


def test_diverged_with_unpushed_local_commit_is_refused(repos):
    upstream, panel = repos
    local = _commit(panel, "local-work")
    _commit(upstream, "more-release-work")
    _git(upstream, "push", "-q", "origin", "release/9.9.9")

    result = git_pull(panel)

    assert result["success"] is False
    assert UNPUSHED_MESSAGE in result["error"]
    assert set(result) == {"success", "output", "error", "method"}
    assert _git(panel, "rev-parse", "HEAD") == local


def test_rewritten_upstream_with_unpushed_local_commit_is_refused(repos):
    upstream, panel = repos
    local = _commit(panel, "local-work")
    _git(upstream, "reset", "-q", "--hard", "HEAD~1")
    _commit(upstream, "rewritten-release")
    _git(upstream, "push", "-q", "-f", "origin", "release/9.9.9")

    result = git_pull(panel)

    assert result["success"] is False
    assert UNPUSHED_MESSAGE in result["error"]
    assert _git(panel, "rev-parse", "HEAD") == local


def test_rewritten_upstream_resets_when_local_commits_are_on_a_remote_branch(repos):
    upstream, panel = repos
    _git(upstream, "push", "-q", "origin", "release/9.9.9:backup")
    _git(upstream, "reset", "-q", "--hard", "HEAD~1")
    rewritten = _commit(upstream, "rewritten-release")
    _git(upstream, "push", "-q", "-f", "origin", "release/9.9.9")

    result = git_pull(panel)

    assert result["success"] is True
    assert result["method"] == "reset"
    assert _git(panel, "rev-parse", "HEAD") == rewritten


def test_branch_without_upstream_is_refused(repos):
    _upstream, panel = repos
    _git(panel, "checkout", "-q", "-b", "local-only")
    before = _git(panel, "rev-parse", "HEAD")

    result = git_pull(panel)

    assert result["success"] is False
    assert "local-only" in result["error"]
    assert _git(panel, "rev-parse", "HEAD") == before


def test_detached_head_is_refused(repos):
    _upstream, panel = repos
    _git(panel, "checkout", "-q", "--detach")
    before = _git(panel, "rev-parse", "HEAD")

    result = git_pull(panel)

    assert result["success"] is False
    assert _git(panel, "rev-parse", "HEAD") == before


def test_update_check_compares_with_the_branch_upstream(repos):
    upstream, panel = repos
    _git(upstream, "checkout", "-q", "main")
    _commit(upstream, "hotfix")
    _git(upstream, "push", "-q", "origin", "main")

    status = check_git_updates(panel)

    assert status["updates_available"] is False
    assert status["commits_behind"] == 0


def test_panel_update_status_compares_with_the_branch_upstream(repos):
    from app.routers.system import _git_update_status

    upstream, panel = repos
    _git(upstream, "checkout", "-q", "main")
    _commit(upstream, "hotfix")
    _git(upstream, "push", "-q", "origin", "main")

    assert _git_update_status(panel)["updates_available"] is False

    _git(upstream, "checkout", "-q", "release/9.9.9")
    _commit(upstream, "more-release-work")
    _git(upstream, "push", "-q", "origin", "release/9.9.9")

    status = _git_update_status(panel)
    assert status["updates_available"] is True
    assert status["commits_behind"] == 1
