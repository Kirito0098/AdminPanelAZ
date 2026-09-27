# Design: Client portal respects VPN profile visibility

Date: 2026-09-22  
Branch: `release/2.26.0`  
Status: approved for planning

## Problem

The public client portal lists and serves all profile files for a client (e.g. both `AZ-TopTinker.ovpn` and `VPN-TopTinker.ovpn`). Admins already control **Видимость VPN-профилей** (`User.visible_vpn_profiles` / global default) for the panel, Telegram Mini App, and Telegram bot — but the portal ignores that policy. Users can download routes/protocols the admin intended to hide.

## Goal

Reuse the existing visibility policy (choice **A** / approach **1**): the client portal must list and download only files allowed by the owner's effective `visible_vpn_profiles` (same semantics as panel / Mini App / Telegram).

Example: owner Novikov has routes `["az"]` only → portal for TopTinker shows AZ profiles; VPN profiles are hidden; direct download of a VPN path returns 404.

## Non-goals

- No new portal-only visibility UI or settings.
- No per-config dashboard toggles.
- No front-end-only filtering (must be enforced on list + download).
- No change to how admins edit visibility (existing Users / default editor stays).
- Mini App / Telegram already respect the policy — out of scope except consistency checks in tests if cheap.

## Policy source

| Portal token kind | Whose policy |
|---|---|
| User portal (`u_…`) | That user (override or global default via `resolve_effective_visible_vpn_profiles`) |
| Client portal (`c_…`) | Owner of the VPN config (`owner_id`); if orphan (`owner_id` is null) → **global default** only (`get_default_visible_vpn_profiles` / effective resolve as if a normal user with `visible_vpn_profiles=None`) |

The public portal visitor is unauthenticated: **never** grant “admin sees everything”. Always apply the owner/default policy intersected with feature flags via `resolve_effective_visible_vpn_profiles` (for a real user) or the same effective default path for orphans.

## Implementation sketch

Single choke point: `backend/app/services/client_portal.py` → `_list_files_for_configs`.

1. When building each file entry, keep enough metadata for `profile_file_allowed` (`protocol` / `variant` / `path` — `enrich_profile_files` already provides variant).
2. Resolve effective policy for the config owner (or default for orphans).
3. Skip files that fail `profile_file_allowed` (or filter via `filter_profile_files` after mapping to the expected shape).
4. `build_portal_status` / payload and `read_portal_profile` / `_read_client_portal_profile` already derive the allowlist from `_list_files_for_configs` — download stays consistent without a second policy path.

Optional: cache policy per `owner_id` inside one `_list_files_for_configs` call when listing many configs for a user portal.

## Testing

- Unit/integration: owner with `routes: ["az"]` → portal file list contains AZ, not VPN; download VPN path → 404.
- Owner with full policy → both AZ and VPN present (regression).
- Orphan config → uses global default (set default to AZ-only in test → VPN filtered).
- User portal token with restricted owner → same filtering across owned clients.

## Docs

- Clarify in `docs/podpiska.md` that portal downloads respect **Видимость VPN-профилей**.
- `CHANGELOG.md` `[Unreleased]` Changed note in Russian.

## Success criteria

- Admin sets user visibility to AZ-only → that user's portal (and owned client portals) no longer offer VPN download/import.
- Crafted download URL for a hidden path returns 404.
- No new settings screens; existing Users visibility editor is the control surface.
