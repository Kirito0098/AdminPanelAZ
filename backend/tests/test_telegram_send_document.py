import inspect

from app.services.telegram import send_tg_document, send_tg_photo


def test_send_tg_document_default_is_sync():
    assert inspect.signature(send_tg_document).parameters["run_async"].default is False


def test_send_tg_photo_default_is_sync():
    assert inspect.signature(send_tg_photo).parameters["run_async"].default is False


def test_send_tg_document_sync_calls_urlopen_before_returning(tmp_path, monkeypatch):
    called = {"urlopen": False}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_urlopen(_req, timeout=None):
        called["urlopen"] = True
        return _Resp()

    monkeypatch.setattr("app.services.telegram._outbound_enabled", lambda: True)
    monkeypatch.setattr("app.services.telegram.urllib.request.urlopen", fake_urlopen)
    payload = tmp_path / "backup.tar.gz"
    payload.write_bytes(b"archive")

    ok = send_tg_document("token", "1", str(payload), caption="cap")

    assert ok is True
    assert called["urlopen"] is True


def test_send_tg_document_async_returns_before_urlopen(tmp_path, monkeypatch):
    started = {"thread": False}

    class _FakeThread:
        def __init__(self, target, daemon=False):
            self._target = target
            started["thread"] = True

        def start(self):
            return None

    monkeypatch.setattr("app.services.telegram._outbound_enabled", lambda: True)
    monkeypatch.setattr("app.services.telegram.threading.Thread", _FakeThread)
    payload = tmp_path / "backup.tar.gz"
    payload.write_bytes(b"archive")

    ok = send_tg_document("token", "1", str(payload), run_async=True)

    assert ok is True
    assert started["thread"] is True
