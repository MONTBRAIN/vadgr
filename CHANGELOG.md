# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).

## [0.4.2] - 2026-08-05

**The web dashboard is gone.** The machine's clients are now the `vadgr` CLI on the box and the phone app over the tailnet, and installing vadgr no longer installs Node.js. The API contract is unchanged: every operation the dashboard rendered is still served by the same endpoints.

### Removed
- **The React web frontend** (`frontend/`, 71 files, 12,171 lines). It was one of three interchangeable clients of the same API and nothing depended on it. Extracted with its full history into a private attic repository first, so it can be revived by a subtree pull rather than rewritten.
- **Node.js, NVM and npm from the installer.** `setup.sh` loses `install_nvm_and_node` and `setup_frontend`; `setup.ps1` loses `InstallNode` and `SetupFrontend`. A fresh install is now git, Python, the virtualenvs and the CLI, and nothing else.
- **The frontend half of `vadgr start`.** The `--frontend-port` flag, the node/npm lookup, the `npm run dev` spawn, the Vite log-port parser, the `frontend.log`, and the `frontend` pid and port files. `start` boots the API alone and reports one address.
- **CORS.** `CORSMiddleware`, the `cors_origins` setting and the `AGENT_FORGE_CORS_ORIGINS` environment variable. No browser client remains, so the daemon no longer answers with access-control headers.
- **`frontend_port` / `AGENT_FORGE_FRONTEND_PORT`** from the API settings.

### Changed
- **Pairing is CLI-only.** `vadgr pair` mints the token and prints the Unicode QR in the terminal; it is now the only pairing surface the machine has. The endpoints behind it are unchanged, so a phone that could pair before still pairs.
- **`vadgr api` and `vadgr start` are one command.** `api` stays as a name for it, and its `--port` spelling still parses alongside `--api-port`.
- **`vadgr status` lists one service**, not two. The second row was permanently `stopped` on any machine without Node.
- **`vadgr stop`, `vadgr restart` and `vadgr logs`** act on the daemon alone; `logs --service` accepts only `api`.
- **A finished run links to the API.** `vadgr run` used to probe for a dev server and print `http://localhost:3000/runs/<id>` when it found one; it now prints `<api>/api/runs/<id>` unconditionally, which also removes a probe that cost about a second on every completed run.
- **`vadgr update`** no longer reinstalls frontend dependencies.
- README, `cli/README.md`, `api/README.md` and `AGENTS.md` updated to describe two clients instead of three. The two API design documents that describe the v1 visual-canvas product are marked historical rather than rewritten, since the dashboard is their premise.

### Added
- **A guardrail test** (`api/tests/test_frontend_decommissioned.py`) that fails the suite if the frontend directory, an npm manifest, the npm-start path, a `--frontend-port` flag, the CORS origin or a Node step in either setup script ever returns.
- **Runbook** at `E2E/0.4.2/e2e.md`, run live before this was offered for review.

### Notes
- Agent creation on a native provider fails with `[Errno 13] Permission denied: ''` and reaches status `error`. This is not new here - it reproduces identically on `v0.4.1` - but it is recorded because the runbook hit it. Runs on an existing agent are unaffected.

### Tests
- engine 122, api 554, cli 192, all green. The api count moves by seven new guardrail tests and two new API-only tests against five deleted CORS and frontend-port tests and one deleted gateway-guard test; the cli count by ten new API-only tests against seven deleted Node-discovery and Vite-log tests.
- Verified live on WSL against a real tailnet: `vadgr start` spawns no child process at all on a host that has Node on its PATH, nothing answers on port 3000, `vadgr pair` mints a token that a claim turns into a persisted device, and a native-loop run still completes from both the API and the CLI. The CLI surface and both installer changes were also verified on native Windows.

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
- **A parking gate now announces itself.** `ask_user`, `request_approval` and `propose_plan` wrote a journal line and emitted nothing, so a run could park on a human with no watcher able to learn it had - while three layers carried an `awaiting` branch that nothing could reach and every test passed. Journalling and announcing are now one call, since they are the same fact for two audiences.
- **An unrecognized loop event is dropped loudly.** The bridge returned the same silent `None` for the two events it drops on purpose and for any type the engine grows later, so the second was invisible until a feature turned out to be missing. The deliberate pair is named as data; anything else warns.
- **An unreachable daemon is reported in ~1.6s instead of ~15s on WSL.** A short connect probe runs before the request. On Linux and macOS a closed local port is refused instantly; on WSL2 IPv4 loopback swallows it, so the connect ran to the full request timeout - which has to stay generous because a request can be doing real work.
- **The CLI can say "the daemon is down".** Exit `3` is reserved for an unreachable daemon and `1` for a request that ran and was refused; both came back as `1`, so a script could not branch on them - and the first is worth retrying after `vadgr start` while the second never is.
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
