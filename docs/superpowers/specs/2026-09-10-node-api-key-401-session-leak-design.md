# Design: Node API-key 401 must not kill admin session

**Date:** 2026-09-10  
**Status:** Approved for planning (brainstorming)  
**Reporter context:** Operator locked out of Nodes/settings when multiple remote nodes have rotated API keys; UI shows session-style auth failure (`Not authenticated`); workaround is race the UI to local/main settings.

## Problem

Two auth planes are conflated:

1. **Admin session** — JWT Bearer + refresh cookie between browser and panel.
2. **Node agent key** — `X-Node-Key` between panel and `node_agent` / `proxy_agent`.

When a remote agent rejects the key, it returns **HTTP 401**. `RemoteNodeAdapter` / `ProxyNodeAdapter` re-raise `HTTPException` with the **same status code** to the browser. The SPA treats **any** panel API 401 as expired session: calls `/auth/refresh`, may `clearAccessToken()`, and subsequent requests without Bearer surface FastAPI/OAuth2 **`Not authenticated`**. The operator cannot reach the Nodes UI to fix keys — a closed loop.

Amplifiers:

- Dashboard / monitoring / configs call `get_active_adapter()` and surface agent failures directly (unlike `check_node_health`, which catches `HTTPException` and returns offline).
- `AuthContext.silentRefresh` calls `POST /auth/refresh` **outside** the `refreshAccessToken()` in-flight mutex in `http.ts`, racing token rotation (`rotate_refresh_token` revokes the previous cookie).

## Goals

1. Invalid / rejected **node** credentials never look like an expired **admin** session.
2. With bad remote keys, admin stays logged in and can open **Узлы** (and settings) to update keys.
3. All refresh-cookie rotations share **one** in-flight path (no concurrent rotate races from silent refresh vs apiFetch).
4. Defense in depth on the SPA if a legacy 401 with node-key wording still appears during rollout.

## Non-goals

- Auto-healing or automatic re-sync of agent keys beyond existing rotation flows.
- New UX wizard for “fix node keys”.
- Changing `node_agent` / `proxy_agent` error payloads.
- Custom HTTP status codes (424/460/etc.).
- Broader auth redesign (session model, WebAuthn, etc.).

## Decisions (locked)

| Topic | Choice |
|-------|--------|
| Scope | **C** — backend remap + frontend guard + shared refresh mutex |
| Approach | **1** — agent 401/403 → panel **502**; shared `refreshAccessToken`; soft 401 guard by detail text |
| Agent 401 | Map to **502** with existing Russian detail about `X-Node-Key` |
| Agent 403 | Map to **502** with existing allowlist detail (avoid colliding with panel admin **403**) |
| Missing key / connect errors | Unchanged (**503** and existing messages) |
| JWT / missing Bearer 401 | Unchanged (session flow) |
| Custom status codes | Out of scope |

## Architecture

```
Browser  --JWT-->  Panel API  --X-Node-Key-->  node_agent / proxy_agent
   ^                  |
   |                  +-- on agent 401/403: raise HTTP 502 (node fault), NOT 401
   |
   +-- apiFetch: only session-refresh on real session 401
   +-- silentRefresh / apiFetch / blob helpers: one refreshAccessToken() mutex
```

### Backend

In `RemoteNodeAdapter._request` / `_request_bytes` and the equivalent path in `ProxyNodeAdapter`:

- If upstream status is **401** or **403**, raise `HTTPException(status_code=502, detail=…)`.
- Keep current detail strings:
  - 401 → `Неверный API-ключ узла (заголовок X-Node-Key)`
  - 403 → allowlist message (node vs proxy wording as today)
- Other ≥400 statuses continue to pass through `response.status_code` as today (except the 401/403 remap above).

Call sites that already catch `HTTPException` (e.g. `check_node_health`) keep working: they still show offline + error text.

### Frontend — refresh mutex

- Single entry: `refreshAccessToken()` in `frontend/src/api/http.ts` (existing `refreshPromise`).
- `AuthContext.silentRefresh` must call `refreshAccessToken()` instead of raw `fetch(`${API_BASE}/auth/refresh`)`.
- On refresh failure, existing behavior: clear access token / return null (session genuinely dead).

### Frontend — 401 session guard (belt and suspenders)

In `apiFetchAtBase` (and mirrored 401 handlers in `configs.ts` / `awg2.ts`, preferably via a shared helper):

- Before treating 401 as session expiry: if response body `detail` (string or first list element) matches node-key failure (substring checks for `X-Node-Key` and/or `Неверный API-ключ`), **do not** call `refreshAccessToken` / **do not** `clearAccessToken`; throw `ApiError` as a normal failure.
- All other 401s keep current session refresh / clear behavior.

## Error handling / UX

| Condition | HTTP to browser | Session | Operator sees |
|-----------|-----------------|---------|---------------|
| Bad JWT / no Bearer | 401 | logout / login | session auth message |
| Bad node API key | **502** | stays | node key / offline style error |
| Agent IP allowlist reject | **502** | stays | allowlist detail |
| Node unreachable / no key stored | 503 (unchanged) | stays | existing messages |

Success criterion (reporter scenario): two remotes with rotated keys → admin remains authenticated → Nodes page reachable → health/errors visible → keys can be updated.

## Testing

### Backend

- Unit/adapter tests with mocked upstream response **401** → panel raises **502** + key detail.
- Same for **403** → **502** + allowlist detail.
- Regression: connection errors still **503**; missing stored key still **503**.

### Frontend

- Helper/unit: node-key-like 401 detail → no `clearAccessToken`, no refresh.
- Ordinary 401 → still triggers refresh path.
- Two concurrent `refreshAccessToken()` calls → single `fetch` to `/auth/refresh`.
- `AuthContext` silent path uses shared refresh (covered by using the same function; optional light test if practical).

## Files (expected)

| File | Role |
|------|------|
| `backend/app/services/node_adapter.py` | Remap 401/403 → 502 |
| `backend/app/services/proxy_node_adapter.py` | Remap 401/403 → 502 |
| `backend/tests/…` | Adapter remap coverage |
| `frontend/src/api/http.ts` | Shared refresh; 401 guard helper |
| `frontend/src/context/AuthContext.tsx` | silentRefresh → `refreshAccessToken` |
| `frontend/src/api/configs.ts` | Use shared 401 guard |
| `frontend/src/api/awg2.ts` | Use shared 401 guard |
| `frontend` unit tests (existing Vitest patterns) | Guard + mutex |

## Rollout

- Single PR/change set; no feature flag required.
- After deploy, old “logout on bad node key” behavior disappears even before all tabs refresh, once panel process serves remapped statuses.
- SPA guard covers any transitional 401 still in flight.

## Open risks (accepted)

- Operators/scripts that keyed off HTTP **401** for “bad node key” must treat **502** + detail instead (unlikely; internal panel API).
- Substring guard is Russian/English-detail based; primary fix is status remap.
