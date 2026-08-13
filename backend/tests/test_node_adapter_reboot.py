from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.antizapret import AntiZapretService


def test_antizapret_reboot_calls_systemctl_no_wall():
    svc = AntiZapretService(base_path=Path("/tmp"))
    fake = MagicMock(returncode=0, stdout="ok\n", stderr="")
    with patch("app.services.antizapret.subprocess.run", return_value=fake) as run:
        out = svc.reboot()
    run.assert_called_once()
    args = run.call_args[0][0]
    assert args[:2] == ["systemctl", "reboot"]
    assert "--no-wall" in args
    assert run.call_args.kwargs.get("shell") in (None, False)
    assert "ok" in out


def test_remote_adapter_reboot_posts_endpoint():
    from app.services.node_adapter import RemoteNodeAdapter

    adapter = RemoteNodeAdapter.__new__(RemoteNodeAdapter)
    adapter._request = MagicMock(return_value={"message": "Узел перезагружается", "detail": "systemctl"})
    result = RemoteNodeAdapter.reboot(adapter)
    assert result == "systemctl"
    adapter._request.assert_called_once_with("POST", "/reboot")
