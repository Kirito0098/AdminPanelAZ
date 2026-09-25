from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

import app.main as main_module


@pytest.fixture
def spa_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>INDEX</html>", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg>ICON</svg>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("TOPSECRET", encoding="utf-8")

    monkeypatch.setattr(main_module.settings, "frontend_dist_path", dist)
    monkeypatch.setattr(
        "app.services.html_csp.serve_html_with_nonce",
        lambda request, index_file, portal_root=False: PlainTextResponse("INDEX"),
    )
    app = FastAPI()
    main_module._mount_frontend(app)
    return TestClient(app)


@pytest.mark.parametrize(
    "path",
    [
        "/..%2fsecret.txt",
        "/%2e%2e%2fsecret.txt",
        "/%2e%2e/secret.txt",
        "/assets/..%2f..%2fsecret.txt",
        "/..%5csecret.txt",
    ],
)
def test_spa_catch_all_does_not_serve_files_outside_dist(spa_client: TestClient, path: str):
    response = spa_client.get(path)

    assert "TOPSECRET" not in response.text


def test_spa_catch_all_does_not_serve_system_files(spa_client: TestClient):
    response = spa_client.get("/..%2f..%2f..%2f..%2f..%2f..%2f..%2f..%2fetc%2fpasswd")

    assert "root:" not in response.text


@pytest.mark.parametrize("path", ["/%00", "/foo%00bar"])
def test_spa_catch_all_falls_back_to_index_for_null_byte_paths(spa_client: TestClient, path: str):
    response = spa_client.get(path)

    assert response.status_code == 200
    assert response.text == "INDEX"


def test_spa_catch_all_still_serves_real_dist_files(spa_client: TestClient):
    response = spa_client.get("/favicon.svg")

    assert response.status_code == 200
    assert "ICON" in response.text


def test_spa_catch_all_falls_back_to_index_for_client_routes(spa_client: TestClient):
    response = spa_client.get("/settings/security")

    assert response.status_code == 200
    assert response.text == "INDEX"
