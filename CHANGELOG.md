# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).

## [0.4.0] - 2026-07-30

### Added
- **Native agent loop** (`engine/`). A provider-agnostic tool-use loop that owns the conversation, the tool-use cycle, keep-last-N screenshot pruning, and an append-only resume journal. Every tool call writes `in_flight` before dispatch and `done`/`error` after, so a crash between them leaves the dangling line a resume keys on. Resume reads the journal tail and continues from the first uncompleted step; completed steps are never re-run.
- **Native Anthropic provider over subscription OAuth** (`engine/providers/`). Dev runs bill against a Claude subscription instead of API credit. Three auth strategies (`oauth`, `api_key`, `none`); the OAuth strategy caches the access token, refreshes on expiry and on 401, and resolves the token store per OS - the credentials file on Linux, Windows and WSL (WSL reads the Linux-side home, not `/mnt/c`), the login Keychain on macOS.
- **Shared async HTTP client** (`engine/http.py`) with retry-on-transient (429, 5xx, transport errors) and exponential back-off. Every model call and token refresh goes through it.
- **Control-plane MCP server** (`engine/tools/`), in-process and mounted beside cua, with eight tools: `todo_write`, `todo_update`, `report_progress`, `get_run_status`, `request_approval`, `ask_user`, `propose_plan`, `notify_user`.
- **Human-in-the-loop gate.** `request_approval` pauses the loop, consults the policy hook, and only then routes to the active channel; the pause is journaled as an `await_user` line on the same step. A reject or a timeout comes back as an ordinary tool result, not a crash, and the loop continues.
- **Policy hook** (`engine/policy/`) with a denylist, a risk level and four auth modes (`bypass`, `default`, `autonomous`, `paranoid`).
- **Channels** (`engine/channels/`): a CLI channel (TTY prompt, timeout, importance-to-loudness) and a desktop channel (native toast or modal, command selected per OS).
- **Acceptance runbook** at `E2E/0.4.0/e2e.md`, run live against the real endpoint: 110 enumerated cells across the loop, the eight tools, crash/resume, the policy matrix, the channels, the auth strategies and the MCP host.

### Changed
- **Default model is now `claude-opus-5`**, up from `claude-sonnet-4-6`. Bumped everywhere the default is defined - the native provider, the agent model field, the repository and agent-service defaults, the `agents` table `DEFAULT`, the manifest default and the manifest-import fallback. The advertised catalogue in `providers.yaml` moves to the current family (Opus 5, Sonnet 5, Fable 5, Opus 4.8, Sonnet 4.6, Haiku 4.5).
- `providers.yaml` gains a native `anthropic_oauth` block and sets it as `default_provider`; the legacy CLI providers are tagged `deprecated`.
- The providers discovery route treats native providers as a distinct kind - they carry no command or args.

### Fixed
- **A broken MCP server no longer takes the whole run down.** `MCPHost.connect()` awaited `list_tools()` inline with no guard, so one unreachable server raised straight out and the run never started, losing every healthy server's tools with it. Each server's start is now guarded; a failure is logged, that server is dropped, and the reason is recorded in `MCPHost.failed()`. A server-name collision still raises, because silently dropping one of two same-named servers would shadow the other's tools.
- **Journal redaction no longer destroys the token counts.** The key pattern matched the bare substring `token`, so `input_tokens`, `output_tokens` and `max_tokens` were written as `[REDACTED]` along with real credentials. Keys are now matched as whole words after normalizing camelCase and kebab-case: `accessToken`, `apiKey` and `Authorization` are still redacted, `input_tokens` and `max_tokens` survive.
- **`todo_update` accepts the vocabulary a model actually uses.** Given a plain goal the model wrote `completed` where the enum is `done`; a JSON-Schema enum is advisory, so the value reached the tool and returned an error that cost an iteration. Synonyms now map to the canonical status, and both errors name what is legal - all four statuses, and the ids that exist.
- The Anthropic endpoint rejects a `tool_result` whose content is a bare object; content is now normalized to a string or a list of content blocks.

### Notes
- The engine ships as a library. The API run endpoints still execute through the CLI executor; wiring them to the native loop is `0.4.1`, and that is what puts the loop on the product's own run path.
- The native provider refuses to start under `VADGR_MODE=production`.
- The `agents` table `DEFAULT` applies to newly created databases. Existing rows keep the model they were written with, and an agent that names its model is unaffected.
- Two findings are recorded rather than fixed, with their reason: `default` and `autonomous` produce identical outcomes in all 24 policy cells, and the gate is reached only when the model both chooses `request_approval` and self-declares `risk: "high"` - ordinary tool dispatch is not policed. Risk classes and decision tables are `0.6.0`.
- macOS Keychain and the native Windows desktop channel are proven by command and store *selection* only; that the selected command works on those hosts is owed.

### Tests
- `engine/` 110 passed (loop, pruning, journal, http, auth incl. per-OS resolution, format, provider invariants, the eight control-plane tools, policy, channels, ports).
- `api/` + `registry/` + `cli/` 850 passed, 1 skipped. No regressions.

## [0.3.0] - 2026-07-03

*Reconstructed from the diff: this release was tagged without a changelog entry.*

### Added
- **Mobile pairing.** `vadgr pair` mints a one-time token and prints a terminal QR; the same card appears in Settings under Mobile Pairing. Both encode a `vadgr://pair?...` deep link carrying host, port, token and machine name.
- **Pluggable connection transport** (`api/transport/`) selected by `VADGR_TRANSPORT`: `loopback` (default, single machine) and `tailscale`, which reaches the machine from another device over the user's own tailnet and advertises the node's MagicDNS name in the QR.
- **Two-gate access control** (`api/auth/middleware.py`) on every request: the source must be an authorized peer - a tailnet member, with loopback trusted - *and* carry a valid per-device bearer token.
- **Pairing endpoints and storage**: `POST /api/auth/pair`, `POST /api/auth/claim`, `GET` and `DELETE /api/devices`, backed by token primitives, a pairing store, a device repository and a `devices` table.
- **Mobile run-event WebSocket stream**, and the contract models the mobile app consumes: `Device`, `Pair`/`Claim`, `RunEvent`.

### Fixed
- tailscaled LocalAPI is queried over HTTP/1.0, and reached over a named pipe on native Windows.

### Notes
- Pairing needs a transport that can advertise a reachable address. On `loopback` it returns 503 by design - a localhost QR is useless to a phone - so use `VADGR_TRANSPORT=tailscale`.

### Tests
- 513 passed. Verified live over a real tailnet: pair, claim and device persisted, with gate enforcement confirmed from a second machine (401 without a token, 200 with it).

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
