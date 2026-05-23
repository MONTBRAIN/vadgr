# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).

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
