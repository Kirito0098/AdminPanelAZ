"""Warper domains.txt is read once per domains endpoint payload."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import app.services.warper as warper_mod
from app.services.warper import WarperService, domains_payload_from_text, read_domains_file_payload


SAMPLE = """# Пользовательские домены:
example.com
# --- GEMINI ---
gemini.google.com
# --- END GEMINI ---
# --- CHATGPT ---
chatgpt.com
# --- END CHATGPT ---
"""


def test_domains_payload_from_text_derives_lists_domains_and_user_text():
    payload = domains_payload_from_text(SAMPLE)
    assert payload["lists"] == {"gemini": True, "chatgpt": True}
    domains = {item["domain"]: item["type"] for item in payload["domains"]}
    assert domains["example.com"] == "user"
    assert domains["gemini.google.com"] == "gemini"
    assert domains["chatgpt.com"] == "chatgpt"
    assert "example.com" in payload["user_text"]
    assert "gemini.google.com" not in payload["user_text"]
    assert "chatgpt.com" not in payload["user_text"]


def test_read_domains_file_payload_reads_once(tmp_path: Path, monkeypatch):
    domains_file = tmp_path / "domains.txt"
    domains_file.write_text(SAMPLE, encoding="utf-8")
    monkeypatch.setattr(warper_mod, "WARPER_DOMAINS_FILE", domains_file)

    opens: list[str] = []
    real_open = Path.open

    def tracking_open(self, *args, **kwargs):
        opens.append(str(self))
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)

    payload = read_domains_file_payload()
    assert len(opens) == 1
    assert payload["lists"]["gemini"] is True
    assert any(item["domain"] == "example.com" for item in payload["domains"])
    assert "example.com" in payload["user_text"]


def test_get_domains_bundle_uses_single_file_read_when_api_unavailable(tmp_path: Path, monkeypatch):
    domains_file = tmp_path / "domains.txt"
    domains_file.write_text(SAMPLE, encoding="utf-8")
    monkeypatch.setattr(warper_mod, "WARPER_DOMAINS_FILE", domains_file)
    monkeypatch.setattr(warper_mod, "is_warper_installed", lambda: True)

    service = WarperService()
    api = MagicMock()
    from fastapi import HTTPException

    api.list_domains.side_effect = HTTPException(status_code=502, detail="down")
    # Missing get_user_domains_text → file-derived user_text.
    del api.get_user_domains_text
    monkeypatch.setattr(service, "_api_client", lambda: api)

    opens: list[str] = []
    real_open = Path.open

    def tracking_open(self, *args, **kwargs):
        opens.append(str(self))
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)

    payload = service.get_domains_bundle()
    assert len(opens) == 1
    assert payload["lists"]["chatgpt"] is True
    assert any(item["domain"] == "example.com" for item in payload["domains"])
    assert "example.com" in payload["user_text"]
