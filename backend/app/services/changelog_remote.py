"""Fetch and parse CHANGELOG.md from the remote git ref (not the local working tree)."""

from __future__ import annotations

import re
import urllib.request
from pathlib import Path
from typing import Any

from app.services.node_update import DEFAULT_GIT_BRANCH, _git_run, resolve_repo_root

VERSION_HEADER = re.compile(r"^## \[(.+?)\](?:\s*[–\-]\s*(.+))?$", re.MULTILINE)
SECTION_HEADER = re.compile(r"^### (?![#])(.+)$", re.MULTILINE)

DEFAULT_RAW_CHANGELOG_URL = (
    "https://raw.githubusercontent.com/Kirito0098/AdminPanelAZ/main/CHANGELOG.md"
)


def _parse_sections(block: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    sec_matches = list(SECTION_HEADER.finditer(block))
    for index, match in enumerate(sec_matches):
        sec_end = sec_matches[index + 1].start() if index + 1 < len(sec_matches) else len(block)
        sec_text = block[match.end() : sec_end].strip()
        items = [
            line.lstrip("-* \t").strip()
            for line in sec_text.splitlines()
            if line.strip().startswith(("-", "*"))
        ]
        if items:
            sections.append({"title": match.group(1).strip(), "items": items})
    return sections


def parse_version_blocks(content: str) -> list[dict[str, Any]]:
    matches = list(VERSION_HEADER.finditer(content))
    blocks: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        block_text = content[match.end() : end].strip()
        sections = _parse_sections(block_text)
        blocks.append(
            {
                "version": match.group(1).strip(),
                "date": (match.group(2) or "").strip(),
                "sections": sections,
            }
        )
    return blocks


def _raw_changelog_url(repo_root: Path, branch: str) -> str | None:
    remote = _git_run(["remote", "get-url", "origin"], repo_root, timeout=10.0)
    url = remote.stdout.strip()
    if not url:
        return None

    ssh_match = re.match(r"git@github\.com:(.+?)/(.+?)(?:\.git)?$", url)
    if ssh_match:
        user, repo = ssh_match.group(1), ssh_match.group(2)
        return f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/CHANGELOG.md"

    https_match = re.match(r"https?://github\.com/(.+?)/(.+?)(?:\.git)?/?$", url)
    if https_match:
        user, repo = https_match.group(1), https_match.group(2)
        return f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/CHANGELOG.md"

    return None


def _fetch_via_http(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "AdminPanelAZ/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


def fetch_remote_changelog_content(
    repo_root: Path | None = None,
    *,
    branch: str = DEFAULT_GIT_BRANCH,
) -> tuple[str, str]:
    """Return CHANGELOG text and source label (``git`` or ``github_raw``)."""
    root = repo_root or resolve_repo_root()
    if root is None or not (root / ".git").is_dir():
        content = _fetch_via_http(DEFAULT_RAW_CHANGELOG_URL)
        return content, "github_raw"

    _git_run(["fetch", "origin"], root, timeout=60.0)

    for ref in (f"origin/{branch}", "origin/master"):
        show = _git_run(["show", f"{ref}:CHANGELOG.md"], root, timeout=30.0)
        if show.returncode == 0 and show.stdout.strip():
            return show.stdout, "git"

    raw_url = _raw_changelog_url(root, branch) or DEFAULT_RAW_CHANGELOG_URL
    return _fetch_via_http(raw_url), "github_raw"


def _block_payload(block: dict[str, Any] | None) -> dict[str, Any] | None:
    if block is None or not block.get("sections"):
        return None
    return {
        "version": block["version"],
        "date": block.get("date") or "",
        "sections": block["sections"],
    }


def build_changelog_response(
    content: str,
    *,
    updates_available: bool,
    source: str,
) -> dict[str, Any]:
    blocks = parse_version_blocks(content)
    if not blocks:
        return {
            "success": False,
            "message": "CHANGELOG не содержит версий",
            "source": source,
            "version": "",
            "date": "",
            "sections": [],
            "latest_release": None,
            "pending": None,
        }

    unreleased = next((block for block in blocks if block["version"].lower() == "unreleased"), None)
    releases = [block for block in blocks if block["version"].lower() != "unreleased"]
    latest_release = releases[0] if releases else None

    pending: dict[str, Any] | None = None
    if updates_available:
        if unreleased and unreleased["sections"]:
            pending = unreleased
        elif latest_release:
            pending = latest_release

    latest_payload = _block_payload(latest_release)
    pending_payload = _block_payload(pending)

    primary = pending_payload if updates_available and pending_payload else latest_payload
    return {
        "success": True,
        "message": "",
        "source": source,
        "version": primary["version"] if primary else "",
        "date": primary["date"] if primary else "",
        "sections": primary["sections"] if primary else [],
        "latest_release": latest_payload,
        "pending": pending_payload,
    }
