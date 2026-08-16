# 0.4.7 - provider onboarding precedes pairing: e2e runbook

A clean Vadgr installation can connect supported model credentials directly,
keep multiple providers, select one machine default, and complete real work
without an external model CLI in the request path.

> **Status: partially run on WSL2, 2026-08-16.** The static Linux artifact and
> its clean install in `scratch` pass. Direct ChatGPT OAuth, authenticated model
> discovery, readiness, credential persistence across restart, and one real
> installed-cua run pass. Gemini, Anthropic, the full surface sweep,
> repeatability, hard-kill continuation, and dogfood are open. **6 findings,
> all repaired and rerun.** Nothing is marked pass that was not executed and
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
| Rust all-target suite | pass: 168 passed, 1 Docker-only test ignored |
| `cargo fmt --check` | pass |
| `cargo check --all-targets` | pass |
| `cargo clippy --all-targets -- -D warnings` | pass |
| Windows credential module target check | pass |
| macOS credential module target check | pass |
| Linux musl release build | pass: static PIE, SHA-256 `9da75809acb625057a740fecfada4e2842143c29ae127916b45b04c14cd02fe9` |
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
| Surface inventory | 20 HTTP/socket operations + 24 CLI invocations + 30 absent probes | 74 | 0 | 74 |
| A: onboarding | 4 credential paths x 6 assertions | 24 | 0 | 24 |
| B: credential storage | 4 platforms x 8 assertions | 32 | 0 | 32 |
| C: engine behavior | 25 carried native-loop cases | 25 | 0 | 25 |
| Repeatability | 3 passes x 6 observables | 18 | 0 | 18 |
| D: restart continuation | 1 sequence x 7 assertions | 7 | 0 | 7 |
| E: owner dogfood | 1 batch x 5 outcomes | 5 | 0 | 5 |
| | | **185** | **0** | **185** |

## Surface coverage - every published endpoint, with what it returned

The closing sweep must generate this section from one recorded JSON source.
Until that sweep runs, every row is explicitly open and no expected response is
presented as an observation.

### Shipped

| endpoint | what will be asked | status | code | response, as returned |
|---|---|---|---|---|
| `GET /api/health` | installed daemon liveness and version | not run | - | not captured |
| `POST /api/auth/pair` | before and after a default exists | not run | - | not captured |
| `POST /api/auth/claim` | invalid and valid claim | not run | - | not captured |
| `GET /api/devices` | empty and paired lists | not run | - | not captured |
| `DELETE /api/devices/{device_id}` | existing and unknown device | not run | - | not captured |
| `GET /api/providers` | disconnected, connected, default, and stale rows | not run | - | not captured |
| `POST /api/providers/{provider_id}/auth-attempts` | valid methods and every invalid pair | not run | - | not captured |
| `GET /api/provider-auth/{attempt_id}` | pending, authenticated, cancelled, expired, and missing | not run | - | not captured |
| `PUT /api/providers/{provider_id}/connection` | passing, failed, replacement, and wrong attempt | not run | - | not captured |
| `DELETE /api/providers/{provider_id}/connection` | non-default, default, and missing | not run | - | not captured |
| `POST /api/providers/{provider_id}/catalog-refresh` | success and rollback on failure | not run | - | not captured |
| `PUT /api/default-model` | valid, unavailable, and failed readiness | not run | - | not captured |
| `GET /api/settings/computer-use` | current setting | not run | - | not captured |
| `PUT /api/settings/computer-use` | disable and restore | not run | - | not captured |
| `GET /api/computer-use/status` | installed cua readiness | not run | - | not captured |
| `GET /api/runs` | empty and populated lists | not run | - | not captured |
| `POST /api/runs` | default and explicit provider/model | not run | - | not captured |
| `GET /api/runs/{run_id}` | existing and unknown run | not run | - | not captured |
| `POST /api/runs/{run_id}/cancel` | running and terminal run | not run | - | not captured |
| `POST /api/runs/{run_id}/resume` | failed, missing, and non-resumable run | not run | - | not captured |

OAuth callback responses on the dedicated `127.0.0.1:1455` listener are also
recorded for valid, cancelled, wrong-state, duplicate, and expired callbacks.

### Not yet built - probed to confirm absent, not half-wired

The generated sweep reuses the 30-route absence inventory from `0.4.6`. Each
must return `404` or `405`; the resulting table replaces this paragraph after
execution. No removed route is accepted on the basis of source inspection.

### The CLI

| command group | cases | result |
|---|---|---|
| `vadgr provider login` | provider chooser, OpenAI method, three API keys, ChatGPT browser, recovery, no pairing | not run |
| `vadgr provider status` | disconnected, connected, all refresh, one refresh | not run |
| `vadgr provider logout` | non-default, default refusal, unknown | not run |
| `vadgr model list` | union of every connected catalog | not run |
| `vadgr model default` | interactive, explicit, failed readiness | not run |
| `vadgr pair` | onboarding first, then immediate QR | not run |
| existing health, providers, cua, run, runs, service commands | positive and required negative cases | not run |
| daemon-down command | stable exit `3` and nonempty output | not run |

The final table records each concrete command, exit code, and printed output.
It asserts nonempty output so a wrong entry point cannot pass silently.

### The sockets

| socket | frames | types, as received |
|---|---:|---|
| `WS /api/ws/runs/{run_id}` | not run | not captured |
| `WS /api/runs/{run_id}/stream` | not run | not captured |

## Part A: provider onboarding and defaults

| # | What | Expected | Status |
|---|---|---|---|
| A1 | clean `vadgr pair` | provider onboarding comes first and a passing connection continues directly to the QR | not run |
| A2 | `vadgr provider login` | connection ends without calling pairing | pass: OpenAI connection completed and returned without minting a pair |
| A3 | OpenAI ChatGPT OAuth | browser PKCE, account catalog, readiness, and direct ChatGPT response pass | pass: seven models discovered; `gpt-5.6-sol` selected and persisted |
| A4 | OpenAI API key | Platform catalog and readiness pass | not run |
| A5 | Gemini API key | Gemini catalog and readiness pass | not run |
| A6 | Anthropic API key | Anthropic catalog and readiness pass | not run |
| A7 | additive connections | all rows coexist and a later connection preserves the default | not run |
| A8 | model default | one explicit pointer changes only after live readiness | not run |
| A9 | reauthentication failure | old credential, catalog, and default remain usable | not run |
| A10 | logout | one non-default disappears without mutating the others | not run |

Measured evidence will include attempt ids, provider rows before and after each
commit, selected defaults, catalog counts, readiness usage, and CLI exits.

## Part B: credential storage and migration

| # | What | Expected | Status |
|---|---|---|---|
| B1 | fresh database | migration one and null machine default commit atomically | not run |
| B2 | existing `0.4.6` database | historical runs remain readable and no legacy credential is imported | not run |
| B3 | raw SQLite files | no API key, access token, or refresh token occurs in DB, WAL, or SHM | pass for the live OpenAI connection |
| B4 | committed record | strict versioned JSON under an opaque immutable reference | pass: opaque reference, owner-only directory, file mode `0600` |
| B5 | effective controls | native owner-only controls pass on Linux, WSL, macOS, and Windows | not run |
| B6 | unsafe path | links, reparse points, wrong owner, broad ACL, and unenforced WSL mount fail closed | not run |
| B7 | crash before DB commit | orphan is removed and old reference survives | not run |
| B8 | crash after DB commit | committed new reference survives and old orphan is removed | not run |

## Part C: full product path and engine behavior

The 25 behavior cases carried from `0.4.6` cover live calls, eight control
tools, text and image content, one tool error, four terminal outcomes, journal
and continuation cases, two cancellation timings, and three cua states. Every
case must be driven through the product and reconciled with the journal.

| # | What | Expected | Status |
|---|---|---|---|
| C1 | default-provider live run | model response has nonzero usage | pass: `run-82271e2add394ea0867b7eeadeae61a2` completed with OpenAI `gpt-5.6-sol` |
| C2 | installed cua dispatch | matching `in_flight` and terminal journal records | pass: every dispatched call has the matching terminal record |
| C3 | completed action | read-back proves the real external effect | pass: platform, shell, WSLg, Windows host, and screenshot reads support the final report |
| C4 | raw and mobile streams | published frames agree with journal phases | not run |
| C5 | complete carried matrix | all remaining behavior cells close | not run |

## Repeatability - three independent passes

Three agents use separate ports, databases, state roots, run roots, daemons,
and provider attempts. They perform the same goal-level task concurrently.

| | pass A | pass B | pass C |
|---|---|---|---|
| run | not run | not run | not run |
| HTTP entries | not run | not run | not run |
| CLI entries | not run | not run | not run |
| raw / mobile frames | not run | not run | not run |
| journal phases | not run | not run | not run |
| tokens in / out | not run | not run | not run |

The comparison normalizes only run id, agent id, timestamp, port, and provider
request id. Input tokens should match and output tokens should differ.

## Part D: hard-kill restart continuation

| # | What | Expected | Status |
|---|---|---|---|
| D1 | kill only the tested daemon during an open cua call | process exits without graceful completion | not run |
| D2 | restart with the same database, state, and journal | the same run continues automatically | not run |
| D3 | journal sequence | sequence continues in the same file | not run |
| D4 | completed side effects | no completed effect repeats | not run |
| D5 | dangling call | boot does not blindly dispatch it | not run |
| D6 | live-state inspection | inspection occurs before any retry | not run |
| D7 | final agreement | database and both sockets agree with the journal | not run |

## Part E: owner dogfood batch

| # | What | Expected | Status |
|---|---|---|---|
| E1 | one real owner batch from the CLI | valid terminal outcome after real work | not run |
| E2 | cua as hands | countable external actions with read-back | not run |
| E3 | deliberate kill during an open call | continuation without duplicate action | not run |
| E4 | cost record | wall time, model calls, input/output tokens, and money | not run |
| E5 | owner contact | human-contact count is recorded | not run |

## Evidence

The final private evidence lives under `e2e_evidence/vadgr-0.4.7/`. It will
contain the source commit and binary checksum, generated surface sweep and
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
| F6 | WSL did not open the Windows browser, and an E2E-only `cmd.exe start` workaround delivered a malformed OAuth request with missing parameters. | Click's Linux launcher could not cross the WSL desktop boundary. The command-shell workaround also gave `cmd.exe` an OAuth URL whose query delimiters are shell syntax. | WSL now invokes a fixed Windows PowerShell script without a shell-built URL and sends the complete authorization URL over stdin. Tests require that the URL is absent from argv and preserved exactly as input. Other platforms retain Click's native launcher. | pass: focused provider CLI suite, 10 tests; formal browser rerun pending |

The probe also moved from host networking to a separate BusyBox container that
joins the product container's network namespace. Docker Desktop does not expose
Linux host networking to WSL in the same way as native Linux. The product image
remains `scratch`, and the probe still drives it from outside the product.

## Per-OS results

Legend: pass / fail / blocked / not run / **Not-Needed**.

| | Linux | macOS | Windows native | WSL |
|---|---|---|---|---|
| build, test, and lint | CI not run | CI not run | CI not run | pass locally |
| credential matrix | not run | type check only | type check only | not run |
| clean install | pass in Linux `scratch` | not run | not run | driver host only |
| live providers | not run | not run | not run | partial: direct ChatGPT OAuth pass |
| full engine | not run | not run | not run | partial: one installed-cua run pass |
| restart and dogfood | not run | not run | not run | not run |
| overall | not run | not run | not run | partially run |

Credential paths, access controls, binary startup, callback binding, and child
process launch are platform-shaped. No supported operating system is
**Not-Needed** for final acceptance.

## What this runbook cannot prove

Until the open cells execute, this runbook cannot prove live external account
authorization, provider billing availability, non-Linux installed-product
startup, cross-platform effective access control, model action through installed
cua, restart continuation, repeatability, or the owner dogfood outcome.
