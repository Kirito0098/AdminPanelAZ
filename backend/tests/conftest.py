import os
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


# Tests run on the production host: a hard-coded system path in the code under test
# must fail the test, not overwrite the live PKI or VPN configs.
_PROTECTED_ROOTS = ("/etc", "/root/antizapret")


def _is_protected(path) -> bool:
    if isinstance(path, int):
        return False
    try:
        real = os.path.realpath(os.fspath(path))
    except TypeError:
        return False
    return any(real == root or real.startswith(root + "/") for root in _PROTECTED_ROOTS)


def _refuse_system(*paths) -> None:
    for path in paths:
        if path is not None and _is_protected(path):
            raise AssertionError(f"test tried to modify host path {path}; point it at tmp_path")


@pytest.fixture(autouse=True)
def _refuse_host_system_writes(monkeypatch):
    import builtins
    import io
    import shutil
    import tarfile

    def wrap(owner, name, pick):
        real = getattr(owner, name)

        def guarded(*args, **kwargs):
            _refuse_system(*pick(*args, **kwargs))
            return real(*args, **kwargs)

        monkeypatch.setattr(owner, name, guarded)

    def open_targets(file, mode="r", *args, **kwargs):
        return (file,) if any(flag in mode for flag in "wax+") else ()

    wrap(builtins, "open", open_targets)
    wrap(io, "open", open_targets)
    for name in ("mkdir", "rmdir", "unlink", "remove"):
        wrap(os, name, lambda path, *a, **k: (path,))
    for name in ("rename", "replace"):
        wrap(os, name, lambda src, dst, *a, **k: (src, dst))
    wrap(shutil, "rmtree", lambda path, *a, **k: (path,))
    for name in ("copy", "copy2", "copyfile", "copytree", "move"):
        wrap(shutil, name, lambda src, dst, *a, **k: (dst,))
    wrap(tarfile.TarFile, "extract", lambda self, member, path="", *a, **k: (path or ".",))
    wrap(tarfile.TarFile, "extractall", lambda self, path=".", *a, **k: (path,))
