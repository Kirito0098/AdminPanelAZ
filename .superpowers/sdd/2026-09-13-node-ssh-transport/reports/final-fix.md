## Final transport fix pass

- Moved SSH discovered host-key persistence off the pool event-loop thread. `ensure()` now returns the local port plus optional discovered host-key text, and caller-thread adapter setup persists metadata through the ORM session.
- Locked SSH passphrase updates so blank edit submissions no longer clear the stored encrypted passphrase. The frontend now omits `ssh_passphrase` when the edit field is blank.
- Direct `enable-mtls` and `disable-mtls` endpoints now reject SSH-transport nodes with a 400 instructing users to switch transport via the node picker instead.
- Verification: `backend/.venv/bin/pytest tests/test_ssh_tunnel_pool.py tests/test_node_transport_api.py tests/test_node_transport.py` passed; `frontend npm run typecheck` passed.
