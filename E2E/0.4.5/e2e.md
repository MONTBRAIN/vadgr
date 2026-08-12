# 0.4.5 - Rust daemon without the engine: E2E runbook

The Rust daemon reproduces the Python daemon's public surface except for the
engine-backed run routes. This is a split comparison. The unchanged `0.4.4`
harness drives the Python daemon. A wrapper selects only cells that do not need
a run for the Rust daemon.

> **Status: partial on WSL2, 2026-08-12.** Three independent Codex CLI 0.147.0
> processes ran concurrently. Each pass owned two ports, two databases, and two
> daemons. All three passes produced the same structural result. The Rust side
> passed 43 HTTP cells, 14 CLI cells, 11 assertions, and two negative socket
> cells. The comparison matched 35 shared HTTP cells and all 14 CLI cells. The
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

The negative missing-run detail, cancel, and socket cells did run against Rust.

## Automated gate

The automated gate is necessary and does not replace this runbook.

- `PYTHONPATH=. python3 -m pytest engine/tests/ -q` -> **122 passed**
- `PYTHONPATH=. python3 -m pytest api/tests/ -q` -> **429 passed**
- `PYTHONPATH=. python3 -m pytest cli/tests/ -q` -> **141 passed**
- `cargo test --locked` -> **91 passed**
- `cargo clippy --all-targets -- -D warnings` -> **pass**
- `cargo fmt --check` -> **pass**

## Isolation and driver

The evidence harness was present before the first final pass. It owns only its
own daemon process ids and confirms that its ports are free after cleanup.
Computer-use setup uses isolated project and configuration homes and a local
fake `vadgr-cua` executable. It does not edit the workstation's real agent
configuration.

| pass | Python port | Rust port | sweep run id | socket run id |
|---|---:|---:|---|---|
| A | 8981 | 8991 | `f187204d-5b36-4fa1-8003-023e229e87f0` | `fa91e95f-2a79-4258-bbcc-b251f2c747d2` |
| B | 8982 | 8992 | `7f924c77-9e2c-4139-a90e-de8e564e0b55` | `1b6a03d5-0b8b-49c0-99e4-4f7b606849e5` |
| C | 8983 | 8993 | `f924a4fb-4ac8-4d79-ba16-6d84de4bdac0` | `e74b5535-4f27-4c32-848e-148ee8b989e9` |

The Python model runs reached the native loop and produced both socket streams.
They ended as `failed` because the Anthropic subscription had no remaining
usage. The raw stream had one each of `run_started`, `agent_started`,
`agent_failed`, and `run_failed`. The mobile stream had one each of `started`,
`tool_call`, and `failed`. No token count exists for a provider call that did
not run. This does not promote any held Rust cell to pass.

## Coverage

| axis | result per pass |
|---|---|
| Rust HTTP surface | 43 calls, 11 assertions, 0 failures |
| Rust CLI surface | 14 commands, all expected exits and non-empty output |
| Shared Python/Rust HTTP | 35 method/path/status/code matches |
| Shared Python/Rust bodies | providers, devices, settings, and computer-use status match |
| Rust sockets | both missing-run handshakes refuse with HTTP 403 |
| Python engine-backed surface | 12 HTTP cells and both existing-run sockets recorded |
| Rust engine-backed surface | held for `0.4.6` |

All published Rust endpoints and all published CLI commands appear in the
generated tables below. Removed and future surfaces are also probed.

## Repeatability

| pass | Python HTTP | Rust HTTP | shared HTTP | CLI | result |
|---|---:|---:|---:|---:|---|
| A | 49 | 43 | 35 | 14 | partial, no runnable failure |
| B | 49 | 43 | 35 | 14 | partial, no runnable failure |
| C | 49 | 43 | 35 | 14 | partial, no runnable failure |

The longest expected negative command was the unreachable-daemon health check
at 1.6 seconds on both targets. The cached Rust provider and computer-use reads
completed in at most 0.01 seconds. No observer reported an unexplained timing
or ordering difference. The final cleanup left no listener on any pass port.

## Findings fixed before the final passes

| id | finding | correction and regression test |
|---|---|---|
| F1 | Loaded provider entries were all reported unavailable because the internal validity flag was skipped during deserialization. | Loaded valid entries now default to valid; malformed entries remain unavailable. |
| F2 | JSON extraction errors differed from the Python 422 response. | Claim and settings routes map malformed and missing-content-type bodies to 422. |
| F3 | WebSocket refusals returned several pre-upgrade statuses. | Every pre-accept refusal now returns the Python/Uvicorn HTTP 403. |
| F4 | Tailscale startup bound one address and failed when the local API was unavailable. | The daemon binds the advertised address and loopback, or falls back to loopback. |
| F5 | Device timestamps used `+00:00` instead of the published `Z`. | The wire mapper normalizes UTC timestamps. |
| F6 | Computer-use settings only changed an in-memory flag. | Rust now performs the same isolated setup and removal as Python. |
| F7 | Hostname lookup depended on `/etc/hostname`, and Windows lacked the tailscaled named-pipe path. | The daemon uses the platform hostname API and implements the Windows pipe client. |
| F8 | CLI output wrapped differently under a non-interactive terminal. | The stable console fixes both width and height; the full CLI suite now passes. |
| F9 | Provider and computer-use reads repeated slow subprocess probes. | The daemon probes once at startup and updates the cached settings state after a PUT. |
| F10 | The Rust evidence log contained no request or response records. | The HTTP trace layer now records each request and status; the harness checks the health request. |

F1 was captured in all three failed pre-fix passes. Those records remain in the
private evidence bundle. The final passes ran after every fix.

## Comparison boundaries

The generic bodies for removed and future routes are not equal. FastAPI usually
returns `{"detail":"Not Found"}`. Axum returns an empty body. The approved stop
condition compares method, path, status, and application error code for these
routes. The generated tables keep the body difference visible. No shipped
application error envelope differs in the final comparison.

## Per-OS result

| platform | live HTTP/CLI | live sockets | overall |
|---|---|---|---|
| WSL2 | partial: all runnable cells pass | partial: Rust negative cells pass; existing-run cells held | **partial** |
| Linux | not run | not run | **not run** |
| Windows native | not run | not run | **not run** |
| macOS | not run | not run | **not run** |

CI does not count as a live per-OS pass. The first packaged four-platform sweep
belongs to `0.5.0`. The held engine cells first run at `0.4.6`.

## Generated results

The tables below were generated from pass A's final JSON records. The response
text is truncated only by the table generator. The private evidence bundle is
keyed by the run ids above. It contains records, daemon logs, driver streams,
failed pre-fix passes, and the unchanged harness.

### Rust HTTP cells

| endpoint | case | status | code | response, as returned |
|---|---|---|---|---|
| `GET /api/health` | daemon liveness | `200` | - | `{"modules":{"computer_use":true},"platform":"wsl2","status":"healthy","transport":{"advertise_host":null,"available":tru ...` |
| `POST /api/auth/pair` | pairing on loopback refuses | `503` | `TRANSPORT_UNREACHABLE` | `{"error":{"code":"TRANSPORT_UNREACHABLE","details":{"transport":"loopback"},"message":"Transport cannot advertise a reac ...` |
| `POST /api/auth/claim` | negative: an invalid pairing code | `401` | `PAIRING_CODE_INVALID` | `{"error":{"code":"PAIRING_CODE_INVALID","details":{},"message":"That pairing code is wrong or has already been used."}}` |
| `GET /api/providers` | the provider catalogue | `200` | - | `[{"available":true,"id":"anthropic_oauth","models":[{"id":"claude-opus-5","name":"Claude Opus 5"},{"id":"claude-sonnet-5 ...` |
| `GET /api/devices` | paired phones | `200` | - | `[]` |
| `DELETE /api/devices/no-such-device` | negative: unknown device | `404` | `DEVICE_NOT_FOUND` | `{"error":{"code":"DEVICE_NOT_FOUND","details":{},"message":"Device 'no-such-device' not found."}}` |
| `GET /api/settings/computer-use` | computer-use settings | `200` | - | `{"daemon":"running","enabled":true,"platform":"wsl2","venv_ready":true}` |
| `PUT /api/settings/computer-use` | disable computer use in the isolated setup | `200` | - | `{"daemon":null,"enabled":false,"platform":"wsl2","venv_ready":true}` |
| `PUT /api/settings/computer-use` | restore computer use in the isolated setup | `200` | - | `{"daemon":"running","enabled":true,"platform":"wsl2","venv_ready":true}` |
| `GET /api/computer-use/status` | computer-use status | `200` | - | `{"available":true,"platform":"wsl2"}` |
| `GET /api/runs` | run list without a run | `200` | - | `[]` |
| `GET /api/runs/no-such-run` | negative: unknown run | `404` | `RUN_NOT_FOUND` | `{"error":{"code":"RUN_NOT_FOUND","details":{},"message":"Run with id 'no-such-run' not found"}}` |
| `POST /api/runs/no-such-run/cancel` | negative: unknown run | `404` | `RUN_NOT_FOUND` | `{"error":{"code":"RUN_NOT_FOUND","details":{},"message":"Run with id 'no-such-run' not found"}}` |
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
| `vadgr health` | `0` | yes | `Status: healthy Version: 0.4.5 Platform: wsl2 Modules: computer_use: available` |
| `vadgr status` | `0` | yes | `Service PID Status api - stopped daemon - running` |
| `vadgr providers` | `0` | yes | `Anthropic (OAuth, subscription) (anthropic_oauth) -- available - Claude Opus 5 (claude-opus-5) - Claude Sonnet 5 (claude-sonnet-5) ...` |
| `vadgr runs list` | `0` | yes | `[vadgr] No runs found.` |
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
| Rust | `WS /api/ws/runs/missing` missing run | HTTP `403` |
| Rust | `WS /api/runs/missing/stream` missing run | HTTP `403` |
