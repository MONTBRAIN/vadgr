# 0.4.6 - the Rust engine reaches live hands: e2e runbook

The Rust daemon demonstrably reaches a live model and installed cua through its
native seam, while the full product-level engine close remains blocked and is
not represented as a pass.

> **Status: partially run on WSL2, 2026-08-15.** Automated gate green
> (Python 692, Rust 135 with 1 Docker-only test ignored). Part A passes as a
> bounded acceptance seam; Parts B through D remain blocked or not run.
> **1 finding**, listed below. Nothing is marked pass that was not executed and
> read back.

The recorded owner disposition is not an E2E pass. It permits `0.4.6` to merge
and tag with this blocked record preserved. Every unfinished engine cell is an
additional mandatory `0.4.7` acceptance gate; a later binary cannot make this
`0.4.6` result pass retroactively.

## The approach

The required close is driven by a real agent given a goal-level task, per
[`../README.md`](../README.md). The verdict comes from `trajectory.jsonl`, the
HTTP response, CLI output and both run WebSockets, never from the agent's prose.
Both product surfaces are required:

- API create plus `WS /api/ws/runs/{run_id}` and
  `WS /api/runs/{run_id}/stream`, which cover the phone and raw run contracts;
- the shipped Python `vadgr run` path against the Rust daemon, which creates the
  run and follows its raw stream.

The recorded final attempts did **not** meet the goal-level driver rule. They
prescribed `computer-use__get_platform` by name, and the evidence bundle did not
capture the driving agent CLI transcript or version. They are therefore
diagnostic failure-path attempts, not the three compliant closing passes. The
product command actually used was equivalent to:

```bash
FORGE_API_URL=http://127.0.0.1:9481 PYTHONPATH=. \
  python3 -m cli run \
  --provider anthropic_oauth \
  --model claude-haiku-4-5-20251001 \
  "Use the computer-use get_platform tool exactly once. Then report the returned platform in one sentence and finish. Do not call any other tool."
```

The bounded seam was an acceptance test, not an E2E. It called the Rust seam
binary directly to isolate provider, MCP and cua wiring before the product
attempts:

```bash
VADGR_CUA_BIN=/home/santiago/Santiago/Common/vadgr-computer-use/.venv/bin/vadgr-cua \
  cargo run --locked --bin engine_seam
```

## Prerequisites

The recorded artifact was built from implementation commit `4b7f7ed` on branch
`feat/0.4.6-rust-engine`:

- artifact: `rust/target/release/vadgr-daemon`;
- SHA-256: `6766cd64e00a8f998f220373be2faeb4890877f5a697f56efd175bde22be0321`;
- installed hands: the `vadgr-cua` executable selected by `VADGR_CUA_BIN`;
- live credential: Anthropic subscription OAuth, excluded from evidence;
- host: WSL2;
- final ports: `9481`, `9482`, `9483`;
- isolation: a new config home, database, journal root and daemon per pass.

A repeatable isolated setup for one pass is:

```bash
export E2E_ROOT="$(mktemp -d)"
export VADGR_CONFIG_HOME="$E2E_ROOT/config"
export VADGR_DB="$E2E_ROOT/vadgr.db"
export VADGR_RUNS_DIR="$E2E_ROOT/runs"
export VADGR_CUA_BIN=/home/santiago/Santiago/Common/vadgr-computer-use/.venv/bin/vadgr-cua
export VADGR_PORT=9481
export VADGR_TRANSPORT=loopback
export VADGR_PROVIDERS="$PWD/providers.yaml"
export FORGE_API_URL=http://127.0.0.1:9481
mkdir -p "$VADGR_CONFIG_HOME" "$VADGR_RUNS_DIR"
./rust/target/release/vadgr-daemon
```

Each final database began empty and contains exactly one run. Each pass stopped
only its own daemon and confirmed that its port was released.

## Automated gate (necessary, never sufficient)

| gate | result |
|---|---|
| unchanged Python engine, API and CLI suites | pass: 692 passed |
| Rust all-target suite | pass: 135 passed, 1 Docker-only test ignored |
| `cargo fmt --check` | pass |
| `cargo clippy --all-targets -- -D warnings` | pass |
| Linux musl release build | pass: x86-64 static PIE |
| installed artifact with an empty environment | pass: complete health body |
| clean install in `scratch` | pass: binary installed alone, started and became healthy |
| Windows native CI | pass: build, test, clippy and rustfmt |
| macOS native CI | pass: build, test, clippy and rustfmt |

All ten jobs passed in CI run
[`31928115373`](https://github.com/MONTBRAIN/vadgr/actions/runs/31928115373)
on documentation commit `3ff1fc3`; the implementation artifact is unchanged
from `4b7f7ed`.

These gates prove compilation, isolated installation and deterministic cases.
They cannot prove a live provider turn, an installed MCP child, client-visible
frames, journal durability during real work or recovery after a hard kill.

## Coverage

The owner disposition moves these checks because their supported replacement
provider composition first exists in `0.4.7`. The rows remain blocked here,
not passed or silently deleted.

| check | why it cannot close here | moved to |
|---|---|---|
| compliant three-pass engine close and generated full-surface sweep | the only configured live product provider rejects the full request before a model turn; `0.4.7` removes that provider identity | `0.4.7` |
| hard-kill restart continuation | no full request reached model or tool progress at which a bounded kill could be made | `0.4.7` |
| owner dogfood batch | no product run reached its first model turn or external action | `0.4.7` |
| native Linux, macOS and Windows live engine passes | no live sessions with a real model and cua child were run on those hosts | `0.4.7` |

The inventory has 14 shipped HTTP operations, 19 published CLI invocations, 2
sockets and 30 absent-route probes: 65 surface cells. The engine behavior matrix
has 25 cases: 2 live calls, 8 control tools, 2 content shapes, 1 tool error, 4
terminal outcomes, 3 journal and continuation cases, 2 cancellation timings and
3 cua states.

| Part | Axes | Cells | Run | Open |
|---|---|---:|---:|---:|
| Surface inventory | 14 HTTP + 19 CLI + 2 sockets + 30 absent probes | 65 | 6 | 62 |
| A: bounded seam | 1 composition x 3 observables | 3 | 3 | 0 |
| B: engine behavior | 25 enumerated native-loop cases | 25 | 1 | 24 |
| Repeatability | 3 passes x 6 observables | 18 | 18 | 18 |
| C: restart recovery | 1 restart sequence x 7 assertions | 7 | 0 | 7 |
| D: owner dogfood | 1 batch x 5 recorded outcomes | 5 | 0 | 5 |
| | | **123** | **28** | **116** |

`Run` means the cell was executed and recorded; it does not mean pass. The three
HTTP rows closed in the surface inventory are health, run acceptance and final
run-list read-back. The CLI and both socket rows were observed only on the
blocked failure path and remain open for the successful close.

## Surface coverage - every published endpoint, with what it returned

No `0.4.6` generated full-surface sweep was captured. The inventory below was
derived from the shipped router and CLI registrations, while results come only
from the final recorded attempts. An unobserved row says `not run`; no `0.4.5`
result is reused. Generating and recording all of these rows is part of the
carried `0.4.7` gate.

### Shipped

| endpoint | what was asked | status | code | response, as returned |
|---|---|---|---|---|
| `GET /api/health` | daemon liveness on all three ports | `200` | - | `{"modules":{"computer_use":true},"platform":"wsl","status":"healthy","transport":{"advertise_host":null,"available":true,"bind_host":"127.0.0.1","name":"loopback"},"version":"0.4.6"}` |
| `POST /api/auth/pair` | pairing on the configured transport | not run | - | not captured |
| `POST /api/auth/claim` | invalid and valid claim cases | not run | - | not captured |
| `GET /api/devices` | paired devices | not run | - | not captured |
| `DELETE /api/devices/{device_id}` | existing and unknown device | not run | - | not captured |
| `GET /api/providers` | provider catalogue | not run | - | not captured |
| `GET /api/settings/computer-use` | current cua setting | not run | - | not captured |
| `PUT /api/settings/computer-use` | disable and restore cua | not run | - | not captured |
| `GET /api/computer-use/status` | live cua readiness | not run | - | not captured |
| `GET /api/runs` | final run read-back | `200` | - | one row with the recorded run id, `status:"failed"`, provider `anthropic_oauth`, model `claude-haiku-4-5-20251001` and the live HTTP 400 provider error |
| `POST /api/runs` | start the fixed diagnostic task | `202` | - | run accepted; daemon log records status `202`, and CLI printed the matching `run-...` id |
| `GET /api/runs/{run_id}` | one run detail and unknown-run case | not run | - | not independently captured |
| `POST /api/runs/{run_id}/cancel` | running and terminal states | not run | - | not captured |
| `POST /api/runs/{run_id}/resume` | failed, missing and non-resumable states | not run | - | not captured |

The two observed run responses are not substitutes for the missing generated
records: the daemon log proves the `202`, and the stored `run.json` proves the
terminal list row, but neither enumerates the route's positive and negative
contract cases.

### Not yet built - probed to confirm absent, not half-wired

These required probes were not run at `0.4.6`; their expected absence comes
from the plan, not from this E2E record.

| endpoint | minor | status | response |
|---|---|---|---|
| `GET /api/agents` | removed at `0.4.4` | not run | not captured |
| `POST /api/agents` | removed at `0.4.4` | not run | not captured |
| `GET /api/agents/{agent_id}` | removed at `0.4.4` | not run | not captured |
| `PUT /api/agents/{agent_id}` | removed at `0.4.4` | not run | not captured |
| `DELETE /api/agents/{agent_id}` | removed at `0.4.4` | not run | not captured |
| `DELETE /api/agents` | removed at `0.4.4` | not run | not captured |
| `POST /api/agents/{agent_id}/run` | removed at `0.4.4` | not run | not captured |
| `GET /api/agents/{agent_id}/runs` | removed at `0.4.4` | not run | not captured |
| `GET /api/agents/{agent_id}/export` | removed at `0.4.4` | not run | not captured |
| `POST /api/agents/import` | removed at `0.4.4` | not run | not captured |
| `POST /api/agents/{agent_id}/uploads` | removed at `0.4.4` | not run | not captured |
| `GET /api/projects` | removed at `0.4.4` | not run | not captured |
| `POST /api/projects` | removed at `0.4.4` | not run | not captured |
| `GET /api/projects/{project_id}` | removed at `0.4.4` | not run | not captured |
| `POST /api/projects/{project_id}/runs` | removed at `0.4.4` | not run | not captured |
| `POST /api/projects/{project_id}/validate` | removed at `0.4.4` | not run | not captured |
| `DELETE /api/runs` | removed at `0.4.4` | not run | not captured |
| `POST /api/runs/{run_id}/approve` | removed at `0.4.4` | not run | not captured |
| `GET /api/runs/{run_id}/logs` | removed at `0.4.4` | not run | not captured |
| `GET /api/runs/{run_id}/logs/{file}` | removed at `0.4.4` | not run | not captured |
| `GET /api/runs/{run_id}/outputs/{field}` | removed at `0.4.4` | not run | not captured |
| `GET /api/machine` | `0.6.0` | not run | not captured |
| `PATCH /api/machine` | `0.7.0` | not run | not captured |
| `POST /api/runs/{run_id}/pause` | `0.6.0` | not run | not captured |
| `POST /api/runs/{run_id}/respond` | never built; re-homed to the `0.6.0` conversation message verb | not run | not captured |
| `GET /api/runs/{run_id}/journal` | struck; conversation history is the remote projection | not run | not captured |
| `POST /api/runs/{run_id}/messages` | never built; re-homed to the `0.6.0` conversation message verb | not run | not captured |
| `GET /api/threads` | superseded by `0.6.0` conversations | not run | not captured |
| `GET /api/approvals` | deleted before shipping; asks become conversation turns | not run | not captured |
| `PUT /api/devices/{device_id}/push_token` | `0.8.0` | not run | not captured |

### The CLI

| command | exit | output, as printed |
|---|---:|---|
| `vadgr run <task> --provider anthropic_oauth --model claude-haiku-4-5-20251001` | `1` | `[vadgr] Run started: run-...` then `[vadgr] Run failed (2s): provider request failed: HTTP 400: ... You're out of extra usage ...` |
| `vadgr health` | not run | not captured |
| `vadgr providers` | not run | not captured |
| `vadgr pair` | not run | not captured |
| `vadgr computer-use enable` | not run | not captured |
| `vadgr computer-use disable` | not run | not captured |
| `vadgr computer-use status` | not run | not captured |
| `vadgr runs` | not run | not captured |
| `vadgr runs list` | not run | not captured |
| `vadgr runs get <run_id>` | not run | not captured |
| `vadgr runs cancel <run_id>` | not run | not captured |
| `vadgr runs resume <run_id>` | not run | not captured |
| `vadgr start` | not run | not captured |
| `vadgr api` | not run | not captured |
| `vadgr stop` | not run | not captured |
| `vadgr restart` | not run | not captured |
| `vadgr status` | not run | not captured |
| `vadgr logs` | not run | not captured |
| `vadgr update` | not run | not captured |

The required daemon-down negative CLI case was not run.

### The sockets

| socket | frames | types, as received |
|---|---:|---|
| `WS /api/ws/runs/{run_id}` | 4 per pass | `run_started`, `agent_started`, `agent_failed`, `run_failed` |
| `WS /api/runs/{run_id}/stream` | 3 in A, 4 in B and C | A: `started`, `tool_call`, `failed`; B/C: `started`, `tool_call`, `failed`, `failed` |

The `tool_call` frame is the quarantined mobile mapper's published mapping of
`agent_started`; it does not prove that an MCP call occurred. Likewise,
`agent_failed` and `run_failed` both map to `failed` by the published legacy
vocabulary. These are surprising observations, but they match the current
contract and are not newly classified `0.4.6` defects.

## Part A: the bounded native seam

| # | What | Expected | Status |
|---|---|---|---|
| A1 | live Anthropic Messages request through the Rust provider | a non-mocked model turn with usage | pass |
| A2 | `rmcp` child initialization and `tools/list` against installed cua | the installed server advertises its tools | pass |
| A3 | call `computer-use__get_platform` through the host | tool result is the real host platform | pass |

**Measured.** The seam returned:

```text
provider: anthropic_oauth
tool: computer-use__get_platform
result: wsl2
input tokens: 11223
output tokens: 46
```

This proves the bounded provider, MCP transport and installed cua composition.
It bypasses the daemon HTTP, CLI, sockets and persistent journal, so it cannot
close the product E2E.

## Part B: full product path and engine behavior

| # | What | Expected | Status |
|---|---|---|---|
| B1 | create a run through the shipped CLI against the Rust daemon | HTTP `202` and a run id printed | pass |
| B2 | first live model response through the full product request | journal `response` with nonzero usage | blocked -> F1 |
| B3 | installed cua tool dispatch | matching `in_flight` then `done` records | blocked -> F1 |
| B4 | terminal product outcome | completed row after at least one real action | blocked -> F1 |
| B5 | raw and mobile successful-stream structures | published frames agree with journal phases | blocked -> F1 |
| B6 | complete generated HTTP and CLI sweep | every row has request, response and error code | not run -> `0.4.7` |
| B7 | remaining 24 engine behavior cases | all control, content, outcome, journal, cancel and cua-state cells close | not run -> `0.4.7` |

**Measured.** Each full request received the provider's live HTTP 400 before a
model response. The final three journals contain zero records, so
`computer-use__get_platform` has zero `in_flight` and zero `done` entries and
usage is absent. This is a verified provider-failure path, not successful engine
execution.

## Part C: hard-kill restart continuation

| # | What | Expected | Status |
|---|---|---|---|
| C1 | kill only the tested daemon while a cua call is open | process exits without a graceful close | not run -> `0.4.7` |
| C2 | restart against the same database and journal | same run id continues automatically | not run -> `0.4.7` |
| C3 | journal sequence | sequence continues in the same file | not run -> `0.4.7` |
| C4 | completed side effects | no completed effect repeats | not run -> `0.4.7` |
| C5 | dangling tool call | boot does not blindly redispatch it | not run -> `0.4.7` |
| C6 | live-state inspection | inspection precedes any retry | not run -> `0.4.7` |
| C7 | final agreement | database and both sockets agree with the journal | not run -> `0.4.7` |

No full request reached a model or an open cua call, so performing a kill would
not have tested continuation.

## Part D: owner dogfood batch

| # | What | Expected | Status |
|---|---|---|---|
| D1 | one real owner batch, started by CLI | valid terminal outcome after real work | not run -> `0.4.7` |
| D2 | cua as hands | countable external actions and read-back | not run -> `0.4.7` |
| D3 | deliberate kill inside an open cua call | continuation without duplicate action | not run -> `0.4.7` |
| D4 | cost record | wall time, model calls, input/output tokens and money | not run -> `0.4.7` |
| D5 | owner contact | human-contact count recorded | not run -> `0.4.7` |

This batch is phase-gate evidence, not a readiness request. The owner
disposition requires it in addition to the `0.4.7` provider login checks.

## Repeatability - three independent passes

The final attempts used separate ports, databases, config homes, journal roots
and daemons. They repeated the same diagnostic task concurrently after a
minimal direct Haiku request had returned HTTP 200.

| | `9481` | `9482` | `9483` |
|---|---|---|---|
| run | `run-fb0274a87d6f40aa95e09479c5104791` | `run-eda4beacda7e4a7ba4e81b9778d9c76d` | `run-38b423873e9d46d492f1b787e9ac61cb` |
| HTTP entries | health `200`, start `202`, list `200`, sockets `101` | same | same |
| CLI entries | exit `1`, stdout yes, stderr no | same | same |
| raw / mobile frames | `4 / 3` | `4 / 4` | `4 / 4` |
| journal phases | none | none | none |
| tokens in / out | absent / absent | absent / absent | absent / absent |
| result | blocked | blocked | blocked |

The generated comparison normalized run id, request id, timestamp and port. It
matched provider/model, CLI exit and output presence, raw frame counts, empty
journals, absent usage and the terminal failed status. Mobile A captured one
fewer terminal `failed` frame before socket close; B and C matched exactly.

Input and output token equality cannot be assessed because no model response
returned usage. The repeated absence is a blocker, not repeatability evidence.
The earlier Opus attempts produced the same provider boundary and are retained
in the private bundle, but are not counted as another close.

## Evidence

Private machine-written evidence is under:

```text
e2e_evidence/vadgr-0.4.6/20260815-095540-engine-final/
```

It contains `PRECONDITIONS.md`, `SUMMARY.md`, generated `comparison.json`, its
generator, and per-pass health, daemon, CLI, HTTP row, database, journal and
socket captures. The final run ids are the three ids in the repeatability table.
Earlier diagnostic and retry bundles remain under the same `vadgr-0.4.6`
evidence root. Credentials and authorization headers are excluded.

## Findings

### F1 (open): Anthropic subscription OAuth rejects the full product request before the first model turn

All three Opus attempts and all three final Haiku attempts returned live HTTP
400 `You're out of extra usage` before a response or tool dispatch. Two bounded
follow-up retries did the same. Claude Code `2.1.229` completed a live Opus call
on the same account after refreshing the credential, and a minimal direct Haiku
request returned HTTP 200. The full vadgr request differs by its 8,192-token
output budget, three system blocks and complete control plus MCP tool catalogue.
The evidence does not isolate which field controls the provider's billing
decision.

The path is implemented by `rust/src/engine/provider/anthropic.rs:18-19` and
`:137-163`, and selected as the default in `providers.yaml`. Unit and integration
tests use controlled provider endpoints, so they cannot reproduce an external
subscription entitlement decision. The one-release exception accepts this
finding only because `0.4.7` removes `anthropic_oauth` instead of repairing or
copying a private client identity. `0.4.7` must close the inherited engine cells
through its supported provider composition before acceptance or tagging.

## Per-OS results

Legend: pass / fail / blocked / not run / **Not-Needed**.

| | Linux | macOS | Windows native | WSL |
|---|---|---|---|---|
| automated build and tests | pass in CI | pass in CI | pass in CI | pass locally and in Linux CI |
| Part A: bounded seam | not run | not run | not run | pass |
| Part B: full product path | not run | not run | not run | blocked -> F1 |
| Part C: restart recovery | not run | not run | not run | not run |
| Part D: owner dogfood | not run | not run | not run | not run |
| Overall live E2E | not run | not run | not run | blocked |

No live OS is marked pass from CI. Credential resolution, process launch, path
handling, kill behavior and partial journal writes are platform-shaped, so none
of the other operating systems qualifies as **Not-Needed**. The owner exception
carries these unfinished live obligations with the engine gate.

## What this runbook cannot prove

- A goal-level agent can complete real work through the `0.4.6` product.
- The full model request can return usage and dispatch installed cua.
- All eight control tools, content types, error and terminal outcomes work over
  the product surfaces.
- Every published endpoint, CLI command and planned absent route returns its
  required status, error code and body at `0.4.6`.
- Successful raw and mobile frames agree with a nonempty journal.
- A hard-killed daemon continues the same run without duplicating an external
  action.
- The owner dogfood batch meets its time, cost, call-count and human-contact
  record.
- The live engine composition works on native Linux, macOS or Windows.
- The three diagnostic attempts satisfy the goal-level agent-driver rule or
  successful three-pass close.
