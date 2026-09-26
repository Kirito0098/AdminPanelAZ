import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Tests run on the production host: these files hold its live secrets and settings.
_LIVE_ENV_FILES = frozenset(
    (BACKEND_ROOT / name).resolve() for name in (".env", "node_agent.env", "proxy_agent.env")
)


def _refuse_live(path) -> None:
    if Path(path).resolve() in _LIVE_ENV_FILES:
        raise AssertionError(f"test tried to write live {path}; point it at tmp_path")


@pytest.fixture(autouse=True)
def _refuse_live_env_writes(monkeypatch):
    from app.services import atomic_file
    from app.services.env_file import EnvFileService

    real_write = atomic_file.atomic_write_bytes
    real_exclusive = EnvFileService._exclusive

    def guarded_write(path, data):
        _refuse_live(path)
        return real_write(path, data)

    @contextmanager
    def guarded_exclusive(self):
        _refuse_live(self.env_file_path)
        with real_exclusive(self):
            yield

    monkeypatch.setattr(atomic_file, "atomic_write_bytes", guarded_write)
    monkeypatch.setattr(EnvFileService, "_exclusive", guarded_exclusive)
