import json
import os
from unittest.mock import MagicMock, patch

from app.services import awg2
from app.services.node_adapter import LocalNodeAdapter


def _fake_install_process(lines: list[str], return_code: int = 0) -> MagicMock:
    proc = MagicMock()
    proc.stdout.readline.side_effect = [*lines, ""]
    proc.wait.return_value = return_code
    proc.poll.return_value = return_code
    return proc


def test_build_install_argv_has_no_install_base():
    argv = awg2.build_install_argv(
        "install",
        preset="high",
        template="web",
        mtu=1280,
        fp="firefox",
    )

    command = " ".join(argv)
    assert "install.sh" in command
    assert "--no-bot" in command
    assert "--preset" in command
    assert "high" in command
    assert "--template" in command
    assert "web" in command
    assert "--fp" in command
    assert "firefox" in command
    assert "--install-base" not in command
    assert "--mtu" not in command


def test_build_update_argv():
    argv = awg2.build_install_argv(
        "update",
        preset="high",
        template="web",
        mtu=1280,
        fp="firefox",
    )

    command = " ".join(argv)
    assert "install.sh" in command
    assert "--update" in command
    assert "--no-bot" not in command
    assert "--preset" not in command
    assert "--template" not in command
    assert "--fp" not in command
    assert "--install-base" not in command
    assert "--mtu" not in command


def test_install_stream_errors_when_base_missing():
    lock_handle = MagicMock()

    with (
        patch("app.services.awg2._acquire_install_lock", return_value=lock_handle),
        patch.object(awg2, "base_installed", return_value=False),
        patch("app.services.awg2.subprocess.Popen") as popen,
    ):
        events = list(
            awg2.iter_install_stream_events(
                "install",
                preset="medium",
                template="web",
                mtu=1360,
            )
        )

    assert popen.called is False
    assert [event["event"] for event in events] == ["error"]
    assert "SSH" in events[0]["detail"]
    lock_handle.close.assert_called_once()


def test_install_lock_rejects_concurrent():
    lock_handle = MagicMock()
    proc = MagicMock()
    proc.stdout.readline.side_effect = ["hello\n", ""]
    proc.wait.return_value = 0
    proc.poll.return_value = 0

    with (
        patch("app.services.awg2._acquire_install_lock", side_effect=[lock_handle, None]),
        patch("app.services.awg2.subprocess.Popen", return_value=proc),
    ):
        first = awg2.iter_install_stream_events("update")
        start_event = next(first)
        second_events = list(awg2.iter_install_stream_events("update"))
        first_tail = list(first)

    assert start_event["event"] == "start"
    assert [event["event"] for event in second_events] == ["error"]
    assert "занят" in second_events[0]["detail"].lower()
    assert [event["event"] for event in first_tail] == ["log", "done"]
    lock_handle.close.assert_called_once()


def test_awg2_service_exposes_install_stream_method():
    """C1 regression: both call sites use the service seam, not the module function."""
    assert callable(getattr(awg2.Awg2Service, "iter_install_stream_events", None))


def test_local_node_adapter_install_stream_uses_real_service():
    """C1 regression: no `Awg2Service` mock, so a missing method surfaces as AttributeError."""
    adapter = LocalNodeAdapter(service=MagicMock(), warper=MagicMock())
    lock_handle = MagicMock()

    with (
        patch("app.services.awg2._acquire_install_lock", return_value=lock_handle),
        patch("app.services.awg2.subprocess.Popen", return_value=_fake_install_process(["update ok\n"])),
    ):
        events = list(adapter.awg2_iter_install_stream("update"))

    assert [event["event"] for event in events] == ["start", "log", "done"]
    assert events[0]["mode"] == "update"
    assert events[1]["line"] == "update ok"
    assert events[2]["success"] is True


def test_node_agent_install_stream_route_streams_events(monkeypatch):
    """Task 2 deferred minor: exercise the agent route against a real `Awg2Service`."""
    monkeypatch.setenv("NODE_AGENT_MODE", "dev")
    monkeypatch.setenv("NODE_AGENT_API_KEY", "n" * 32)
    os.environ.pop("NODE_AGENT_ALLOWED_IPS", None)

    from fastapi.testclient import TestClient

    import node_agent.main as agent_main

    lock_handle = MagicMock()
    with (
        patch("app.services.awg2._acquire_install_lock", return_value=lock_handle),
        patch("app.services.awg2.subprocess.Popen", return_value=_fake_install_process(["agent line\n"])),
    ):
        client = TestClient(agent_main.app)
        response = client.get(
            "/awg2/install/stream",
            params={"mode": "update"},
            headers={"X-Node-Key": agent_main.NODE_AGENT_API_KEY},
        )

    assert response.status_code == 200
    events = [
        json.loads(line[len("data: ") :])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert [event["event"] for event in events] == ["start", "log", "done"]
    assert events[1]["line"] == "agent line"
