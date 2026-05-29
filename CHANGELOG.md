# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).

## [0.3.0] - 2026-05-29

### Added
- Bearer-token middleware (`api/auth/middleware.py`) — pure ASGI middleware
  that enforces `Authorization: Bearer <token>` on every non-localhost
  HTTP request. Loopback peers bypass auth so the CLI and frontend
  served on localhost are unchanged.
- Default token bootstrap at `~/.config/vadgr/token` (chmod 0600).
  Generated automatically on first start via `load_or_create_default_token`.
- `POST /api/auth/pair` — mints a one-time pairing token and returns
  `{host, port, token, machine_name}` for the desktop UI to encode as a QR.
- `POST /api/auth/claim` — a mobile/tailnet device exchanges the pairing
  token for a long-lived persistent token. The token hash is stored in
  the new `devices` table; the plaintext token is returned only once.
- `GET /api/devices` — list paired devices (machine_name, paired_at,
  last_seen). No token material in the response.
- `DELETE /api/devices/{id}` — revoke a device. The device's persistent
  token immediately stops authenticating.
- `WS /api/runs/{run_id}/stream` — mobile-friendly WebSocket that
  streams the same run events as the existing `/api/ws/runs/{run_id}`
  channel. Accepts auth via `Authorization` header or `?token=` query
  string. Supported event types include `started`, `tool_call`,
  `output`, `paused`, `completed`, `failed`.
- `devices` table (id, machine_name, token_hash, paired_at, last_seen)
  added to the schema, plus `idx_devices_token_hash` index.
- `VADGR_BIND_TAILSCALE` env var (read by `cli/bind.py`). When set to a
  truthy value (`1`, `true`, `yes`, `on`), `vadgr start` and `vadgr api`
  pass `--host 0.0.0.0` to uvicorn so the API is reachable on the
  tailnet interface. Default remains `127.0.0.1`.
- Frontend: "Mobile Pairing" card in Settings. Renders the pairing
  token as a QR code (`qrcode.react`) plus the raw token for manual
  entry. Encodes a `vadgr://pair?...` URI for mobile deep-link handling.

### Schema migration
- The `devices` table is added via the existing inline-migration pattern
  in `api/persistence/database.py` (idempotent `CREATE TABLE IF NOT
  EXISTS`). The repo does not use Alembic; the table is created
  automatically on first start.

### Upgrade notes
- 0.2.x → 0.3.0 is **additive**: existing endpoints behave the same and
  no data is migrated. On first start a bearer token is generated at
  `~/.config/vadgr/token` (chmod 0600). This token is required only
  when reaching the API from a non-loopback peer (tailnet / mobile).
- To expose vadgr to your tailnet: `export VADGR_BIND_TAILSCALE=1` then
  `vadgr restart`.

### Tests
- Baseline (post-0.2.0): 453 + 179 + 150 = 782 passed, 1 skipped.
- After this version: 472 + 179 + 150 = 801 passed, 1 skipped.
  +19 new tests (auth middleware, pair endpoint, devices endpoint,
  run-stream WS, tailscale bind). 0 regressions.

## [0.2.0] - 2026-05-21

### Removed
- TypeScript Discord gateway: entire `vadgr/gateway/` directory (17 files — adapters, router, security, server, API client, tests, `package.json`, `tsconfig.json`).
- CLI gateway commands: `cli/commands/gateway_cmd.py`. `vadgr gateway` is no longer a registered command.
- API gateway endpoints: removed the `DiscordUpdate` model and both `/messaging-gateway*` endpoints from `api/routes/settings.py`. Supporting service module `api/services/gateway_setup.py` deleted.
- Frontend gateway UI: `frontend/src/hooks/useMessagingGateway.ts` deleted; the Messaging Gateway `<Card>` block (~176 lines) removed from `frontend/src/pages/Settings.tsx`.
- All gateway references from `README.md` (module section, tree-view entry, "Connect via Discord" wording).

### Added
- `api/tests/test_gateway_decommissioned.py` — 10 guardrail tests that fail if any gateway artifact is re-introduced (import fails, no `/messaging-gateway` routes registered, `vadgr gateway --help` errors, etc.).

### Upgrade notes
- **Operators must manually delete `~/.forge/gateway.json`, `~/.forge/pids/gateway.pid`, and `~/.forge/gateway.log` after upgrading.** Gateway state lived in `~/.forge/gateway.json` (mode 0600 — Discord bot token + enable flag), never in the SQLite schema. The 0.2.0 codebase no longer reads or writes that file.
- **Discord bot tokens stored in `~/.forge/gateway.json` are lost on upgrade.** Back up the file before upgrading if you need to preserve them.
- No Alembic migration ships — no `gateway_*` tables ever existed in the schema.

### Tests
- Baseline (`0.1.0`): 443 + 179 + 150 = 772 passed, 1 skipped.
- After this version: 453 + 179 + 150 = 782 passed, 1 skipped. +10 new guardrail tests, 0 regressions.

## [0.1.0] - 2026-05-21

### Added
- Initial tagged release. Establishes the baseline before the gateway decommission. Captures the current state of the repository: API (FastAPI + engine + persistence + websocket) + CLI (Click HTTP client) + frontend (React + Vite dashboard) + forge (workflow + skills generator) + registry (`.agnt` package manager) + Discord gateway (TypeScript, decommissioned in 0.2.0).
