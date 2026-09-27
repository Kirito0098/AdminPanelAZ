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


def _free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _aaaa_answer(tmp_path: Path, custom: str) -> str:
    port = _free_udp_port()
    custom_path = tmp_path / "custom.lua"
    custom_path.write_text(custom, encoding="utf-8")
    (tmp_path / "cache").mkdir()
    conf = tmp_path / "kresd.conf"
    conf.write_text(_KRESD_CONF.format(port=port, cache=tmp_path / "cache", custom=custom_path), encoding="utf-8")
    proc = subprocess.Popen(
        ["kresd", "-n", "-c", str(conf), str(tmp_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        deadline = time.monotonic() + 10
        while True:
            result = subprocess.run(
                ["dig", "+time=1", "+tries=1", "@127.0.0.1", "-p", str(port), "example.com", "AAAA"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 or time.monotonic() > deadline:
                return result.stdout
            time.sleep(0.2)
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.mark.skipif(not (shutil.which("kresd") and shutil.which("dig")), reason="kresd and dig are required")
@pytest.mark.parametrize(("nodata", "zero_answer"), [(False, True), (True, False)])
def test_kresd_answers_aaaa_by_block(tmp_path: Path, nodata: bool, zero_answer: bool):
    answer = _aaaa_answer(tmp_path, with_aaaa_nodata(UPSTREAM_CUSTOM, nodata))

    assert "status: NOERROR" in answer
    assert ("IN\tAAAA\t::" in answer) is zero_answer
    assert ("IN\tSOA\t. . 1 1 1 1 86400" in answer) is nodata
