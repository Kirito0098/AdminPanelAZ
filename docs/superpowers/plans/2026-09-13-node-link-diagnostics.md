# Node Link Diagnostics + Push full UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stable node link error codes, richer `/health` (agent 1.8.0), panel «Связь» diagnostics, Push full preflight/progress/summary without changing wipe semantics.

**Architecture:** Central `node_link_errors` classifier used by remote adapters; health payload gains `started_at`/`uptime_sec`/`listen_tls`; health worker persists link meta; Push full adds link preflight, stage labels, post-success health refresh.

**Tech Stack:** FastAPI, httpx, React/TS, pytest, vitest

## Global Constraints

- NODE_AGENT_VERSION → **1.8.0**; PROXY_AGENT_VERSION → **1.1.0** (health parity)
- Agent auth failures → HTTP **502** with `detail.code=node_auth` (never panel-session 401)
- Do not change Push full wipe-and-replace order/semantics
- Old agents without new health fields must degrade gracefully

---

### Task 1: Classifier + agent health 1.8.0

**Files:**
- Create: `backend/app/services/node_link_errors.py`
- Create: `backend/tests/test_node_link_errors.py`
- Modify: `backend/app/services/node_health.py`
- Modify: `backend/node_agent/main.py` (pass `listen_tls`)
- Modify: `backend/proxy_agent/__init__.py`, `backend/proxy_agent/main.py`
- Modify: `backend/app/services/node_adapter.py` (`_request` / `_request_bytes`)
- Modify: `backend/app/services/proxy_node_adapter.py` (`_request`)

- [ ] Step 1: Failing tests for classifier codes + health fields
- [ ] Step 2: Implement classifier + health payload + wire adapters
- [ ] Step 3: pytest pass; commit

### Task 2: Panel health meta + FE «Связь»

**Files:**
- Modify: `backend/app/services/node_manager.py` (`check_node_health`, `update_node_from_health`)
- Modify: `frontend/src/api/http.ts` + `httpAuth.test.ts`
- Modify: `frontend/src/components/nodes/nodeHelpers.ts` + `NodeCard.tsx`
- Tests: backend unit for meta; FE unit for auth detail code

- [ ] Step 1: Failing tests
- [ ] Step 2: Persist `last_health_ok_at`, `last_link_error`, `expected_tls`, `tls_mismatch`; FE block + code-aware auth guard
- [ ] Step 3: commit

### Task 3: Push full UX

**Files:**
- Modify: `backend/app/services/node_sync/push_full.py`
- Modify: `backend/tests/test_node_sync_push_full.py`
- Optionally: `frontend/src/lib/haSyncSummary.ts` if summary needs `failed_step`

- [ ] Step 1: Tests for preflight block + progress stage labels + health refresh call
- [ ] Step 2: Implement
- [ ] Step 3: commit

### Task 4: Docs

**Files:** CHANGELOG.md, README.md (agent 1.8.0)

- [ ] Step 1: Document under Unreleased / Fixed+Changed
- [ ] Step 2: commit
