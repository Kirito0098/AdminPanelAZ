from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.main as main_module


def _write_build(dist: Path, marker: str) -> None:
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(f"<html><head></head><body>{marker}</body></html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text(f"console.log('{marker}')", encoding="utf-8")


@pytest.fixture
def dist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    dist = tmp_path / "dist"
    _write_build(dist, "OLD")
    monkeypatch.setattr(main_module.settings, "frontend_dist_path", dist)
    return dist


def _client() -> TestClient:
    app = FastAPI()
    main_module._mount_frontend(app)
    return TestClient(app)


def test_spa_answers_503_while_index_html_is_missing(dist: Path):
    client = _client()
    (dist / "index.html").unlink()

    response = client.get("/settings")

    assert response.status_code == 503
    assert response.headers["retry-after"]


def test_spa_serves_a_build_swapped_in_by_rename_without_restart(dist: Path):
    client = _client()
    assert "OLD" in client.get("/").text

    dist.rename(dist.with_name("dist.old"))
    _write_build(dist, "NEW")

    assert "NEW" in client.get("/").text
    assert "NEW" in client.get("/assets/app.js").text
