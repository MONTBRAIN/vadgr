# 0.4.7 - provider onboarding precedes pairing: e2e runbook

A clean Vadgr installation can connect supported model credentials directly,
keep multiple providers, select one machine default, and complete real work
without an external model CLI in the request path.

> **Status: partially run on WSL2, 2026-08-16.** The static Linux artifact and
> its clean install in `scratch` pass. Direct ChatGPT OAuth, authenticated model
> discovery, readiness, three independent live engine passes, the full surface
> inventory, WSL credential controls, hard-kill continuation, and an owner work
> path through Windows Notepad pass. Live API-key onboarding, native Linux,
> macOS and Windows sessions, 12 named surface branches, the dogfood kill cell,
> and a monetary cost value remain open. **8 findings, all repaired and rerun at
> their affected boundaries.** Nothing is marked pass that was not executed and
> read back.

## The approach

The closing runs use the installed product and a real agent given a goal-level
task, per [`../README.md`](../README.md). The verdict comes from provider rows,
SQLite metadata, credential-file controls, HTTP and CLI records, both run
WebSockets, and `trajectory.jsonl`. The agent's prose is not evidence.

Both product surfaces are required:

- the API plus both run WebSockets, which is the phone path;
- the shipped `vadgr` CLI pointed at the Rust daemon, which is the on-box path.

The agent driver, version, prompt, and complete output must be captured in the
private evidence bundle. The prompt names an owner goal, not a tool call.

## Prerequisites

Use the release artifact and isolate every daemon. Port `1455` must also be
free for the fixed OpenAI browser callback.

```bash
export E2E_ROOT="$(mktemp -d)"
export VADGR_STATE_HOME="$E2E_ROOT/state"
export VADGR_DB="$E2E_ROOT/vadgr.db"
export VADGR_RUNS_DIR="$E2E_ROOT/runs"
export VADGR_CUA_BIN=/home/santiago/Santiago/Common/vadgr-computer-use/.venv/bin/vadgr-cua
export VADGR_PORT=9471
export VADGR_TRANSPORT=loopback
export FORGE_API_URL=http://127.0.0.1:9471
mkdir -p "$VADGR_STATE_HOME" "$VADGR_RUNS_DIR"
./rust/target/release/vadgr-daemon
```

Live secrets are entered through the CLI without echo or supplied through the
documented provider environment variable. They are excluded from commands,
logs, process listings, test records, and the evidence repository.

## Automated gate (necessary, never sufficient)

| gate | result |
|---|---|
| complete Python suite | pass: 703 passed in 21.32s |
| Rust all-target suite | pass: 171 passed, 1 Docker-only test ignored |
| `cargo fmt --check` | pass |
| `cargo check --all-targets` | pass |
| `cargo clippy --all-targets -- -D warnings` | pass |
| Windows credential module target check | pass |
| macOS credential module target check | pass |
| Linux musl release build | pass: static PIE, SHA-256 `36fc7da0a86c82a3991687cdec5177fd792f83e3b7a19b3ae48845839d63e6d7` |
| clean install in `scratch` | pass: healthy `0.4.7`, Linux, loopback, cua disabled, three disconnected providers |
| required GitHub Actions jobs | not run |

The automated tests prove deterministic state, protocol, migration, and error
cases. They cannot prove an external account can authenticate, a live model can
act through installed cua, or a killed installed daemon can continue safely.

## Coverage

There are no deferrals from this minor. The `0.4.6` provider-blocked close is
carried here in full and is part of acceptance.

| Part | Axes | Cells | Run | Open |
|---|---|---:|---:|---:|
| Surface inventory | 20 HTTP operations + 24 CLI invocations + 30 absent probes | 74 | 74 | 0 |
| A: onboarding | 4 credential paths x 6 assertions | 24 | 6 | 18 |
| B: credential storage | 4 platforms x 8 assertions | 32 | 8 | 24 |
| C: engine behavior | 25 carried native-loop cases | 25 | 4 | 21 |
| Repeatability | 3 passes x 6 observables | 18 | 18 | 0 |
| D: restart continuation | 1 sequence x 7 assertions | 7 | 7 | 0 |
| E: owner dogfood | 1 batch x 5 outcomes | 5 | 4 | 2 |
| | | **185** | **121** | **65** |

`Run` means the cell was executed and recorded, not necessarily that every
assertion passed. E4 was run but remains open because the transport did not
provide a monetary price. The surface inventory count is by published
operation; 12 additional named branch subcases remain open and are listed
below.

## Surface coverage - every published endpoint, with what it returned

The closing sweep generated its tables from one recorded JSON source. The
summary below reports what was observed; the private evidence retains all 47
named HTTP cases and their response bodies.

### Shipped

| endpoint | what was asked | status | code | response, as returned |
|---|---|---|---|---|
| `GET /api/health` | installed daemon liveness and version | `200` | - | healthy `0.4.7` daemon |
| `POST /api/auth/pair` | after a default exists | `200` | - | Tailscale pairing response |
| `POST /api/auth/claim` | invalid, valid, and reused claim | `200`, `401` | `PAIRING_CODE_INVALID` | valid claim succeeded; invalid and reused codes failed |
| `GET /api/devices` | paired and empty lists | `200` | - | paired row, then empty after revoke |
| `DELETE /api/devices/{device_id}` | existing and unknown device | `200`, `404` | `DEVICE_NOT_FOUND` | existing revoke succeeded; unknown id failed |
| `GET /api/providers` | connected default and disconnected rows | `200` | - | OpenAI connected/default; Gemini and Anthropic disconnected |
| `POST /api/providers/{provider_id}/auth-attempts` | valid and invalid method pairs | `200`, `202`, `400`, `422` | `INVALID_PROVIDER_AUTH` where applicable | OAuth pending/cancel targets and API-key validation paths observed |
| `GET /api/provider-auth/{attempt_id}` | pending, cancelled, and missing | `200`, `404` | `AUTH_ATTEMPT_NOT_FOUND` | expected attempt states returned |
| `PUT /api/providers/{provider_id}/connection` | pending, wrong provider, and invalid credential | `409`, `401` | `AUTH_ATTEMPT_NOT_READY`, `INVALID_CREDENTIALS` | rejected without replacing the working connection |
| `DELETE /api/providers/{provider_id}/connection` | default and missing | `409`, `204` | `DEFAULT_MODEL_IN_USE` | default refused; absent disconnected row remained absent |
| `POST /api/providers/{provider_id}/catalog-refresh` | connected and disconnected | `200`, `409` | `PROVIDER_NOT_CONNECTED` | OpenAI refreshed; disconnected provider failed |
| `PUT /api/default-model` | valid, unavailable, and disconnected | `200`, `422`, `409` | `MODEL_NOT_AVAILABLE`, `PROVIDER_NOT_CONNECTED` | valid readiness committed only the available model |
| `GET /api/settings/computer-use` | current setting | `200` | - | current setting returned |
| `PUT /api/settings/computer-use` | disable and restore | `200` | - | both transitions returned the committed setting |
| `GET /api/computer-use/status` | installed cua readiness | `200` | - | installed cua reported ready |
| `GET /api/runs` | populated list | `200` | - | recorded runs returned |
| `POST /api/runs` | default and explicit provider/model | `202` | - | both forms accepted |
| `GET /api/runs/{run_id}` | existing and unknown run | `200`, `404` | `RUN_NOT_FOUND` | expected row and missing error returned |
| `POST /api/runs/{run_id}/cancel` | running, terminal, and missing | `200`, `409`, `404` | `RUN_NOT_ACTIVE`, `RUN_NOT_FOUND` | each state returned its contract result |
| `POST /api/runs/{run_id}/resume` | failed, missing, and non-resumable | `200`, `404`, `409` | `RUN_NOT_FOUND`, `RUN_NOT_RESUMABLE` | failed run resumed; other states failed as specified |

OAuth callback responses on `127.0.0.1:1455` were recorded for valid,
cancelled, wrong-state, duplicate, and pending-attempt cleanup. Every callback
returned `303` to query-free `/auth/complete` or `/auth/failed`. A real
ten-minute expiry remains open.

### Not yet built - probed to confirm absent, not half-wired

The generated sweep reused the 30-route absence inventory from `0.4.6`.
All 30 returned `404` or `405`; no removed route was accepted on the basis of
source inspection.

### The CLI

| command group | cases | result |
|---|---|---|
| `vadgr provider login` | invalid cross-provider method | pass: exit `2`, nonempty output |
| `vadgr provider status` | connected rows and live OpenAI refresh | pass: exit `0`, nonempty output |
| `vadgr provider logout` | default refusal | pass: exit `1`, nonempty output |
| `vadgr model list` | connected catalog union | pass: exit `0`, nonempty output |
| `vadgr model default` | explicit live readiness | pass: exit `0`, nonempty output |
| `vadgr pair` | immediate QR with retained default | pass: exit `0`, nonempty output |
| existing health, providers, cua, run, runs, service commands | 18 additional concrete invocations | pass: every invocation produced output |
| daemon-down command | stable exit `3` and nonempty output | pass |

The generated table records 25 cases across all 24 unique shipped invocations.
Interactive provider selection, successful API-key paths, interactive model
selection, onboarding-first pairing, and live legacy service lifecycle remain
among the 12 open surface subcases.

The 12 open branch subcases are: live callback expiry; pairing before a default;
a stale catalog row; replacement of the current default connection; deletion of
a connected non-default provider; catalog-refresh rollback after an upstream
failure; default-model rollback after failed readiness; CLI provider chooser,
OpenAI method choice, three successful API-key paths and recovery; CLI ChatGPT
login success as one continuous command; interactive model selection;
onboarding-first pairing; and live legacy service lifecycle commands.

### The sockets

| socket | frames | types, as received |
|---|---:|---|
| `WS /api/ws/runs/{run_id}` | 8 in A; 5 in B and C | terminal `run_completed` present in all three |
| `WS /api/runs/{run_id}/stream` | 5 in each pass | `started`, `tool_call`, two `output`, `completed` |

## Part A: provider onboarding and defaults

| # | What | Expected | Status |
|---|---|---|---|
| A1 | clean `vadgr pair` | provider onboarding comes first and a passing connection continues directly to the QR | not run; retained-default QR path passed |
| A2 | `vadgr provider login` | connection ends without calling pairing | pass: OpenAI connection completed and returned without minting a pair |
| A3 | OpenAI ChatGPT OAuth | browser PKCE, account catalog, readiness, and direct ChatGPT response pass | pass: seven models discovered; `gpt-5.6-sol` selected and persisted |
| A4 | OpenAI API key | Platform catalog and readiness pass | not run |
| A5 | Gemini API key | Gemini catalog and readiness pass | not run |
| A6 | Anthropic API key | Anthropic catalog and readiness pass | not run |
| A7 | additive connections | all rows coexist and a later connection preserves the default | deterministic tests pass; multi-provider live path not run |
| A8 | model default | one explicit pointer changes only after live readiness | pass for explicit OpenAI default; cross-provider path not run |
| A9 | reauthentication failure | old credential, catalog, and default remain usable | pass: invalid replacement preserved the live OpenAI connection |
| A10 | logout | one non-default disappears without mutating the others | default refusal and absent row pass; connected non-default path not run |

Measured evidence includes attempt ids, provider rows before and after each
commit, selected defaults, catalog counts, readiness usage, and CLI exits.

## Part B: credential storage and migration

| # | What | Expected | Status |
|---|---|---|---|
| B1 | fresh database | migration one and null machine default commit atomically | pass on WSL |
| B2 | existing `0.4.6` database | historical runs remain readable and no legacy credential is imported | pass on WSL with a real `0.4.6` database |
| B3 | raw SQLite files | no API key, access token, or refresh token occurs in DB, WAL, or SHM | pass on WSL across create, rotate, resolve and delete |
| B4 | committed record | strict versioned JSON under an opaque immutable reference | pass on WSL: strict v1 JSON, immutable opaque reference, mode `0600` |
| B5 | effective controls | native owner-only controls pass on Linux, WSL, macOS, and Windows | pass on WSL; other operating systems not run |
| B6 | unsafe path | links, reparse points, wrong owner, broad ACL, and unenforced WSL mount fail closed | pass on WSL: 15 malformed/control cases and real `/mnt/c` fail-closed; other operating systems not run |
| B7 | crash before DB commit | orphan is removed and old reference survives | pass on WSL |
| B8 | crash after DB commit | committed new reference survives and old orphan is removed | pass on WSL |

## Part C: full product path and engine behavior

The 25 behavior cases carried from `0.4.6` cover live calls, eight control
tools, text and image content, one tool error, four terminal outcomes, journal
and continuation cases, two cancellation timings, and three cua states. Every
case must be driven through the product and reconciled with the journal.

| # | What | Expected | Status |
|---|---|---|---|
| C1 | default-provider live run | model response has nonzero usage | pass: all three formal runs completed with OpenAI `gpt-5.6-sol` and nonzero usage |
| C2 | installed cua dispatch | matching `in_flight` and terminal journal records | pass: every dispatched call has the matching terminal record |
| C3 | completed action | read-back proves the real external effect | pass: platform, shell, WSLg, Windows host, and screenshot reads support the final report |
| C4 | raw and mobile streams | published frames agree with journal phases | pass: both sockets reached their terminal completed frame in all three passes |
| C5 | complete carried matrix | all remaining behavior cells close | not run |

## Repeatability - three independent passes

Three agents use separate ports, databases, state roots, run roots, daemons,
and provider attempts. They perform the same goal-level task concurrently.

| | pass A | pass B | pass C |
|---|---|---|---|
| run | `run-1ce4abf3fa184847928dac457f685842` | `run-21f9bcb4e5e44609ae460581d0df6b43` | `run-db0e530b08d34ce08f26df69e505756b` |
| HTTP entries | accepted and completed | accepted and completed | accepted and completed |
| CLI entries | login/readiness and persisted state captured | login/readiness and persisted state captured | login/readiness and persisted state captured |
| raw / mobile frames | `8 / 5`, terminal | `5 / 5`, terminal | `5 / 5`, terminal |
| journal phases | `19 / 19`, no error | `16 / 16`, 2 handled errors | `11 / 11`, no error |
| tokens in / out | `1,077,574 / 1,286` | `913,612 / 2,030` | `317,047 / 796` |

The three runs began with the same 5,458-token input fixture. Their first output
counts and later trajectories differ, proving independent model calls. The
comparison normalizes only run id, timestamp, port, and provider request id.

## Part D: hard-kill restart continuation

| # | What | Expected | Status |
|---|---|---|---|
| D1 | kill only the tested daemon during an open cua call | process exits without graceful completion | pass: assigned daemon received `SIGKILL` during open journal sequence 6 |
| D2 | restart with the same database, state, and journal | the same run continues automatically | pass: same run resumed from sequence 7 |
| D3 | journal sequence | sequence continues in the same file | pass |
| D4 | completed side effects | no completed effect repeats | pass: marker inode, timestamp and hash were unchanged |
| D5 | dangling call | boot does not blindly dispatch it | pass: the shell effect appears once |
| D6 | live-state inspection | inspection occurs before any retry | pass: marker read was the first external call after restart |
| D7 | final agreement | database and both sockets agree with the journal | pass: run completed; usage and terminal frames agree |

The final rerun used source `5558cf6` and run
`run-6889e6bf31e44e309114f8c9ffe7078b`. It also proved that the reconstructed
todo list survived restart and accepted both subsequent updates.

## Part E: owner dogfood batch

| # | What | Expected | Status |
|---|---|---|---|
| E1 | one real owner batch from the CLI | valid terminal outcome after real work | pass: `run-549f588dd35e48a7864adfe99f3a6caa` completed |
| E2 | cua as hands | countable external actions with read-back | pass: WSL write, Windows Notepad append/save, exact WSL read-back |
| E3 | deliberate kill during an open call | continuation without duplicate action | not run in the owner batch; Part D passes separately |
| E4 | cost record | wall time, model calls, input/output tokens, and money | partial: 86.080s, 22 model calls, 1,628,437 input and 1,050 output tokens; monetary value unavailable |
| E5 | owner contact | human-contact count is recorded | pass: zero human contacts |

## Evidence

The final private evidence lives under `e2e_evidence/vadgr-0.4.7/`. It
contains the source commit and binary checksum, generated surface sweep and
tables, CLI transcripts, provider rows, redacted credential metadata and
effective-control checks, databases, journals, socket frames, daemon logs,
comparison output, and a checksum manifest. Secrets and authorization headers
must not be present.

## Findings

| id | finding | root cause | repair and regression | rerun |
|---|---|---|---|---|
| F1 | The first `scratch` start exited before readiness with `provider request failed: builder error`. | Reqwest selected the platform certificate verifier. A `scratch` image has no system certificate store. | The provider client now supplies a Rustls configuration with embedded Web PKI roots. The clean-install test remains the regression because it starts with no host files or libraries. | pass: the exact static artifact served health and providers from `scratch` |
| F2 | Docker Desktop first returned health with `platform: wsl` from the Linux container. | The container shares a Microsoft WSL kernel, and host detection treated that kernel marker as direct WSL. | Linux container markers now take precedence over WSL markers. A unit test keeps direct WSL as `wsl` and a container as Linux. | pass: health returned `platform: linux` from `scratch` |
| F3 | The first direct ChatGPT connection returned no usable models, then readiness returned HTTP 400 after catalog discovery was repaired. | The catalog used Vadgr `0.4.7` as a ChatGPT protocol capability version, and the Responses body sent `max_output_tokens`, which the native ChatGPT route does not support. | The catalog has an explicit protocol version independent of the product version. The ChatGPT request omits the unsupported field while the API-key request retains it. Both boundaries have regression tests. | pass: browser OAuth, catalog discovery, bounded readiness, credential commit, and default selection completed |
| F4 | The first real OpenAI run consumed tokens but failed with `NO_ACTION_TAKEN`; its journal contained no tool call. | ChatGPT delivered the completed item in `response.output_item.done` while `response.completed` carried usage and an empty output array. The decoder read only the terminal frame and discarded the streamed item. | The SSE decoder accumulates completed output items and uses them when terminal output is empty. A regression test reproduces the live event sequence. | pass: the rerun completed in 12 iterations with installed cua calls, nonzero usage, matched journal phases, one handled tool error, and a final verified report |
| F5 | The CLI printed the fallback authorization URL after a successful browser launch and hid it after a failed launch. | Click returns process-style status `0` for a successful launch, but the branch treated that value as false. | The branch now compares the launch status to zero explicitly. A regression test forces a nonzero result and requires the URL in output. | pass: focused provider CLI suite, 9 tests |
| F6 | WSL did not open the Windows browser, and an E2E-only `cmd.exe start` workaround delivered a malformed OAuth request with missing parameters. | Click's Linux launcher could not cross the WSL desktop boundary. The command-shell workaround also gave `cmd.exe` an OAuth URL whose query delimiters are shell syntax. | WSL now invokes a fixed Windows PowerShell script without a shell-built URL and sends the complete authorization URL over stdin. Tests require that the URL is absent from argv and preserved exactly as input. Other platforms retain Click's native launcher. | pass: focused provider CLI suite and three live browser launches from WSL |
| F7 | The formal work-run screenshots captured the spent OAuth callback query from Chrome's address bar. A denied callback also rendered the connected page. | The callback returned its final HTML directly on the URL that carried `code` and `state`, and the route treated a cleanly recorded cancellation as a successful connection. | Every callback now redirects to a parameter-free completion or failure route. A route-level regression requires `303`, a query-free `Location`, a generic final page, and failure status for cancellation. Evidence copies replace affected screenshot payloads with explicit redaction records while preserving hashes and sizes. | pass at affected boundaries: focused route regression, live reauthentication, readiness and commit; visual address-bar read-back unavailable because the owner closed the completion tab |
| F8 | The hard-kill run resumed safely but its next `control__todo_update` returned `unknown todo id`. | The journal recovered model usage, recent results and external-call state, while `RunContext` recreated its control todo list as empty. | Recovery now reconstructs the canonical list from successful journaled `todo_write` and `todo_update` results before the MCP host starts. Tests cover both reconstruction and a successful update through a restored control server. | pass: final hard-kill rerun restored all todos and completed both later updates |

The probe also moved from host networking to a separate BusyBox container that
joins the product container's network namespace. Docker Desktop does not expose
Linux host networking to WSL in the same way as native Linux. The product image
remains `scratch`, and the probe still drives it from outside the product.

## Per-OS results

Legend: pass / fail / blocked / not run / **Not-Needed**.

| | Linux | macOS | Windows native | WSL |
|---|---|---|---|---|
| build, test, and lint | CI not run | CI not run | CI not run | pass locally |
| credential matrix | not run | type check only | type check only | pass on WSL |
| clean install | pass in Linux `scratch` | not run | not run | driver host only |
| live providers | not run | not run | not run | partial: direct ChatGPT OAuth passes; API-key paths not run |
| full engine | not run | not run | not run | partial: three independent installed-cua runs pass; full 25-case matrix open |
| restart and dogfood | not run | not run | not run | hard-kill pass; owner work path pass; dogfood kill and money cells open |
| overall | not run | not run | not run | partially run |

Credential paths, access controls, binary startup, callback binding, and child
process launch are platform-shaped. No supported operating system is
**Not-Needed** for final acceptance.

## What this runbook cannot prove

The remaining cells cannot prove OpenAI API-key, Gemini API-key or Anthropic
API-key onboarding; native Linux, macOS or Windows installed-product sessions;
cross-platform effective credential controls outside WSL; the remaining 21
engine behaviors; the 12 named surface branches; a kill inside the owner
dogfood batch; or a monetary cost for ChatGPT OAuth usage. Those are open and
prevent this runbook from declaring the minor fully accepted.
