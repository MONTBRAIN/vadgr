# 0.4.5 - Rust daemon without the engine: E2E runbook

The Rust daemon carries the released public surface except for the engine-backed
run routes. This is a split comparison. The unchanged `0.4.4` harness drives
the Python daemon. A wrapper selects Rust cells and classifies each difference
as compatibility, a target correction or a regression.

> **Status: partial on WSL2, updated 2026-08-14.** Three independent Codex CLI 0.147.0
> processes ran concurrently. Each pass owned two ports, two databases, and two
> daemons. All three passes produced the same structural result. The Rust side
> passed 44 HTTP cells, 14 CLI cells, 17 assertions, and two socket close cells.
> The comparison matched 35 shared HTTP cells and all 14 CLI cells. The
> Python daemon supplied the engine-backed cells. Those Rust cells are **held
> for 0.4.6**. The overall result is therefore **partial**, not pass.

## Held before the run

The Rust daemon has no engine in this release. These cells need a Rust-created
run and are held for `0.4.6`:

- start a run from a task
- reject each invalid run-start body
- cancel the run that was started
- resume the cancelled run
- read the created run by id
- probe the removed run routes with the created run id
- connect both run sockets to an existing run and compare replay and live frames
- compare the fixed fixture's token counts

The negative missing-run detail and cancel cells ran against Rust. A seeded
active Rust row also proved that cancel records `cancelled` and stamps
`completed_at`. Both missing-run sockets accepted and then closed with `4004`.

## Automated gate

The automated gate is necessary and does not replace this runbook.

- `PYTHONPATH=. python3 -m pytest engine/tests/ -q` -> **122 passed**
- `PYTHONPATH=. python3 -m pytest api/tests/ -q` -> **429 passed**
- `PYTHONPATH=. python3 -m pytest cli/tests/ -q` -> **141 passed**
- `cargo test --locked` -> **109 passed**
- `cargo clippy --all-targets -- -D warnings` -> **pass**
- `cargo fmt --check` -> **pass**

## Isolation and driver

The evidence harness was present before the first final pass. It owns only its
own daemon process ids and confirms that its ports are free after cleanup.
Computer-use state uses an isolated daemon configuration home and a local fake
`vadgr-cua` executable. No external agent configuration exists in the pass.

| pass | Python port | Rust port | sweep run id | socket run id |
|---|---:|---:|---|---|
| A | 9441 | 9451 | `62689880-9058-4efe-922b-8795924c88e7` | `63e0b093-88a9-40a4-8058-916b55604395` |
| B | 9442 | 9452 | `d69287dc-c3fb-4307-bf88-d18a2c0539d6` | `7cb88362-2e94-4f14-aeb1-fb9a19498b6d` |
| C | 9443 | 9453 | `9aa11ab6-941e-4e9a-8344-186615d94d75` | `68fa8563-12c0-4597-ad82-ee1154b30302` |

The Python model runs reached the native loop and produced both socket streams.
They ended as `failed` because the Anthropic subscription had no remaining
usage. The raw stream had one each of `run_started`, `agent_started`,
`agent_failed`, and `run_failed`. The mobile stream had one each of `started`,
`tool_call`, and `failed`. No token count exists for a provider call that did
not run. This does not promote any held Rust cell to pass.

## Coverage

| axis | result per pass |
|---|---|
| Rust HTTP surface | 44 calls, 17 assertions, 0 failures |
| Rust CLI surface | 14 commands, all expected exits and non-empty output |
| Shared Python/Rust HTTP | 35 method/path/status/code matches |
| Classified bodies | devices match; native-only providers, detected platform, daemon-owned settings, and honest computer-use status pass |
| Rust sockets | both missing-run upgrades close with `4004` after accept |
| Python engine-backed surface | 12 HTTP cells and both existing-run sockets recorded |
| Rust engine-backed surface | held for `0.4.6` |

All published Rust endpoints and all published CLI commands appear in the
generated tables below. Removed and future surfaces are also probed.

Pass B recorded one `-1.02` second HTTP duration in the released Python
baseline. The other Python passes and every Rust record had no negative
duration. This is a baseline measurement defect. The Rust migration does not
port it.

## Repeatability

| pass | Python HTTP | Rust HTTP | shared HTTP | CLI | result |
|---|---:|---:|---:|---:|---|
| A | 49 | 44 | 35 | 14 | partial, no runnable failure |
| B | 49 | 44 | 35 | 14 | partial, no runnable failure |
| C | 49 | 44 | 35 | 14 | partial, no runnable failure |

The Rust logs contain 54 request records in each pass. No comparison reported a
method, path, status, code, CLI or classified-body mismatch. The final cleanup
left no listener on any pass port.

## Findings fixed before the final passes

| id | finding | correction and regression test |
|---|---|---|
| F1 | Loaded provider entries were all reported unavailable because the internal validity flag was skipped during deserialization. | Loaded valid entries now default to valid; malformed entries remain unavailable. |
| F2 | JSON extraction errors differed from the Python 422 response. | Claim and settings routes map malformed and missing-content-type bodies to 422. |
| F3 | The first implementation flattened WebSocket refusals to HTTP 403. | Superseded by F12: target close codes now reach the client. |
| F4 | Tailscale startup bound one address and failed when the local API was unavailable. | The daemon binds the advertised address and loopback, or falls back to loopback. |
| F5 | Device timestamps used `+00:00` instead of the published `Z`. | The wire mapper normalizes UTC timestamps. |
| F6 | Computer-use settings only changed an in-memory flag. | Superseded by F14: Rust now persists daemon-owned state only. |
| F7 | Hostname lookup depended on `/etc/hostname`, and Windows lacked the tailscaled named-pipe path. | The daemon uses the platform hostname API and implements the Windows pipe client. |
| F8 | CLI output wrapped differently under a non-interactive terminal. | The stable console fixes both width and height; the full CLI suite now passes. |
| F9 | Provider and computer-use reads repeated slow subprocess probes. | Rust removes external agent CLI probes. Cua runtime discovery starts no process. |
| F10 | The Rust evidence log contained no request or response records. | The HTTP trace layer now records each request and status; the harness checks the health request. |
| F11 | Health hardcoded every host as `wsl2`. | Rust detects `linux`, `macos`, `windows` or `wsl`; platform classification has a regression test. |
| F12 | Auth and missing-run sockets closed before the upgrade, so clients lost `4401` and `4004`. | Rust accepts first and closes with the stable code; a real TCP upgrade and the e2e socket client cover it. |
| F13 | Cancel copied Python's `failed` status for a deliberate stop. | Rust records `cancelled` and stamps completion; route, repository and e2e checks cover it. |
| F14 | The setup service edited `.mcp.json`, Gemini settings and Codex global settings. | Rust writes only daemon-owned `settings.json`, preserves unrelated keys and does not install a runtime. |
| F15 | Rust deserialized and probed deprecated subprocess providers. | The catalog accepts native entries only and starts no external agent process. |

F1 was captured in all three failed pre-fix passes. Those records remain in the
private evidence bundle. The final passes ran after every fix.

## Comparison boundaries

The generic bodies for removed and future routes are not equal. FastAPI usually
returns `{"detail":"Not Found"}`. Axum returns an empty body. The approved stop
condition compares method, path, status, and application error code for these
routes. The target-body checks separately require native-only providers,
daemon-owned settings, unavailable computer use without an engine, and a
detected platform. The generated tables keep each difference visible. No
released application error envelope differs in the final comparison.

## Per-OS result

| platform | live HTTP/CLI | live sockets | overall |
|---|---|---|---|
| WSL2 | partial: all runnable cells pass | partial: missing-run close cells pass; existing-run cells held | **partial** |
| Linux | not run | not run | **not run** |
| Windows native | not run | not run | **not run** |
| macOS | not run | not run | **not run** |

CI does not count as a live per-OS pass. The first packaged four-platform sweep
belongs to `0.5.0`. The held engine cells first run at `0.4.6`.

### Cross-platform path audit and repeated WSL2 live pass

The path audit does not promote any `not run` row above. The three final WSL2
passes repeated every runnable cell after the audit. The audit added native unit
coverage for XDG, macOS Application Support, Windows roaming AppData and
`PATHEXT`, Unix executable bits, non-UTF-8 paths, macOS and Windows tailscaled
endpoints, replacement of an existing settings file, IPv6 loopback and
listener addresses, creation of missing database parents, malformed settings
and invalid toggle values. The GitHub Rust matrix runs these tests and Clippy
on Ubuntu, native Windows and macOS. CI is still not live E2E.

## Generated results

The tables below were generated from pass A's final JSON records. The response
text is truncated only by the table generator. The private evidence bundle is
keyed by the run ids above. It contains records, daemon logs, driver streams,
the first target-correction passes, the final repeated passes, failed pre-fix
passes, and the baseline harness with its target-aware selector.

### Rust HTTP cells

| endpoint | case | status | code | response, as returned |
|---|---|---|---|---|
| `GET /api/health` | daemon liveness | `200` | - | `{"modules":{"computer_use":true},"platform":"wsl","status":"healthy","transport":{"advertise_host":null,"available":true ...` |
| `POST /api/auth/pair` | pairing on loopback refuses | `503` | `TRANSPORT_UNREACHABLE` | `{"error":{"code":"TRANSPORT_UNREACHABLE","details":{"transport":"loopback"},"message":"Transport cannot advertise a reac ...` |
| `POST /api/auth/claim` | negative: an invalid pairing code | `401` | `PAIRING_CODE_INVALID` | `{"error":{"code":"PAIRING_CODE_INVALID","details":{},"message":"That pairing code is wrong or has already been used."}}` |
| `GET /api/providers` | the native provider catalogue | `200` | - | `[{"available":true,"id":"anthropic_oauth","models":[{"id":"claude-opus-5","name":"Claude Opus 5"},{"id":"claude-sonnet-5 ...` |
| `GET /api/devices` | paired phones | `200` | - | `[]` |
| `DELETE /api/devices/no-such-device` | negative: unknown device | `404` | `DEVICE_NOT_FOUND` | `{"error":{"code":"DEVICE_NOT_FOUND","details":{},"message":"Device 'no-such-device' not found."}}` |
| `GET /api/settings/computer-use` | computer-use settings | `200` | - | `{"daemon":null,"enabled":true,"platform":"wsl2","venv_ready":true}` |
| `PUT /api/settings/computer-use` | disable computer use in the isolated setup | `200` | - | `{"daemon":null,"enabled":false,"platform":"wsl2","venv_ready":true}` |
| `PUT /api/settings/computer-use` | restore computer use in the isolated setup | `200` | - | `{"daemon":null,"enabled":true,"platform":"wsl2","venv_ready":true}` |
| `GET /api/computer-use/status` | computer-use status | `200` | - | `{"available":false,"platform":"wsl2"}` |
| `GET /api/runs` | run list without a run | `200` | - | `[]` |
| `GET /api/runs/no-such-run` | negative: unknown run | `404` | `RUN_NOT_FOUND` | `{"error":{"code":"RUN_NOT_FOUND","details":{},"message":"Run with id 'no-such-run' not found"}}` |
| `POST /api/runs/no-such-run/cancel` | negative: unknown run | `404` | `RUN_NOT_FOUND` | `{"error":{"code":"RUN_NOT_FOUND","details":{},"message":"Run with id 'no-such-run' not found"}}` |
| `POST /api/runs/cancel-target/cancel` | cancel an existing Rust run | `200` | - | `{"agent_name":"cancel target","completed_at":"2026-08-15T00:45:41.021667+00:00","id":"cancel-target","inputs":{},"log_pa ...` |
| `GET /api/agents` | removed at 0.4.4: the agent list | `404` | - | `` |
| `POST /api/agents` | removed at 0.4.4: agent creation | `404` | - | `` |
| `GET /api/agents/no-such-agent` | removed at 0.4.4: one agent | `404` | - | `` |
| `PUT /api/agents/no-such-agent` | removed at 0.4.4: agent update | `404` | - | `` |
| `DELETE /api/agents/no-such-agent` | removed at 0.4.4: agent deletion | `404` | - | `` |
| `DELETE /api/agents` | removed at 0.4.4: delete every agent | `404` | - | `` |
| `POST /api/agents/no-such-agent/run` | removed at 0.4.4: the old trigger | `404` | - | `` |
| `GET /api/agents/no-such-agent/runs` | removed at 0.4.4: an agent's runs | `404` | - | `` |
| `GET /api/agents/no-such-agent/export` | removed at 0.4.4: agent export | `404` | - | `` |
| `POST /api/agents/import` | removed at 0.4.4: agent import | `404` | - | `` |
| `POST /api/agents/no-such-agent/uploads` | removed at 0.4.4: an agent's input upload | `404` | - | `` |
| `GET /api/projects` | removed at 0.4.4: the project list | `404` | - | `` |
| `POST /api/projects` | removed at 0.4.4: project creation | `404` | - | `` |
| `GET /api/projects/no-such-project` | removed at 0.4.4: one project | `404` | - | `` |
| `POST /api/projects/no-such-project/runs` | removed at 0.4.4: the project trigger | `404` | - | `` |
| `POST /api/projects/no-such-project/validate` | removed at 0.4.4: DAG validation | `404` | - | `` |
| `DELETE /api/runs` | removed at 0.4.4: delete every run | `405` | - | `` |
| `POST /api/runs/held-run/approve` | removed at 0.4.4: the approval gate | `404` | - | `` |
| `GET /api/runs/held-run/logs` | removed at 0.4.4: the run's log events | `404` | - | `` |
| `GET /api/runs/held-run/logs/step_01_a.jsonl` | removed at 0.4.4: one step's log file | `404` | - | `` |
| `GET /api/runs/held-run/outputs/result` | removed at 0.4.4: an output field | `404` | - | `` |
| `GET /api/machine` | not built until 0.6.0 | `404` | - | `` |
| `PATCH /api/machine` | not built until 0.6.0 | `404` | - | `` |
| `POST /api/runs/no-such-run/pause` | not built until 0.6.0 | `404` | - | `` |
| `POST /api/runs/no-such-run/respond` | not built until 0.5.0 | `404` | - | `` |
| `GET /api/runs/no-such-run/journal` | not built until 0.5.0 | `404` | - | `` |
| `POST /api/runs/no-such-run/messages` | not built until 0.6.0 | `404` | - | `` |
| `GET /api/threads` | not built until 0.6.0 | `404` | - | `` |
| `GET /api/approvals` | not built until 0.7.0 | `404` | - | `` |
| `PUT /api/devices/probe/push_token` | not built until 0.7.0 | `404` | - | `` |

### Rust CLI cells

| command | exit | output produced | first output |
|---|---|---|---|
| `vadgr health` | `0` | yes | `Status: healthy Version: 0.4.5 Platform: wsl Modules: computer_use: available` |
| `vadgr status` | `0` | yes | `Service PID Status api - stopped` |
| `vadgr providers` | `0` | yes | `Anthropic (OAuth, subscription) (anthropic_oauth) -- available - Claude Opus 5 (claude-opus-5) - Claude Sonnet 5 (claude-sonnet-5) ...` |
| `vadgr runs list` | `0` | yes | `Run ID Task Status Duration cancel-t cancel target cancelled -` |
| `vadgr --help` | `0` | yes | `Usage: python -m cli [OPTIONS] COMMAND [ARGS]... vadgr CLI. Options: --help Show this message and exit. Commands: api Start the va ...` |
| `vadgr runs --help` | `0` | yes | `Usage: python -m cli runs [OPTIONS] COMMAND [ARGS]... Manage runs. Options: --help Show this message and exit. Commands: cancel Ca ...` |
| `vadgr health` | `3` | yes | `Error: API is not running at http://127.0.0.1:9. Start it with: vadgr start` |
| `vadgr run  --background` | `2` | yes | `Usage: python -m cli run [OPTIONS] TASK Try 'python -m cli run --help' for help. Error: TASK must not be empty.` |
| `vadgr run x --provider codex --background` | `2` | yes | `Usage: python -m cli run [OPTIONS] TASK Try 'python -m cli run --help' for help. Error: --provider and --model must be given toget ...` |
| `vadgr agents list` | `2` | yes | `Usage: python -m cli [OPTIONS] COMMAND [ARGS]... Try 'python -m cli --help' for help. Error: No such command 'agents'.` |
| `vadgr ps` | `2` | yes | `Usage: python -m cli [OPTIONS] COMMAND [ARGS]... Try 'python -m cli --help' for help. Error: No such command 'ps'.` |
| `vadgr registry list` | `2` | yes | `Usage: python -m cli [OPTIONS] COMMAND [ARGS]... Try 'python -m cli --help' for help. Error: No such command 'registry'.` |
| `vadgr runs approve x` | `2` | yes | `Usage: python -m cli runs [OPTIONS] COMMAND [ARGS]... Try 'python -m cli runs --help' for help. Error: No such command 'approve'.` |
| `vadgr runs logs x` | `2` | yes | `Usage: python -m cli runs [OPTIONS] COMMAND [ARGS]... Try 'python -m cli runs --help' for help. Error: No such command 'logs'.` |

### Python cells held on Rust

| endpoint | case | status | code | response, as returned |
|---|---|---|---|---|
| `POST /api/runs` | start a run from a task | `202` | - | `{"id":"{run}","agent_name":"Write the single line 'vadgr 0.4.4 sweep' to /tmp/vadgr-sweep-fixture.txt, then say DONE."," ...` |
| `POST /api/runs/{run}/cancel` | cancel the run just started | `200` | - | `{"id":"{run}","agent_name":"Write the single line 'vadgr 0.4.4 sweep' to /tmp/vadgr-sweep-fixture.txt, then say DONE."," ...` |
| `POST /api/runs/{run}/resume` | resume the cancelled run | `200` | - | `{"run_id":"{run}","status":"running","message":"Resuming"}` |
| `POST /api/runs` | negative: an empty task | `422` | - | `{"detail":[{"type":"value_error","loc":["body"],"msg":"Value error, task must not be empty","input":{"task":""},"ctx":{" ...` |
| `POST /api/runs` | negative: no task at all | `422` | - | `{"detail":[{"type":"missing","loc":["body","task"],"msg":"Field required","input":{}}]}` |
| `POST /api/runs` | negative: a provider with no model | `422` | - | `{"detail":[{"type":"value_error","loc":["body"],"msg":"Value error, provider and model must be provided together","input ...` |
| `POST /api/runs` | negative: the old body's inputs key | `422` | - | `{"detail":[{"type":"extra_forbidden","loc":["body","inputs"],"msg":"Extra inputs are not permitted","input":{"topic":"AI ...` |
| `GET /api/runs/{run}` | the run, settled | `200` | - | `{"id":"{run}","agent_name":"Write the single line 'vadgr 0.4.4 sweep' to /tmp/vadgr-sweep-fixture.txt, then say DONE."," ...` |
| `POST /api/runs/{run}/approve` | removed at 0.4.4: the approval gate | `404` | - | `{"detail":"Not Found"}` |
| `GET /api/runs/{run}/logs` | removed at 0.4.4: the run's log events | `404` | - | `{"detail":"Not Found"}` |
| `GET /api/runs/{run}/logs/step_01_a.jsonl` | removed at 0.4.4: one step's log file | `404` | - | `{"detail":"Not Found"}` |
| `GET /api/runs/{run}/outputs/result` | removed at 0.4.4: an output field | `404` | - | `{"detail":"Not Found"}` |

### Socket cells

| daemon | socket | result |
|---|---|---|
| Python | raw run stream | `{"agent_failed": 1, "agent_started": 1, "run_failed": 1, "run_started": 1}` |
| Python | mobile run stream | `{"failed": 1, "started": 1, "tool_call": 1}` |
| Rust | `WS /api/ws/runs/missing` missing run | accepted, close `4004` |
| Rust | `WS /api/runs/missing/stream` missing run | accepted, close `4004` |
