"""Remove the runtime peers of many WireGuard/AWG clients with one ``set`` per interface."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterable

PEERS_PER_COMMAND = 200
# Agent-side cap of one block-batch request; the panel splits longer lists.
CLIENTS_PER_REQUEST = 5000
NO_PEERS_ERROR = "Пиры клиента не найдены"

Peer = tuple[str, str]
Runner = Callable[[list[str]], subprocess.CompletedProcess]


def _stderr(result: subprocess.CompletedProcess, tool: str) -> str:
    return (result.stderr or result.stdout or "").strip() or f"{tool} set failed"


def _remove_on_interface(tool: str, interface: str, keys: list[str], run: Runner) -> dict[str, str]:
    """Return ``{public_key: stderr}`` for peers that could not be removed."""
    failed: dict[str, str] = {}
    for start in range(0, len(keys), PEERS_PER_COMMAND):
        chunk = keys[start : start + PEERS_PER_COMMAND]
        args = [tool, "set", interface]
        for key in chunk:
            args.extend(["peer", key, "remove"])
        if run(args).returncode == 0:
            continue
        for key in chunk:
            result = run([tool, "set", interface, "peer", key, "remove"])
            if result.returncode != 0:
                failed[key] = _stderr(result, tool)
    return failed


def block_peers_batch(peers_by_client: dict[str, list[Peer]], *, tool: str, run: Runner) -> dict[str, dict]:
    """Per-client results in the ``block_client_runtime`` shape."""
    keys_by_interface: dict[str, list[str]] = {}
    for peers in peers_by_client.values():
        for interface, key in peers:
            keys = keys_by_interface.setdefault(interface, [])
            if key not in keys:
                keys.append(key)
    failed: dict[Peer, str] = {}
    for interface, keys in keys_by_interface.items():
        for key, stderr in _remove_on_interface(tool, interface, keys, run).items():
            failed[(interface, key)] = stderr

    results: dict[str, dict] = {}
    for client_name, peers in peers_by_client.items():
        if not peers:
            results[client_name] = {
                "success": False,
                "removed_count": 0,
                "blocked": 0,
                "error_count": 1,
                "errors": [{"interface": None, "stderr": NO_PEERS_ERROR}],
            }
            continue
        errors = [
            {"interface": interface, "peer_public_key": key, "stderr": failed[(interface, key)]}
            for interface, key in peers
            if (interface, key) in failed
        ]
        removed_count = len(peers) - len(errors)
        results[client_name] = {
            "success": removed_count > 0,
            "removed_count": removed_count,
            "blocked": removed_count,
            "error_count": len(errors),
            "errors": errors,
        }
    return results


def group_peers_by_client(
    client_names: Iterable[str],
    peer_specs: Iterable[dict],
    normalize: Callable[[str], str],
) -> dict[str, list[Peer]]:
    """Pick the peers of ``client_names`` out of every parsed peer spec."""
    grouped: dict[str, list[Peer]] = {normalize(name): [] for name in client_names if normalize(name)}
    for spec in peer_specs:
        name = normalize(spec.get("client_name", ""))
        interface = spec.get("interface_name")
        key = spec.get("peer_public_key")
        if name in grouped and interface and key:
            grouped[name].append((interface, key))
    return grouped
