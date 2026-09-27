# User-level subscription (Fider #28)

**Date:** 2026-09-19  
**Status:** Draft for review  
**Source:** [Fider #28 — Улучшение Подписки](https://claymore0098.fider.io/posts/28/uluchshenie-podpiski)  
**Branch:** `release/2.26.0`  
**Approach:** User Subscription Policy (source of truth on `User`, cascade to owned clients)

## Problem

Subscription today is client-centric: `access_until`, blocks, portal tokens, and unlock redemption are keyed by `client_name` (+ node/protocol). That conflicts with the panel model where a self-service **User** owns multiple VPN clients via `VpnConfig.owner_id`. Admins must repeat the same access date per client; expiry/renewal does not cascade; Telegram reminders still track certificate expiry, not access period.

## Goals

1. **User-level access period** — one `access_until` on the User; cascade to all owned clients.
2. **Cascade block/unblock** — expiry disables configs and portal access; renewal clears only `access_expired` blocks (manual blocks stay).
3. **Forbid new configs** when the user's subscription is expired/blocked by access.
4. **Unlock at user level** — redeem once → extend User → unlock/extend all owned configs (respecting manual blocks).
5. **Portal** — both user-scoped link (all owned clients) and existing client-scoped links.
6. **Telegram** — separate reminders for access expiry and certificate expiry (both kept).
7. **Admin safety** — per-client edits allowed with explicit warning + conflict guard / confirm override; sync-from-user action.

## Non-goals

- Making the self-service user an "admin of their clients" (RBAC unchanged).
- Full billing/payment product or a separate BillingAccount entity.
- Removing client-level policies or client portal tokens.

## Architecture

```text
User.access_until  (source of truth)
        │
        ▼
 cascade service / access_expiry_worker
        │
        ├── owned VpnConfig(s) on all nodes
        │       └── per-protocol access policies
        │             block_reason=access_expired only
        │             (skip permanent / other manual reasons)
        │
        ├── create-config API gate → 403 subscription_expired
        │
        ├── Unlock redeem → extend User → same cascade
        │
        └── Portal
              ├── UserPortalToken → all owned clients
              └── ClientPortalToken → one client (unchanged)
```

Telegram: new access-expiry notify events alongside existing cert-expiry events; independent subscription toggles.

## Data model

### `users` columns

| Column | Type | Notes |
|--------|------|--------|
| `access_until` | `DateTime` nullable | UTC naive, same convention as access policies. `NULL` = unlimited (no subscription-driven cascade). |

Derived state: subscription expired when `access_until is not None and access_until <= now`. No separate user block flag required for v1.

### `user_portal_tokens`

| Column | Notes |
|--------|--------|
| `token` | Unique public token |
| `user_id` | FK → users |
| `created_by_user_id` | Nullable |
| `created_at` | |
| `revoked_at` | Nullable; one active token per user (partial unique like client tokens) |

### Unchanged / retained

- `openvpn_access_policy`, `wg_access_policy`, `amneziawg2_access_policies` — keep `access_until` and block fields.
- `client_portal_tokens` — keep.
- `unlock_codes` — redeem target is **User** when the subject has an owner; client-only redeem only for orphan clients (no `owner_id`).

### Unlock redemptions

Log `user_id` on redemption when cascading to a User (optionally record which clients were touched). Rules:

1. If redeem context resolves to a User (direct user portal, or client with `owner_id`) → always extend that User and cascade.
2. If client has no owner → keep legacy client-level redeem only (orphan path).
3. Do not silently redeem to a single client when an owner exists.

## Migration

1. For each User that owns configs: set `User.access_until = max(non-null access_until across owned clients' policies)` when any exist; else leave `NULL`.
2. Orphan clients (`owner_id` missing / no owner) — unchanged client-level behavior only.
3. Do **not** auto-create `user_portal_tokens`; admin creates explicitly.
4. Existing unlock codes keep working; when owner exists, redemption extends the User (not a single client).

## Flows

### Expiry

`access_expiry_worker` (or an adjacent pass) finds Users with expired `access_until`, then for each owned client applies `access_expired` on policies **unless** a permanent/manual block with another reason is active. Create-config APIs refuse with `403` + code `subscription_expired`. User and client portal pages for that owner show expired/blocked state for config download (unlock redeem still allowed).

Panel login for expired users remains allowed so they can see status and redeem an unlock code.

### Admin extends user

Setting/moving `User.access_until` into the future runs cascade: clear only `access_expired` on owned clients; align client policy `access_until` to the User value (user-edit always syncs down).

### Unlock

Redeem (portal / mini-app / API) → validate code →  
`User.access_until = max(now, User.access_until or now) + grant_days` → same unexpire cascade.  
Redeem from a client portal link resolves the client's `owner_id` and extends that User.

### Portal

- `/p/{userToken}` — list all owned clients; download paths analogous to current portal payload, multi-client.
- `/p/{clientToken}` — unchanged single-client behavior.
- Unlock redeem from either link type extends the **User** (owner).

### Telegram

Add access-expiry reminders mirroring the cert pair: admin broadcast + user/self-service personal reminder, driven by `User.access_until` and a day threshold (same pattern as `self_service_reminder_cert_days_threshold`). Keep existing cert reminders; toggles independent.

## Admin conflict guard

When a User has `access_until` set and an admin changes a client's `access_until` to a different value:

1. Without `confirm_override=true` → `409` with diff (user vs client).
2. With confirm → allow divergent client date; UI shows persistent warning that client diverges from user subscription.
3. Action **«Синхронизировать с юзером»** — set client policy dates from `User.access_until`; do **not** clear manual blocks.

## Error handling

| Situation | Response |
|-----------|----------|
| Create config while user subscription expired | `403` `subscription_expired` |
| Unlock invalid/revoked/exhausted | Existing unlock errors |
| Client-link redeem but client has no owner | Clear error: cannot attach renewal to a user |
| Client date change conflicts with user without confirm | `409` + diff payload |

## Edge cases

| Case | Behavior |
|------|----------|
| Client without owner | Client-level only |
| New client under user with active `access_until` | On create, set policy `access_until = User.access_until` |
| New client while user already expired | Create forbidden |
| Manual client block | Not cleared by user unlock/extend |
| Admin clears manual block but user still expired | Worker re-applies `access_expired` |
| `User.access_until = NULL` | Unlimited; no subscription cascade |
| Multi-node / multi-protocol | Cascade all owned `VpnConfig` rows |
| HA | Replicate the same access ops used today for unlock/expiry |

## Testing (minimum)

1. User expiry → all owned clients `access_expired`; create forbidden.
2. User unlock → all owned unexpire; permanent/manual blocks remain.
3. Client override without confirm → `409`; with confirm → OK.
4. Sync-from-user aligns dates; does not clear manual blocks.
5. User portal payload lists all owned clients; client portal stays single-client.
6. TG access reminder is separate from cert (both can fire).
7. Migration: `User.access_until = max(children)`.

## Out of scope for follow-ups (explicit)

- Payments / invoices / plans catalog.
- Changing self-service RBAC beyond subscription create gate.
- Removing cert-based reminders.
