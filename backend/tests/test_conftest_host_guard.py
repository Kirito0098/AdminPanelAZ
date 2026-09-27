"""The test-suite guard refuses writes to host system paths."""

from __future__ import annotations

import io
import os
import shutil
import tarfile
from pathlib import Path

import pytest

PROBE = Path("/etc/adminpanelaz-test-guard-probe")


def _tar() -> tarfile.TarFile:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo("probe.txt")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    buffer.seek(0)
    return tarfile.open(fileobj=buffer, mode="r:gz")


@pytest.mark.parametrize(
    "action",
    [
        pytest.param(lambda tmp: PROBE.write_text("x"), id="write_text"),
        pytest.param(lambda tmp: open(PROBE, "w"), id="open-w"),
        pytest.param(lambda tmp: open(PROBE, "ab"), id="open-a"),
        pytest.param(lambda tmp: PROBE.mkdir(), id="mkdir"),
        pytest.param(lambda tmp: os.rename(tmp / "src", PROBE), id="rename"),
        pytest.param(lambda tmp: os.replace(tmp / "src", PROBE), id="replace"),
        pytest.param(lambda tmp: shutil.copy2(tmp / "src", PROBE), id="copy2"),
        pytest.param(lambda tmp: shutil.copytree(tmp, PROBE), id="copytree"),
        pytest.param(lambda tmp: shutil.move(tmp / "src", PROBE), id="move"),
        pytest.param(lambda tmp: shutil.rmtree(PROBE), id="rmtree"),
        pytest.param(lambda tmp: os.unlink(PROBE), id="unlink"),
        pytest.param(lambda tmp: _tar().extractall(path=PROBE, filter="data"), id="extractall"),
        pytest.param(lambda tmp: _tar().extract("probe.txt", path=PROBE, filter="data"), id="extract"),
        pytest.param(lambda tmp: open("/root/antizapret/adminpanelaz-test-guard-probe", "w"), id="antizapret"),
    ],
)
def test_writes_to_host_system_paths_are_refused(tmp_path, action):
    (tmp_path / "src").write_text("x")
    with pytest.raises(AssertionError, match="host path"):
        action(tmp_path)
    assert not PROBE.exists()
    assert (tmp_path / "src").exists()


def test_reads_and_tmp_writes_still_work(tmp_path):
    assert Path("/etc/hostname").read_text()
    (tmp_path / "a").write_text("x")
    os.rename(tmp_path / "a", tmp_path / "b")
    _tar().extractall(path=tmp_path, filter="data")
    assert (tmp_path / "probe.txt").read_text() == "x"
