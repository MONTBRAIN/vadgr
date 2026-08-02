# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).

## [0.4.1] - 2026-08-02

Puts the native loop on the product's own run path. Before this, `POST /api/agents/{id}/run` executed through the CLI executor and the engine shipped as a library nothing called.

### Added
- **Native loop on the API run path** (`api/engine/native_bridge.py`). A bridge between an executor that pulls (`AsyncIterator[ExecutionEvent]`) and a loop that pushes (`on_event` callback), joined by an `asyncio.Queue`. Events are mapped to the frames the published frame vocabulary names; anything the bridge has not been taught is dropped rather than forwarded, because an unrecognized payload is exactly the unbounded one.
- **Resume on boot** (`api/main.py`, `api/services/execution_service.py`). On start the daemon finds journals with a dangling record and continues those runs from the first uncompleted step.
- **Resume entry point** (`engine/loop.py`, `engine/trajectory.py`). `run_loop(..., resume_state=...)` reconstructs the conversation from the journal, and a resumed journal continues its sequence instead of restarting it. Prior results are truncated on the way in, so a resume does not replay screenshots.
- **E2E doctrine and template** (`E2E/README.md`, `E2E/TEMPLATE.md`). Where the ground truth is, the verdict rules, the honest use of `Not-Needed`, and the shape every runbook follows.
- **Runbook** at `E2E/0.4.1/e2e.md`, run live. Eleven defects, none of which the unit suite saw.

### Fixed
- **Agent creation on a native provider raised three different ways.** `load_provider_config` did `config["args"] + [...]` on a provider that has a module and no argv; `ProviderConfig` made `command` mandatory; and `is_available()` fell through to spawning an empty argv. One defect wearing three hats: nothing on the creation path knew a provider might not be a subprocess.
- **The journal could not be tied to its run.** The executor never passed `run_id`, so the loop minted its own and wrote a directory nothing could correlate - which also broke resume on boot, since it finds a journal by id and then has to look that run up.
- **A gate crashed on a timeout the model typed.** `ask_user` declares `timeout` a `number` and the model sent `"300"`; `asyncio.wait_for` compared a `str` to an `int` and raised. The run failed at the exact moment it was trying to consult a human. Timeouts are coerced, and an unparseable one means no timeout rather than an exception.
- **The on-box WebSocket authenticated nothing.** `/api/ws/runs/{run_id}` never called the authorizer - the auth middleware is HTTP-only - so any peer gate 1 admits could open it. It also honoured an inbound `approval_response` that resumed a parked run, making it an unauthenticated way to answer a human-approval gate. It now authenticates as `/stream` does and is send-only.
- **A checklist sent as a JSON string crashed `todo_write`.** The model sent `items` already serialised; iterating a `str` yields characters, so every entry raised `'str' object has no attribute 'get'`. A JSON-Schema type is advisory for containers exactly as it is for enum values.
- **The phone's run stream carried a start and an end and nothing between.** Five of the eight keys in the mobile translator's map were event types nothing emits, and the executor's real vocabulary was absent - measured at 2 frames for a six-tool-call run, 11 after. The severe half is `awaiting`: an approval request could not reach the device that has to answer it. A test now checks every key in the map against what `executor.py` actually broadcasts.
- **The checklist reached the wire as a Python repr.** `ExecutionEvent.data` was annotated `str`, so the bridge coerced the list with `str()` and clients received single-quoted text that is not JSON.
- **An output field of prose no longer answers `500`.** `GET /api/runs/{id}/outputs/{field}` handed the output value to `Path.resolve()` to test whether it named a file; on the native loop that value is usually the model's prose, and past `NAME_MAX` it raised `OSError: File name too long`. The route has two outcomes, the bytes or `404`, so it was broken for essentially every free-text output.
- **Pairing returns the documented error codes.** `TRANSPORT_UNAVAILABLE` is now `TRANSPORT_UNREACHABLE` and `INVALID_PAIRING_TOKEN` is now `PAIRING_CODE_INVALID`; an expired code answers `410 PAIRING_CODE_EXPIRED` instead of collapsing into `401`, so a client can tell the owner to ask for a new code rather than that they mistyped this one. Codes are what a client switches on, and this is the first-run flow.
- **A gate with no terminal now says so.** The daemon has no stdin, so gates died on `EOF when reading a line` - a message about a file descriptor, not about the problem. It now says there is no interactive channel and to proceed or stop rather than retry.

### Notes
- **No gate on the daemon can reach a human yet.** The default channel router is the CLI channel, which reads stdin the daemon does not have, so gates park correctly and reach nobody. The shipped `POST /api/runs/{id}/approve` does not close this: it takes no body, so it carries a verdict and never the answer `ask_user` and `propose_plan` need, and its resume path re-runs the whole project rather than continuing it. The channel lands at `0.5.0` against `POST /api/runs/{id}/respond`, which carries a verdict, a reason and an answer and resolves against the loop's own resume.
- Agent creation is still CLI-bound: it runs forge generation, which spawns the configured provider as a subprocess, and a native provider cannot. A run may override the provider per trigger, which is the path the runbook exercises.
- **Pairing has no attempt limit.** The published `429 RATE_LIMITED` on `/api/auth/pair` and `/api/auth/claim` is unimplemented - the store has no attempt counter. An 8-character code inside a five-minute window is not practically guessable over HTTP, but the behaviour is specified and absent.
- `/api/ws/runs/{run_id}` is deleted at `0.5.0`, when one socket survives. It has a live consumer today (`cli/stream.py`), so it was fixed rather than removed.

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
