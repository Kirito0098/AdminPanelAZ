"""AAAA answer switch: managed NODATA block in custom.lua / custom2.lua."""

from __future__ import annotations

import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

from app.services.kresd_aaaa import NODATA_BLOCK, aaaa_mode, with_aaaa_nodata

UPSTREAM_CUSTOM = """-- Custom query policies for AntiZapret VPN
-- Resolve domains via custom DNS only
--policy.add(policy.suffix(policy.STUB({'8.8.8.8', '8.8.4.4'}), {
--    todname('example.com'),
--}))
"""


@pytest.mark.parametrize("content", ["", UPSTREAM_CUSTOM])
def test_file_without_block_is_zero(content):
    assert aaaa_mode(content) == "zero"


def test_enable_appends_block_after_user_content():
    updated = with_aaaa_nodata(UPSTREAM_CUSTOM, True)

    assert updated == UPSTREAM_CUSTOM + "\n" + NODATA_BLOCK
    assert aaaa_mode(updated) == "nodata"


def test_enable_on_empty_file_writes_only_block():
    assert with_aaaa_nodata("", True) == NODATA_BLOCK


def test_disable_restores_original_content():
    assert with_aaaa_nodata(with_aaaa_nodata(UPSTREAM_CUSTOM, True), False) == UPSTREAM_CUSTOM
    assert with_aaaa_nodata(with_aaaa_nodata("", True), False) == ""


def test_missing_trailing_newline_is_normalised_on_round_trip():
    enabled = with_aaaa_nodata("-- x", True)

    assert enabled == "-- x\n\n" + NODATA_BLOCK
    assert with_aaaa_nodata(enabled, False) == "-- x\n"


def test_disable_keeps_user_lines_after_block():
    content = with_aaaa_nodata(UPSTREAM_CUSTOM, True) + "net.outgoing_v4('1.2.3.4')\n"

    assert with_aaaa_nodata(content, False) == UPSTREAM_CUSTOM + "net.outgoing_v4('1.2.3.4')\n"


@pytest.mark.parametrize("enabled", [True, False])
def test_repeated_call_changes_nothing(enabled):
    once = with_aaaa_nodata(UPSTREAM_CUSTOM, enabled)

    assert with_aaaa_nodata(once, enabled) == once


@pytest.mark.parametrize(
    "content",
    [
        NODATA_BLOCK.replace("86400", "3600"),
        NODATA_BLOCK.split("\n", 1)[0] + "\n",
        UPSTREAM_CUSTOM + "-- [ADMINPANEL-AAAA-NODATA-END]\n",
        NODATA_BLOCK + NODATA_BLOCK,
    ],
)
def test_hand_edited_block_is_custom_and_left_alone(content):
    assert aaaa_mode(content) == "custom"
    with pytest.raises(ValueError):
        with_aaaa_nodata(content, True)
    with pytest.raises(ValueError):
        with_aaaa_nodata(content, False)


_KRESD_CONF = """
net.listen('127.0.0.1', {port}, {{kind = 'dns'}})
cache.open(10 * MB, 'lmdb://{cache}')
trust_anchors.remove('.')
for _, item in ipairs(policy.special_names) do
\tpolicy.add(item.cb)
end
local zero_aaaa_answer = policy.ANSWER({{[kres.type.AAAA] = {{rdata = kres.str2ip('::'), ttl = 86400}}}})
local function match_query_type(action, target_qtype)
\treturn function (state, query)
\t\tif query.stype == target_qtype then return action else return nil end
\tend
end
policy.add(match_query_type(zero_aaaa_answer, kres.type.AAAA))
policy.add(policy.all(policy.FLAGS({{'NO_EDNS', 'NO_0X20'}})))
dofile('{custom}')
policy.add(policy.all(policy.DENY))
"""


def _free_port() -> int:
    """Port free on 127.0.0.1 for both UDP and TCP (kind='dns' binds both)."""
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
            tcp.bind(("127.0.0.1", 0))
            port = tcp.getsockname()[1]
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                try:
                    udp.bind(("127.0.0.1", port))
                except OSError:
                    continue
        return port


def _dig_aaaa(port: int, name: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["dig", "+time=1", "+tries=1", "@127.0.0.1", "-p", str(port), name, "AAAA"],
        capture_output=True,
        text=True,
        check=False,
    )


def _aaaa_answers(tmp_path: Path, custom: str, names: list[str]) -> dict[str, str]:
    port = _free_port()
    custom_path = tmp_path / "custom.lua"
    custom_path.write_text(custom, encoding="utf-8")
    (tmp_path / "cache").mkdir()
    conf = tmp_path / "kresd.conf"
    conf.write_text(_KRESD_CONF.format(port=port, cache=tmp_path / "cache", custom=custom_path), encoding="utf-8")
    log_path = tmp_path / "kresd.log"
    with log_path.open("wb") as log:
        proc = subprocess.Popen(["kresd", "-n", "-c", str(conf), str(tmp_path)], stdout=log, stderr=log)
    try:
        deadline = time.monotonic() + 10
        while True:
            result = _dig_aaaa(port, names[0])
            if result.returncode == 0:
                break
            if proc.poll() is not None:
                pytest.fail(f"kresd exited with {proc.returncode}:\n{log_path.read_text(errors='replace')}")
            if time.monotonic() > deadline:
                pytest.fail(f"kresd did not answer:\n{result.stdout}\n{log_path.read_text(errors='replace')}")
            time.sleep(0.2)
        return {names[0]: result.stdout} | {name: _dig_aaaa(port, name).stdout for name in names[1:]}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


@pytest.mark.skipif(not (shutil.which("kresd") and shutil.which("dig")), reason="kresd and dig are required")
@pytest.mark.parametrize("nodata", [False, True])
def test_kresd_answers_aaaa_by_block(tmp_path: Path, nodata: bool):
    answers = _aaaa_answers(tmp_path, with_aaaa_nodata(UPSTREAM_CUSTOM, nodata), ["example.com", "localhost"])

    ordinary, localhost = answers["example.com"], answers["localhost"]
    assert "status: NOERROR" in ordinary
    assert ("IN\tAAAA\t::\n" in ordinary) is not nodata
    assert ("IN\tSOA\t. . 1 1 1 1 86400" in ordinary) is nodata
    assert "status: NOERROR" in localhost
    assert "IN\tAAAA\t::1\n" in localhost
