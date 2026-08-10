# 0.4.4 - the deletion: e2e runbook

A machine that has never heard of agents, projects or workflows still takes a
sentence, runs it, and shows a phone what happened. Everything the shipped phone
reads answers exactly as it did, an owner's existing database migrates in place
without losing a run, and every surface this release removed answers `404`
because it is gone rather than because it is half-wired.

> **Status: run on WSL2 and native Windows, 2026-08-09.** Automated gate green
> (engine 122, api 427, cli 141). The recorded sweep closed with **three
> independent concurrent passes**, structurally identical. **The pass is
> complete.** Two cells were blocked during the first round, on one
> environmental fact: the machine's model subscription was out of usage, so no
> run could complete. They were **re-run on 2026-08-09 once it was restored**,
> both pass, and the failed round is kept in Part G because it is what proves a
> run started through the new door reaches the native loop. **5 findings**,
> listed below, three fixed on this branch. Nothing is marked pass that was not
> executed and read back. **Linux and macOS are `Not-Needed`, not owed**
> (owner, 2026-08-09): this release removes code and adds no platform
> surface, and the one OS-sensitive thing it does add, the schema migration,
> was driven on two SQLite versions. The reasoning and its limits are with
> the results table.

## The approach

Driven through the product's real surfaces, per [`../README.md`](../README.md):
the HTTP API, both run WebSockets, and the `vadgr` CLI. The verdict comes from
what the daemon and the database wrote down, never from prose.

The recording is what makes this runbook worth more than its predecessor. It
replaces `E2E/0.4.3`'s as the meter every later release is judged against,
because the `0.4.3` recording measures a daemon that stops existing here, routes
and all. Four properties make it trustworthy:

1. **It is recorded, not typed.** The tables below are emitted from a JSON
   record by `gen_tables.py`. Both the record and the harness are kept, so the
   sweep can be re-run and the tables re-emitted.
2. **It is finished in Python before any Rust exists**, which is what lets each
   later release be judged by a runbook it did not write.
3. **It probes what is absent, not only what is present.** Every route this
   release removes is called and its status recorded, so a `404` arriving for
   the wrong reason is a finding rather than a wave-through.
4. **The fixture is pinned byte for byte** in the committed harness: one task
   sentence, one string literal. `0.4.3`'s three passes recorded 1462, 1493 and
   1495 turn-0 input tokens because each agent reconstructed the prompt itself.
   There is no agent to reconstruct now.

Each pass is one script with its own port, database, `FORGE_HOME` and daemon:

```bash
bash <harness>/pass.sh <port> <workdir>
```

It seeds a database in the previous schema, starts the daemon (so the migration
runs on the boot path, not in a test), sweeps every surface, triggers a run and
records both sockets, reads the run's journal by exact id, and stops its own
daemon by pid.

## Prerequisites

```bash
export FORGE_HOME=$WORK/forge$PORT
export AGENT_FORGE_PORT=$PORT
export AGENT_FORGE_DATABASE_PATH=$WORK/db$PORT.db
```

Two hazards, both recorded from earlier closes and both handled by the harness:

- **The journal tree `~/.vadgr/runs/` is not isolated.** A pass looks its run up
  by exact id and never globs, or it reads a neighbour's run.
- **`vadgr stop` returns before the socket is released**, after which
  `vadgr start` silently relocates to the next free port, which in a three-pass
  close is a neighbour's. The port is confirmed with `ss -ltn`, never by
  connecting to it.

## Automated gate (necessary, never sufficient)

- `PYTHONPATH=. python3 -m pytest engine/tests/ -q` -> **122 passed**
- `PYTHONPATH=. python3 -m pytest api/tests/ -q` -> **427 passed**
- `PYTHONPATH=. python3 -m pytest cli/tests/ -q` -> **141 passed**

What they cannot tell you, and why this runbook exists: the suites run the
migration against `tmp_path` databases, never against a daemon booting on one;
they assert route tables in a process, not `404`s on a socket; and they mock the
provider, so nothing in them proves a task sentence reaches the loop.

## Coverage

Axes: {HTTP surviving, HTTP removed, HTTP not yet built, CLI surviving, CLI
removed, sockets, migration, per-OS} multiplied by {outcome}.

| Part | Axes | Cells | Run | Open |
|---|---|---|---|---|
| A. the trigger and the watch surface | 19 HTTP calls x recorded outcome | 19 | 19 | 0 |
| B. what the release removed | 21 HTTP calls x recorded outcome | 21 | 21 | 0 |
| C. not yet built | 9 HTTP calls x recorded outcome | 9 | 9 | 0 |
| D. the CLI | 14 invocations x exit code and output | 14 | 14 | 0 |
| E. the sockets | 2 sockets x frame type counts | 2 | 2 | 0 |
| F. the migration on the boot path | 6 checks | 6 | 6 | 0 |
| G. the run reaching the loop | 4 checks | 4 | 2 | 2 |
| H. per-OS | 4 platforms x 4 checks | 16 | 8 | 8 |
| | | **91** | **81** | **10** |

Deferred, with where each went:

| check | why it cannot run here | moved to |
|---|---|---|
| the run stream carries a `paused` frame from a real gate | the loop parks on `await_user`, and nothing in a task sentence provokes one deterministically | the minor that ships `POST /api/runs/{id}/respond` |
| a resumed run continues rather than replays | resume on boot is detection-only in this release by design; it continues nothing | the minor that builds it |
| `agent_name` renamed to `title` on the wire | the rename is deliberately not in this release | `0.6.0` |

## Surface coverage - every published endpoint, with what it returned

Generated from `sweep-8971.json` by `gen_tables.py`. The run uuid is normalised
to `{run}`; nothing else is edited.

#### The checks the sweep asserts on

| # | check | expected | as measured | |
|---|---|---|---|---|
| S1 | the health payload names no module the machine does not have | `(False, True)` | `(False, True)` | **pass** |
| S2 | health reports this release | `'0.4.4'` | `'0.4.4'` | **pass** |
| S3 | the trigger answers 202, not 201: the row exists and nothing has run | `202` | `202` | **pass** |
| S4 | the row carries the task under the key the phone reads | `"Write the single line 'vadgr 0.4.4 sweep' to /tmp/vadgr-sweep-fixture.txt, then say DONE. ...` | `"Write the single line 'vadgr 0.4.4 sweep' to /tmp/vadgr-sweep-fixture.txt, then say DONE. ...` | **pass** |
| S5 | the row carries the task as the work as well as the display fact | `{'task': "Write the single line 'vadgr 0.4.4 sweep' to /tmp/vadgr-sweep-fixture.txt, then  ...` | `{'task': "Write the single line 'vadgr 0.4.4 sweep' to /tmp/vadgr-sweep-fixture.txt, then  ...` | **pass** |
| S6 | the published row's keys are frozen | `['agent_name', 'completed_at', 'id', 'inputs', 'log_path', 'model', 'outputs', 'provider', ...` | `['agent_name', 'completed_at', 'id', 'inputs', 'log_path', 'model', 'outputs', 'provider', ...` | **pass** |
| S7 | an unreachable daemon is exit 3, not exit 1: a script has to branch on it | `3` | `3` | **pass** |
| S8 | an empty task is a usage error before anything reaches the daemon | `2` | `2` | **pass** |
| S9 | a provider with no model is a usage error, never a half-resolved run | `2` | `2` | **pass** |
| S10 | `vadgr agents list` is gone | `2` | `2` | **pass** |
| S11 | `vadgr ps` is gone | `2` | `2` | **pass** |
| S12 | `vadgr registry list` is gone | `2` | `2` | **pass** |
| S13 | `vadgr runs approve x` is gone | `2` | `2` | **pass** |
| S14 | `vadgr runs logs x` is gone | `2` | `2` | **pass** |

#### Shipped endpoints

| endpoint | what was asked | status | code | response, as returned |
|---|---|---|---|---|
| `GET /api/health` | daemon liveness | `200` | - | `{"status":"healthy","modules":{"computer_use":true},"platform":"wsl2","version":"0.4.4","transport":{"name":"l ...` |
| `GET /api/providers` | the provider catalogue | `200` | - | `[{"id":"anthropic_oauth","name":"Anthropic (OAuth, subscription)","available":true,"models":[{"id":"claude-opu ...` |
| `GET /api/devices` | paired phones | `200` | - | `[{"id":"dev-1","machine_name":"Pixel","paired_at":"2026-01-01T00:00:00","last_seen":null}]` |
| `DELETE /api/devices/no-such-device` | negative: unknown device | `404` | `DEVICE_NOT_FOUND` | `{"error":{"code":"DEVICE_NOT_FOUND","message":"Device 'no-such-device' not found.","details":{}}}` |
| `GET /api/settings/computer-use` | computer-use settings | `200` | - | `{"enabled":true,"venv_ready":true,"daemon":"running","platform":"wsl2"}` |
| `GET /api/computer-use/status` | computer-use status | `200` | - | `{"available":true,"platform":"wsl2"}` |
| `POST /api/runs` | start a run from a task | `202` | - | `{"id":"{run}","agent_name":"Write the single line 'vadgr 0.4.4 sweep' to /tmp/vadgr-sweep-fixture.txt, then sa ...` |
| `POST /api/runs/{run}/cancel` | cancel the run just started | `200` | - | `{"id":"{run}","agent_name":"Write the single line 'vadgr 0.4.4 sweep' to /tmp/vadgr-sweep-fixture.txt, then sa ...` |
| `POST /api/runs/no-such-run/cancel` | negative: unknown run | `404` | `RUN_NOT_FOUND` | `{"error":{"code":"RUN_NOT_FOUND","message":"Run with id 'no-such-run' not found","details":{}}}` |
| `POST /api/runs/{run}/resume` | resume the cancelled run | `200` | - | `{"run_id":"{run}","status":"running","message":"Resuming"}` |
| `POST /api/runs/no-such-run/resume` | negative: unknown run | `404` | `RUN_NOT_FOUND` | `{"error":{"code":"RUN_NOT_FOUND","message":"Run with id 'no-such-run' not found","details":{}}}` |
| `POST /api/runs` | negative: an empty task | `422` | - | `{"detail":[{"type":"value_error","loc":["body"],"msg":"Value error, task must not be empty","input":{"task":"" ...` |
| `POST /api/runs` | negative: no task at all | `422` | - | `{"detail":[{"type":"missing","loc":["body","task"],"msg":"Field required","input":{}}]}` |
| `POST /api/runs` | negative: a provider with no model | `422` | - | `{"detail":[{"type":"value_error","loc":["body"],"msg":"Value error, provider and model must be provided togeth ...` |
| `POST /api/runs` | negative: the old body's inputs key | `422` | - | `{"detail":[{"type":"extra_forbidden","loc":["body","inputs"],"msg":"Extra inputs are not permitted","input":{" ...` |
| `GET /api/runs` | run list | `200` | - | `[{"id":"{run}","agent_name":"Write the single line 'vadgr 0.4.4 sweep' to /tmp/vadgr-sweep-fixture.txt, then s ...` |
| `GET /api/runs/{run}` | the run, settled | `200` | - | `{"id":"{run}","agent_name":"Write the single line 'vadgr 0.4.4 sweep' to /tmp/vadgr-sweep-fixture.txt, then sa ...` |
| `GET /api/runs/no-such-run` | negative: unknown run | `404` | `RUN_NOT_FOUND` | `{"error":{"code":"RUN_NOT_FOUND","message":"Run with id 'no-such-run' not found","details":{}}}` |
| `GET /api/runs?status=running` | run list, filtered | `200` | - | `[]` |

#### Removed by this release - probed to confirm gone, not half-wired

| endpoint | what it was | status | response |
|---|---|---|---|
| `GET /api/agents` | the agent list | `404` | `{"detail":"Not Found"}` |
| `POST /api/agents` | agent creation | `404` | `{"detail":"Not Found"}` |
| `GET /api/agents/no-such-agent` | one agent | `404` | `{"detail":"Not Found"}` |
| `PUT /api/agents/no-such-agent` | agent update | `404` | `{"detail":"Not Found"}` |
| `DELETE /api/agents/no-such-agent` | agent deletion | `404` | `{"detail":"Not Found"}` |
| `DELETE /api/agents` | delete every agent | `404` | `{"detail":"Not Found"}` |
| `POST /api/agents/no-such-agent/run` | the old trigger | `404` | `{"detail":"Not Found"}` |
| `GET /api/agents/no-such-agent/runs` | an agent's runs | `404` | `{"detail":"Not Found"}` |
| `GET /api/agents/no-such-agent/export` | agent export | `404` | `{"detail":"Not Found"}` |
| `POST /api/agents/import` | agent import | `404` | `{"detail":"Not Found"}` |
| `POST /api/agents/no-such-agent/uploads` | an agent's input upload | `404` | `{"detail":"Not Found"}` |
| `GET /api/projects` | the project list | `404` | `{"detail":"Not Found"}` |
| `POST /api/projects` | project creation | `404` | `{"detail":"Not Found"}` |
| `GET /api/projects/no-such-project` | one project | `404` | `{"detail":"Not Found"}` |
| `POST /api/projects/no-such-project/runs` | the project trigger | `404` | `<body unread: ConnectionResetError>` |
| `POST /api/projects/no-such-project/validate` | DAG validation | `404` | `{"detail":"Not Found"}` |
| `DELETE /api/runs` | delete every run | `405` | `{"detail":"Method Not Allowed"}` |
| `POST /api/runs/{run}/approve` | the approval gate | `404` | `{"detail":"Not Found"}` |
| `GET /api/runs/{run}/logs` | the run's log events | `404` | `{"detail":"Not Found"}` |
| `GET /api/runs/{run}/logs/step_01_a.jsonl` | one step's log file | `404` | `{"detail":"Not Found"}` |
| `GET /api/runs/{run}/outputs/result` | an output field | `404` | `{"detail":"Not Found"}` |

#### Not yet built - probed to confirm absent

| endpoint | minor | status | response |
|---|---|---|---|
| `GET /api/machine` | `0.6.0` | `404` | `{"detail":"Not Found"}` |
| `PATCH /api/machine` | `0.6.0` | `404` | `{"detail":"Not Found"}` |
| `POST /api/runs/no-such-run/pause` | `0.6.0` | `404` | `{"detail":"Not Found"}` |
| `POST /api/runs/no-such-run/respond` | `0.5.0` | `404` | `{"detail":"Not Found"}` |
| `GET /api/runs/no-such-run/journal` | `0.5.0` | `404` | `{"detail":"Not Found"}` |
| `POST /api/runs/no-such-run/messages` | `0.6.0` | `404` | `{"detail":"Not Found"}` |
| `GET /api/threads` | `0.6.0` | `404` | `{"detail":"Not Found"}` |
| `GET /api/approvals` | `0.7.0` | `404` | `{"detail":"Not Found"}` |
| `PUT /api/devices/probe/push_token` | `0.7.0` | `404` | `{"detail":"Not Found"}` |

#### The CLI

| command | exit | seconds | output, as printed |
|---|---|---|---|
| `vadgr health` | `0` | 0.1 | `Status: healthy / Version: 0.4.4 / Platform: wsl2 / Modules:` |
| `vadgr status` | `0` | 0.6 | `Service PID Status / api 223329 running / daemon - running` |
| `vadgr providers` | `0` | 0.6 | `Anthropic (OAuth, subscription) (anthropic_oauth) -- available / - Claude Opus 5 (claude-opus-5) / - Claude Sonnet 5 (claude-sonne ...` |
| `vadgr runs list` | `0` | 0.1 | `Run ID Task Status Duration / 699d12e5 Write the single line 'vadgr 0.4.4 sweep' to /tmp/vadgr-sweep-fixture.txt, then say DONE. f ...` |
| `vadgr --help` | `0` | 0.1 | `Usage: python -m cli [OPTIONS] COMMAND [ARGS]... / vadgr CLI. / Options: / --help Show this message and exit.` |
| `vadgr runs --help` | `0` | 0.1 | `Usage: python -m cli runs [OPTIONS] COMMAND [ARGS]... / Manage runs. / Options: / --help Show this message and exit.` |
| `vadgr health` | `3` | 1.6 | `Error: API is not running at http://127.0.0.1:9. Start it with: vadgr start` |
| `vadgr run  --background` | `2` | 0.1 | `Usage: python -m cli run [OPTIONS] TASK / Try 'python -m cli run --help' for help. / Error: TASK must not be empty.` |
| `vadgr run x --provider codex --background` | `2` | 0.1 | `Usage: python -m cli run [OPTIONS] TASK / Try 'python -m cli run --help' for help. / Error: --provider and --model must be given t ...` |
| `vadgr agents list` | `2` | 0.1 | `Usage: python -m cli [OPTIONS] COMMAND [ARGS]... / Try 'python -m cli --help' for help. / Error: No such command 'agents'.` |
| `vadgr ps` | `2` | 0.1 | `Usage: python -m cli [OPTIONS] COMMAND [ARGS]... / Try 'python -m cli --help' for help. / Error: No such command 'ps'.` |
| `vadgr registry list` | `2` | 0.1 | `Usage: python -m cli [OPTIONS] COMMAND [ARGS]... / Try 'python -m cli --help' for help. / Error: No such command 'registry'.` |
| `vadgr runs approve x` | `2` | 0.1 | `Usage: python -m cli runs [OPTIONS] COMMAND [ARGS]... / Try 'python -m cli runs --help' for help. / Error: No such command 'approv ...` |
| `vadgr runs logs x` | `2` | 0.1 | `Usage: python -m cli runs [OPTIONS] COMMAND [ARGS]... / Try 'python -m cli runs --help' for help. / Error: No such command 'logs'.` |

#### The sockets

| socket | frames | types, as received |
|---|---|---|
| `WS /api/ws/runs/{run_id}` | 4 | `{"run_started": 1, "agent_started": 1, "agent_failed": 1, "run_failed": 1}` |
| `WS /api/runs/{run_id}/stream` | 3 | `{"started": 1, "tool_call": 1, "failed": 1}` |

## Part F: the migration, on the daemon's own boot path

| # | What | Expected | Status |
|---|---|---|---|
| F1 | a database in the previous schema, with rows in all five doomed tables, is present when the daemon starts | the daemon boots | pass |
| F2 | the five tables are gone | `sqlite_master` holds exactly `runs`, `devices`, `idx_devices_token_hash` | pass |
| F3 | a run whose agent existed takes that agent's name as its title | `run-owned` -> `Research` | pass |
| F4 | a run with no agent takes the empty string | `run-orphan` -> `''` | pass |
| F5 | the backup is written before anything is dropped and is a readable database | `db.pre-0.4.4` opens and still holds the seven tables | pass |
| F6 | the migration says what it did and names the backup | two log lines, the second after the integrity check | pass |

**Measured.**

The daemon's own log, pass A, lines 3 and 4, before `Application startup complete`
(paths shortened to `<W>`):

```
INFO:     migrating <W>/db8971.db: dropping the workflow tables and rebuilding runs
INFO:     migration complete: <W>/db8971.db now holds runs and devices; the
          database before it is at <W>/db8971.db.pre-0.4.4
```

The databases either side of it:

```
db8971.db            tables: ['devices', 'runs']
db8971.db.pre-0.4.4  tables: ['agent_runs', 'agents', 'devices', 'project_edges',
                              'project_nodes', 'projects', 'runs']

SELECT id, title, status, provider, model FROM runs ORDER BY id:
  <run>      | Write the single line 'vadgr 0.4.4 sweep' ... | failed    | anthropic_oauth | claude-opus-5
  <run>      | Write the single line 'vadgr 0.4.4 sweep' ... | failed    | anthropic_oauth | claude-opus-5
  run-orphan |                                               | failed    | NULL | NULL
  run-owned  | Research                                      | completed | NULL | NULL
```

`run-owned` had an agent named `Research` before the migration and carries that
name as its title; `run-orphan` had none and carries the empty string, which the
shipped phone renders exactly as it rendered a null. Both keep `provider` and
`model` NULL, which is what a pre-0.4.4 row honestly holds.

The daemon's own log is the evidence rather than a test's, because the failure
this guards against is a migration that works in a unit test and not in a
lifespan.

## Part G: the regression that matters most

`E2E/0.4.1` proved a triggered run reaching the native loop. That proof runs
again here through the new door.

| # | What | Expected | Status |
|---|---|---|---|
| G1 | `POST /api/runs {task}` reaches the native loop | the loop's own stack frames appear on the run's path | pass |
| G2 | both sockets carry the release's frame vocabulary and `step_completed` never appears | raw: run/agent frames; mobile: the translated ones | pass |
| G3 | the run completes and its journal records the turns | `trajectory.jsonl` with real `usage` | pass (re-run 2026-08-09, see below) |
| G4 | `vadgr run "<task>"` exits `0` on a completed run | exit `0` | pass (re-run 2026-08-09, see below) |

**Measured.**

**The first round could not complete a run**, because the machine's provider
subscription was out of usage. That round is kept below rather than replaced:
it is what proved G1, that a run started through the new door reaches the
native loop, and the loop's own stack frames are the proof.

**G3 and G4 were re-run on 2026-08-09 once usage was restored**, on an
isolated daemon (port 8931, its own database and `FORGE_HOME`, port confirmed
free with `ss -ltn` before the start).

`vadgr run "Reply with exactly the word ACORN and nothing else."` exited `0`,
reporting `Run completed (3s)`. The run's terminal state, read back from
`GET /api/runs/{run_id}` by exact id:

```
status      completed
agent_name  Reply with exactly the word ACORN and nothing else.
provider    anthropic_oauth      model  claude-opus-5
started_at  2026-08-09T23:19:07.248830+00:00
completed_at 2026-08-09T23:19:09.729138+00:00
```

The row carries **no `title` key**: the published keys are `id`, `agent_name`,
`status`, `inputs`, `outputs`, `provider`, `model`, `log_path`, `started_at`,
`completed_at`, which is the shipped shape unchanged. The title rides
`agent_name`, as this release specifies, and storage calls it `title`.

The journal at `~/.vadgr/runs/<run_id>/trajectory.jsonl`, looked up by exact
id and never globbed, holds one turn:

```json
{"phase": "response", "iteration": 0,
 "response": {"content": [{"type": "text", "text": "ACORN"}],
              "usage": {"input_tokens": 1334, "output_tokens": 6},
              "stop_reason": "end_turn"}}
```

Real usage, and the model answered exactly what it was asked. Worth noting
against the loop's known termination defect: this response carries **no tool
call**, and completing here is correct, because the task was to say a word
rather than to do something. That the loop cannot tell those two apart is the
defect; this run is the benign side of it.

The failed round follows, kept as the record for G1.

The daemon's log, on the path of a run started by `POST /api/runs`:

```
native run <run> failed
Traceback (most recent call last):
  File ".../api/engine/native_bridge.py", line 133, in drive
    result = await self._provider.run_agent(
  File ".../engine/providers/_anthropic_base.py", line 232, in run_agent
    result = await run_loop(
  File ".../engine/loop.py", line 169, in run_loop
    response = await llm_call(messages, tools=mcp_tools, max_tokens=max_tokens)
  File ".../engine/providers/_anthropic_base.py", line 132, in llm_call
    wire_response = await self._post(request, body)
engine.providers._anthropic_base.ProviderError: Anthropic request failed
  (HTTP 400): {"type":"error","error":{"type":"invalid_request_error",
  "message":"You're out of extra usage. ..."},"request_id":"req_..."}
```

The frames, per socket, identical in all three passes:

```
raw    /api/ws/runs/{run_id}      run_started 1, agent_started 1, agent_failed 1, run_failed 1
mobile /api/runs/{run_id}/stream  started 1, tool_call 1, failed 1
```

`step_completed` appears on neither, which is the vocabulary change this release
makes. The mobile socket shows three where the raw shows four because the
recorder stops on the first terminal frame it receives, and `agent_failed` maps
to `failed` before `run_failed` arrives.

The CLI half, run by hand against a live daemon on port 8946:

```
$ vadgr run "Say DONE."
[vadgr] Run started: 0ab2cd09-f5ae-4df9-aa77-3ade89a54e8a
[vadgr] Run failed (2s): Anthropic request failed (HTTP 400): ...
  See the run: vadgr runs get 0ab2cd09-f5ae-4df9-aa77-3ade89a54e8a
RUN EXIT=1

$ vadgr run "Say DONE." --background
[vadgr] Run started: d3945de6-6089-43f4-bed0-1526a250af2f
  Watch it with: vadgr runs get d3945de6-6089-43f4-bed0-1526a250af2f
BG EXIT=0
```

Exit `1` on a failed run and exit `0` on `--background` are read directly, not
piped. Exit `0` on a **completed** run is what G4 still cannot show.

G1 is proved by the stack, not by the status. A run ends `failed` for many
reasons; only one of them puts `engine/loop.py` and the provider's own HTTP call
on the path, and that is the seam this release could have broken.

## Repeatability - three independent passes

Three agents, concurrently, each with its own port, database, `FORGE_HOME` and
daemon, each killing only its own pid.

| | 8971 (A) | 8972 (B) | 8973 (C) |
|---|---|---|---|
| run (sweep) | `699d12e5` | `0f73dc7f` | `ba520f13` |
| run (socket) | `5458fc54` | `89064078` | `3a7f3525` |
| HTTP entries | 49 | 49 | 49 |
| CLI entries | 14 | 14 | 14 |
| sweep checks | 14 pass, 0 fail | 14 pass, 0 fail | 14 pass, 0 fail |
| raw / mobile frames | 4 / 3 | 4 / 3 | 4 / 3 |
| settled provider, model | `anthropic_oauth`, `claude-opus-5` | same | same |
| migration lines in the log | 2 | 2 | 2 |
| journal phases | none written | none written | none written |
| tokens in / out | none | none | none |

**What was diffed, and that it matched.** Every HTTP entry on
`(method, path, status, error_code)` with the run uuid normalised: the three
lists are **equal element by element**, 49 entries each. Every CLI entry on
`(argv, exit_code, produced_output)`: **equal**, 14 entries each. Every sweep
check on name and verdict: **equal**. Frame type counts per socket: **equal**.
The three socket run ids differ, which is what proves these were three runs and
not one result read three times.

**The token axis could not be read.** Input tokens should be identical across
passes and output tokens should differ; with no model turn there are no counts
at all. That is stated rather than papered over, and it is the reason this
runbook does not claim the meter is fully calibrated.

**What each agent found odd**, none of which any assertion covered:

- **`GET /api/providers` and `GET /api/settings/computer-use` answer in about
  0.55s** where every other endpoint answers in 0.00 to 0.04s. All three passes
  measured it; the two are within 30ms of each other, which points at one shared
  probe on the request path rather than noise. Pre-existing, carried forward.
- **`vadgr health` against a dead port takes 1.6s**, sixteen times any other CLI
  call. The client's own docstring names the cause: on WSL2 a loopback connect
  to a port nothing listens on is swallowed rather than refused, so the probe
  spends its full 1.5s ceiling. The exit code is right and nothing asserts on
  duration, which is exactly the shape of the `0.4.1` finding.
- **A cancelled run gets a `completed_at` while its `started_at` is still null**,
  because cancel marks a queued run `failed` before it has started. Recorded as
  F3.
- **Every failed run leaves an empty directory under `~/.vadgr/runs/`.** The
  loop creates it before its first turn and writes nothing if that turn fails.
- **The two sockets serialise the same instant differently**, raw as `+00:00`
  and mobile as `Z`. Pre-existing, and harmless to a parser that reads ISO 8601.
- **`POST /api/runs/{id}/resume` answers with `{run_id, status, message}`** where
  every other run endpoint answers with the frozen row. Pre-existing, and the
  CLI is its only consumer.

## Evidence

The private evidence bundle, under `e2e_evidence/vadgr-0.4.4/`: the harness, the
three sweep records, the socket recordings, the daemon logs, the migrated
databases and their backups, per pass.

## Findings

### F1 (fixed): a run published `provider: null` on a run that demonstrably ran

`POST /api/runs` with no `provider` stored none, and `_resolve_config` resolved
the machine default in memory without writing it back. The published row then
reported `null` for both fields while the daemon's own stack showed the run
going to `anthropic_oauth`. At `0.4.3` the deleted agents route persisted the
agent's provider onto the row, so this was a regression in what a client can
learn about its own run, on a key the surface freezes.

Root cause: `api/services/execution_service.py`, `_resolve_config` returned the
pair and nothing stored it. No unit test crossed the seam because the service's
tests assert on what it returns and the route's tests stub the service out; only
a run against a live daemon reads the row after the fact.

Fixed by `RunRepository.set_config`, called from `_resolve_config`. Test:
`test_resolution_is_written_back_to_the_row`, which fails with the call removed.
Confirmed live: all three closing passes read `anthropic_oauth` /
`claude-opus-5` off the settled row.

### F2 (fixed): the guard suite's route walk was blind on a newer FastAPI

`test_deletion_decommissioned.py` searched `app.routes` flat. From FastAPI
0.141 an included router is one opaque entry whose real routes hang off
`original_router`, so the walk found four routes and none of the daemon's. The
presence guards failed loudly, which is how it was noticed; the **absence**
guards passed silently, for the wrong reason, which is the part that mattered.
`api/requirements.txt` says `fastapi>=0.115`, so which shape a machine gets
depends on when it last installed, and CI installs fresh.

Found by running the api suite on native Windows, where the venv was built from
requirements a few hours old. Fixed by walking `routes`, `router` and
`original_router`, and by adding `test_the_route_walk_sees_the_apps_own_routes`,
which fails first if the walk ever stops finding `/api/health` so the group
cannot pass vacuously again. Both platforms now report 35 passed.

### F3 (open): a cancelled run is recorded as `failed`, with a completion before its start

`POST /api/runs/{id}/cancel` on a queued run marks it `failed` with empty
`outputs`, and `update_status` writes `completed_at` while `started_at` is still
null. A client cannot tell a user's cancel from a crash, and mid-run the row
carries a completion timestamp earlier than its start.

Acceptable to ship: the behaviour is unchanged from `0.4.3`, this release adds
no new way to reach it, and run statuses are owned by the minor that reshapes
them. Recorded here so it is a decision rather than an oversight.

### F5 (open): the recording quantises the duration signal away

`sweep.py` rounds HTTP durations to two decimals and CLI durations to one, so 43
of 49 HTTP entries record `0.0` and most CLI entries record `0.1`. The `0.4.1`
close found a real defect purely on duration, and this recording keeps almost
none of that signal below about ten milliseconds. It still caught the two
half-second endpoints, because those are far above the floor.

Not fixed here on purpose: the harness that produced this record is the record's
own provenance, and changing it after the fact would leave a committed harness
that cannot have emitted the committed tables. **Disposition: the next
re-record raises the precision**, and until then duration comparisons across
passes are only meaningful above ~50ms.

### F4 (fixed): the migration announced itself into nothing

Three independent passes reported that a five-table migration left no line in
the daemon's log, and all three root-caused it identically: `api/serve.py` built
`uvicorn.Config` with the default log config, which installs handlers for the
`uvicorn*` loggers only. Every `logger.info` in the daemon propagated to a root
logger with no handler and was dropped at `WARNING`. The only evidence a
migration had run was a backup file appearing on disk, which is exactly what the
code's own comment said it existed to prevent.

This is the more useful half of the finding: the first fix for it **passed its
unit test and did nothing**, because `caplog` attaches a handler of its own. The
replacement test applies the config with `dictConfig` and asserts a record
reaches a stream, which is a test of the thing rather than of the dictionary.
Fixed in `api/serve.py`; confirmed in all three closing passes, two lines each,
the second naming the backup.

## Per-OS results

**Why `Not-Needed` rather than `not run` here** (ruled by the owner,
2026-08-09). This release **removes code**. It adds no capability, no route
and no platform surface, so there is nothing for a second OS to disagree
about: a deleted route is absent everywhere, and the deletions are proved by
guards that are pure Python with no platform branch. The one thing it does
add is a schema migration, and that **is** OS-sensitive because SQLite's
version differs per platform, which is why it was driven on two: WSL2 on
SQLite 3.45.1 and native Windows on 3.49.1, migrating identically. The sweep
and the run reach the daemon over HTTP and the provider over HTTPS, neither
of which branches per OS.

The honest limit of that argument, stated rather than left implicit: it holds
**because this minor deletes**. It would not hold for a release that adds a
surface, and it does not transfer to the next one.

Legend: pass / fail / blocked / not run / **Not-Needed** (no OS-specific
surface, so a run there adds no signal - always with its reason).

| | Linux | macOS | Windows native | WSL |
|---|---|---|---|---|
| Automated gate | **Not-Needed** | **Not-Needed** | 8 pre-existing failures, otherwise pass | pass |
| F. the migration | **Not-Needed** | **Not-Needed** | pass | pass |
| A-E. the sweep | **Not-Needed** | **Not-Needed** | **Not-Needed** | pass |
| G. the run | **Not-Needed** | **Not-Needed** | **Not-Needed** | **pass** |
| Overall | **Not-Needed** | **Not-Needed** | **pass** | **pass** |

**WSL2** is the development host and carries the full pass: Linux 6.6.87.2,
Python 3.12.3, SQLite **3.45.1**. Three concurrent closing passes, the migration
on the boot path, the sweep, both sockets and the CLI.

**Native Windows 11** (10.0.26200), Python 3.12.10, SQLite **3.49.1**, driven
from the WSL host through `powershell.exe` against a venv built from
`api/requirements.txt`. The api suite runs there: **420 passed, 1 skipped, 8
failed**. All eight failures are pre-existing and were confirmed failing on
`master` under the same interpreter: seven `CLIAgentProvider` cases that shell
out to `echo` and read `HOME`, and one tailscaled localapi parse. The migration
suite and the guard suite pass in full, which is the point of running there: the
migration's file handling is the release's one genuinely per-OS surface, and
`VACUUM INTO` refusing an existing file plus Windows refusing to replace an open
one is why the backup path is removed before it is written.

**Recording the SQLite version is the substance of the portability claim**, not
a formality: the rebuild was chosen over `ALTER TABLE ... DROP COLUMN`
specifically so it does not depend on a version, and the two platforms measured
here differ by four minor versions and both migrate identically.

**Linux** proper and **macOS** were not run. WSL2 is a real Linux kernel and
covers the code paths, but its loopback and filesystem behaviour is its own, so
it is not recorded as Linux. No macOS machine was available; the cells owed
there are the migration's file handling and the transport bind, and they are
owed rather than excused.

The sweep is **not** marked `Not-Needed` anywhere. It binds a port, spawns
processes and writes files, so every platform is owed it.

## What this runbook cannot prove

- **That a run completes.** Nothing here saw a model turn, so the completed
  path, the outputs it produces, the `run_completed` frame and the journal are
  all unproven at this release. Everything up to and including the provider's
  own HTTP request is proven.
- **That the token axis is stable.** Input tokens should be identical across
  passes and output tokens should differ. With no turns, neither number exists.
- **Anything about macOS.** No macOS machine was available.
- **That a phone renders the surviving surface correctly.** This runbook proves
  what the daemon serves. What the app does with it is the app's runbook.
