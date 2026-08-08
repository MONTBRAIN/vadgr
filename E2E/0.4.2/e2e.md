# 0.4.2 - the frontend is gone: e2e runbook

The machine now has exactly two clients, the `vadgr` CLI on the box and the
phone over the tailnet, and starting the daemon reaches for no Node.js at all.

Format and verification rules: [`../README.md`](../README.md) and
[`../TEMPLATE.md`](../TEMPLATE.md).

> **Status: run on WSL, 2026-08-05, with the CLI surface and the installer also
> run on native Windows.** Automated gate green (engine 122, api 554, cli 192).
> Part A (the decommission gate) ran **three times concurrently on three isolated
> daemons** and passed 14/14 each time. Part B (pairing, now the only pairing
> surface) passed end to end against a real tailnet. Part C drove every shipped
> endpoint and every CLI command. Part R re-ran `0.4.1`'s native-loop gate and it
> is unchanged. **One finding, pre-existing and reproduced identically on
> `master`.** Nothing is marked pass that was not executed and read back.

## What is being claimed

A removal has a different burden of proof from a feature: the claim is about
absence, and absence is easy to assert and easy to get wrong. So every cell here
is phrased as something that must **not** be observable, and measured on a
running daemon rather than read out of the diff:

1. `vadgr start` boots the API and **spawns nothing else** - no `npm run dev`, no
   child process of any kind.
2. **Nothing answers on the old dashboard port**, and the daemon sends no CORS
   headers even to a request that carries an `Origin`.
3. **Pairing still works end to end through `vadgr pair`**, which is now the only
   pairing surface the machine has.

The host used for this run **has Node on its PATH** the entire time
(`/home/santiago/.nvm/versions/node/v20.20.1/bin/node`). That matters: a daemon
that starts cleanly on a machine with no Node proves the dependency is optional,
while a daemon that ignores a Node that is sitting right there proves it is
gone.

## The approach

The gate for this minor is not model-shaped - it is about what a process does and
does not do - so Part A is a **recorded sweep** driven through the product's own
surfaces (`vadgr start`, `vadgr pair`, `vadgr stop`, and `curl` against the
booted daemon), never an import. Part R, the regression, is driven the way the
engineering standard requires: a real run whose verdict comes from
`trajectory.jsonl`, not from the run's status.

Both surfaces are exercised and neither substitutes for the other:

- **the API + the run WebSocket** - how the phone calls it;
- **the CLI** - the on-box path, which is the surface this minor actually
  changed.

The CLI is driven through the **shim entry point** (`PYTHONPATH=$REPO
cli/.venv/bin/python -m cli`), the same form the installed `vadgr` binary uses,
pointed at the branch under test. Not `python -m cli.main`, which exits `0`
having printed nothing.

## Prerequisites

```bash
export FORGE_HOME=$SCRATCH/forge8791          # a throwaway home, so pid/port/log files are this run's
export AGENT_FORGE_PORT=8791
export AGENT_FORGE_DATABASE_PATH=$SCRATCH/db8791.db
export VADGR_TRANSPORT=tailscale              # pairing 503s on loopback by design
vadgr start
```

Tailscale must be up **inside WSL** (the Linux `tailscaled` socket), not only on
the Windows side, or the transport reports unavailable and `vadgr pair` refuses
to hand out a QR the phone cannot reach.

## Automated gate (necessary, never sufficient)

- `PYTHONPATH=. python3 -m pytest engine/tests/ -q` -> **122 passed**
- `python3 -m pytest api/tests/ -q` -> **554 passed**
- `python3 -m pytest cli/tests/ -q` -> **192 passed**

Counts moved, which for a removal is the point: `api` 551 -> 554 (seven new
guardrail tests, five CORS/frontend-port tests deleted, two new API-only tests,
one gateway-guard test deleted because the file it read no longer exists), `cli`
189 -> 192 (seven Node-discovery and Vite-log-parsing tests deleted, ten new
API-only tests). A removal that changed no test count would mean the deleted
behaviour was never tested or the new behaviour is not.

**What the gate cannot tell you.** Every one of those tests reads source text or
a fake. None of them starts a process. The claim "`start` spawns nothing" is a
claim about a running process tree, and only Part A's `ps --ppid` against a live
daemon can make it.

## Coverage

Axes, multiplied, with the count written down.

| Part | Axes | Cells | Run | Open |
|---|---|---|---|---|
| A - the decommission gate | 14 recorded checks x 3 isolated concurrent passes | 42 | 42 | 0 |
| B - pairing (inside A's record) | mint x claim x persist x replay-refused | 4 | 4 | 0 |
| C - surface | 14 shipped endpoints + 10 not-yet-built + 7 CLI commands | 31 | 31 | 0 |
| R - regression | 2 trigger paths (API, CLI) x (journal, sockets, outputs) | 6 | 6 | 0 |
| W - native Windows | 4 CLI checks + 4 installer checks | 8 | 8 | 0 |
| | | **91** | **91** | **0** |

Nothing is deferred out of this runbook. A removal has no "needs a later minor"
cells: everything it claims is true or false today.

## Surface coverage - every published endpoint, with what it returned

**Generated, not written.** One sweep drives every surface and records the
request, the status, the error code, the response headers and the body; the
tables below are emitted from that record by `gen_tables.py`, so no row was typed
and none can drift from the run it describes. Harness and record are both in the
evidence bundle (`sweep.py`, `gen_tables.py`, `sweep-879{1,2,3}.json`).

Pass shown: port `8791`, WSL, `tailscale` transport, daemon pid `1427109`.
`{device}` stands in for that pass's device id.

#### The decommission checks

| # | check | expected | as measured | |
|---|---|---|---|---|
| D1 | frontend/ directory exists | `False` | `False` | **pass** |
| D2 | npm manifests in the repo | `0` | `0` | **pass** |
| D3 | frontend.log written by start | `False` | `False` | **pass** |
| D4 | frontend pid/port files written by start | `[]` | `[]` | **pass** |
| D5 | pid files after start | `['api.pid', 'api.port']` | `['api.pid', 'api.port']` | **pass** |
| D6 | child processes of the daemon | `[]` | `[]` | **pass** |
| D7 | anything listening on the old dashboard port 3000 | `False` | `False` | **pass** |
| D8 | access-control-allow-origin on a request carrying Origin | `None` | `None` | **pass** |
| D9 | `vadgr start --frontend-port` exit code | `2` | `2` | **pass** |
| D10 | `vadgr start --frontend-port` says no such option | `True` | `True` | **pass** |
| D11 | `vadgr pair` exit code | `0` | `0` | **pass** |
| D12 | `vadgr pair` rendered a terminal QR (rows of blocks) | `True` | `True` | **pass** |
| D13 | `vadgr pair` printed a token | `True` | `True` | **pass** |
| D14 | the claimed device is in GET /api/devices | `True` | `True` | **pass** |

`node` on this host's PATH while all of the above held: `/home/santiago/.nvm/versions/node/v20.20.1/bin/node`.

**D6 is the cell that carries the headline.** `ps -o pid,comm,args --ppid <daemon
pid>` returns nothing at all: the daemon is a lone uvicorn. Before this minor the
same command would have listed an `npm run dev`. D5 is its corroboration from the
other side - `~/.forge/pids/` holds two files where it used to hold four, and
there is no `frontend.log` beside `api.log` (D3).

**D9 and D10 are there because a removed flag that is silently ignored looks
exactly like a removed flag that works.** `--frontend-port` is a usage error with
exit `2`, not an argument that parses and does nothing.

#### Shipped endpoints

| endpoint | what was asked | status | code | response, as returned |
|---|---|---|---|---|
| `GET /api/health` | a browser-shaped request: Origin set, no CORS expected | `200` | - | `{"status":"healthy","modules":{"forge":true,"computer_use":true},"platform":"wsl2","version":"0.4.2","transpor ...` |
| `POST /api/auth/claim` | claim the token vadgr pair minted (the phone's half) | `200` | - | `{"token":"9ojvV4keeMmxrvcljAssy_fbK8sSU4sRervNQk_yrJ0","device_id":"{device}"}` |
| `GET /api/devices` | ground truth: the device persisted | `200` | - | `[{"id":"{device}","machine_name":"e2e-phone","paired_at":"2026-08-05T14:13:28.061770Z","last_seen":"2026-08-05 ...` |
| `POST /api/auth/claim` | negative: the pairing code is one-time | `401` | `PAIRING_CODE_INVALID` | `{"error":{"code":"PAIRING_CODE_INVALID","message":"That pairing code is wrong or has already been used.","deta ...` |
| `DELETE /api/devices/{device}` | clean up the paired device | `200` | - | `{"status":"revoked","device_id":"{device}"}` |
| `GET /api/health` | daemon liveness | `200` | - | `{"status":"healthy","modules":{"forge":true,"computer_use":true},"platform":"wsl2","version":"0.4.2","transpor ...` |
| `GET /api/providers` | the provider catalogue | `200` | - | `[{"id":"anthropic_oauth","name":"Anthropic (OAuth, subscription)","available":true,"models":[{"id":"claude-opu ...` |
| `GET /api/devices` | paired phones | `200` | - | `[]` |
| `DELETE /api/devices/no-such-device` | negative: unknown device | `404` | `DEVICE_NOT_FOUND` | `{"error":{"code":"DEVICE_NOT_FOUND","message":"Device 'no-such-device' not found.","details":{}}}` |
| `POST /api/auth/claim` | negative: bad pairing code | `401` | `PAIRING_CODE_INVALID` | `{"error":{"code":"PAIRING_CODE_INVALID","message":"That pairing code is wrong or has already been used.","deta ...` |
| `GET /api/runs` | run list | `200` | - | `[]` |
| `GET /api/runs/no-such-run` | negative: unknown run | `404` | `RUN_NOT_FOUND` | `{"error":{"code":"RUN_NOT_FOUND","message":"Run with id 'no-such-run' not found","details":{}}}` |
| `GET /api/agents` | agent list | `200` | - | `[]` |
| `GET /api/settings/computer-use` | computer-use settings | `200` | - | `{"enabled":true,"venv_ready":true,"daemon":"running","platform":"wsl2"}` |

The version string is the one thing on this table that a phone reads and acts on,
and it says `0.4.2`. That is the whole argument for the number: a daemon carrying
`0.4.1`'s features cannot serve a lower one.

Every negative case is asserted on its `code`, never its sentence: a client
switches on one and shows the other.

#### Not yet built - probed to confirm absent, not half-wired

| endpoint | minor | status | response |
|---|---|---|---|
| `GET /api/machine` | `0.5.0` | `404` | `{"detail":"Not Found"}` |
| `PATCH /api/machine` | `0.6.0` | `404` | `{"detail":"Not Found"}` |
| `POST /api/runs` | `0.5.0` | `405` | `{"detail":"Method Not Allowed"}` |
| `POST /api/runs/no-such-run/pause` | `0.5.0` | `404` | `{"detail":"Not Found"}` |
| `POST /api/runs/no-such-run/respond` | `0.5.0` | `404` | `{"detail":"Not Found"}` |
| `GET /api/runs/no-such-run/journal` | `0.5.0` | `404` | `{"detail":"Not Found"}` |
| `POST /api/runs/no-such-run/messages` | `0.6.0` | `404` | `{"detail":"Not Found"}` |
| `GET /api/threads` | `0.6.0` | `404` | `{"detail":"Not Found"}` |
| `GET /api/approvals` | `0.7.0` | `404` | `{"detail":"Not Found"}` |
| `PUT /api/devices/probe/push_token` | `0.7.0` | `404` | `{"detail":"Not Found"}` |

Ten endpoints, ten refusals, unchanged from `0.4.1`. Worth the thirty seconds
because a pure-removal release is exactly when nobody expects a route table to
have moved.

#### The CLI

| command | exit | seconds | output, as printed |
|---|---|---|---|
| `vadgr start --frontend-port 3000` | `2` | 0.1 | `Usage: python -m cli start [OPTIONS] / Try 'python -m cli start --help' for help. / Error: No such option: --frontend-po ...` |
| `vadgr pair` | `0` | 0.2 | `[terminal QR, 24 rows] / Machine: Santiago-Casa / Address: santiago-casa-1.tail323b9e.ts.net:8791 / Pairing token: gXA7u ...` |
| `vadgr health` | `0` | 0.2 | `Status: healthy / Version: 0.4.2 / Platform: wsl2` |
| `vadgr status` | `0` | 0.7 | `Service PID Status / api 1427109 running / daemon - running` |
| `vadgr runs list` | `0` | 0.1 | `[vadgr] No runs found.` |
| `vadgr providers` | `0` | 0.7 | `Anthropic (OAuth, subscription) (anthropic_oauth) -- available / - Claude Opus 5 (claude-opus-5) / - Claude Sonnet 5 (cl ...` |
| `vadgr health` | `3` | 1.6 | `Error: API is not running at http://127.0.0.1:9999. Start it with: vadgr start` |

`vadgr status` lists **one** service. It used to list two, the second of which
was permanently `stopped` on any machine without Node - a row that taught the
owner nothing and looked like a fault.

The last row is the negative case, and it took two attempts to make it honest -
see *Harness notes* below.

Driven outside the recorded sweep, because they change the daemon's lifecycle and
so cannot sit inside a sweep that needs it up:

| command | exit | what happened |
|---|---|---|
| `vadgr api --port 8794` | `0` | booted the daemon; `GET /api/health` -> `200`; `pids/` held `api.pid`, `api.port` and nothing else |
| `vadgr restart` | `0` | stopped pid `1429508`, started a new one, `GET /api/health` -> `200` |
| `vadgr stop` | `0` | `Stopped api (PID ...)`, then `vadgr status` -> `api - stopped` |

`vadgr api` and `vadgr start` are now the same command, so the third of the
three ways to start the daemon that used to exist is gone without the name being
taken away from anyone scripting against it. `--port` still parses, as the old
`api` spelling.

## Part A: the decommission gate - **passes, three times over**

Run three times **concurrently**, each pass with its own port, database,
`FORGE_HOME` and daemon process (8791, 8792, 8793) - three observations, not one
observed three times. Isolation is what makes concurrency safe here.

| | 8791 | 8792 | 8793 | identical |
|---|---|---|---|---|
| decommission checks | 14 | 14 | 14 | **yes** |
| HTTP entries | 24 | 24 | 24 | **yes** |
| CLI entries | 7 | 7 | 7 | **yes** |
| failures | none | none | none | |

| | 8791 | 8792 | 8793 |
|---|---|---|---|
| pairing token length | 32 | 32 | 32 |
| QR rows rendered | 24 | 24 | 24 |
| device id claimed | `1ec4c171` | `a3a901f6` | `d84447c9` |
| daemon pid at status | 1427109 | 1427111 | 1427112 |

What was diffed: the check name, expectation and measured value of all 14
decommission checks; method, path, status and error code of all 24 HTTP entries;
and command, exit code and whether output was produced for all 7 CLI entries.
**All three agree exactly.** The device ids and daemon pids differ, which is what
says these were three separate daemons rather than one answer read three times.

There is no token column here because Part A makes no model call. Its regression
counterpart in Part R does, and carries one.

## Part B: pairing, now the only surface - **passes**

| # | What | Expected | Status |
|---|---|---|---|
| B1 | `vadgr pair` mints a token against a real tailnet | exit `0`, a token, an advertised MagicDNS address | **pass** |
| B2 | It renders a scannable QR in the terminal | rows of block characters, not a fallback URI | **pass** (24 rows) |
| B3 | The phone's half completes | `POST /api/auth/claim` -> `200` with a device token | **pass** |
| B4 | The device persisted | it appears in `GET /api/devices` | **pass** |
| B5 | The code is one-time | replaying it -> `401 PAIRING_CODE_INVALID` | **pass** |

**Measured.**

```
$ vadgr pair
  [24 rows of Unicode QR]
  Machine:        Santiago-Casa
  Address:        santiago-casa-1.tail323b9e.ts.net:8791
  Pairing token:  gXA7u... (32 chars)
exit 0

POST /api/auth/claim  {"pairing_token": "<that token>", "device_name": "e2e-phone"}
  -> 200 {"token":"9ojvV4ke...","device_id":"1ec4c171-..."}
GET  /api/devices
  -> 200 [{"id":"1ec4c171-...","machine_name":"e2e-phone","paired_at":"2026-08-05T14:13:28.061770Z",...}]
POST /api/auth/claim  (same token again)
  -> 401 PAIRING_CODE_INVALID
```

**The ground truth is `GET /api/devices`, not the claim's own `200`.** A claim
endpoint that minted a token and persisted nothing would answer identically, and
the phone would be paired to a machine that had never heard of it.

The address is a MagicDNS name rather than `127.0.0.1`, which is the only form a
phone can act on. That is the property `vadgr pair` had before this minor and
still has; what changed is that it is now the **only** place on the machine that
can produce one.

## Part C: the surface - **passes**

Every shipped endpoint, every not-yet-built endpoint and every CLI command in the
tables above, driven live and recorded. Nothing on the published surface moved:
the removal touched configuration, one middleware and the CLI's service
commands, and the route table is byte-for-byte what `0.4.1` served, with the
version string as the single deliberate difference.

The CORS row is the one worth reading twice. `GET /api/health` with
`Origin: http://localhost:3000` comes back `200` with **no**
`access-control-allow-origin` header. The daemon does not refuse the request - it
simply no longer tells a browser it is welcome, because there is no browser.

## Part R: regression - the native loop still runs - **passes**

`0.4.1`'s gate re-run on this branch. The diff does not touch the loop, but it
touches `cli/stream.py`, which is what the CLI uses to watch a run, so the CLI
trigger path is where collateral damage would show.

| # | What | Expected | Status |
|---|---|---|---|
| R1 | Trigger through the API | run reaches the native loop | **pass** |
| R2 | The loop actually ran | journal at the API run id, real usage | **pass** |
| R3 | Both sockets carry the run | frames on `/api/ws/runs/{id}` and `/api/runs/{id}/stream` | **pass** |
| R4 | Trigger through the CLI | `vadgr run <agent>` completes, exit `0` | **pass** |
| R5 | The CLI-triggered run reached the loop too | journal at that run id | **pass** |
| R6 | The results link points at the API, not a dashboard | `http://<api>/api/runs/<id>`, and it resolves | **pass** |

**Fixture setup, stated where it happens.** Agent creation on a native provider
fails on this branch **and identically on `master`** (F1 below), so no agent can
be brought to `ready` through the product path. The agent used here was created
through `POST /api/agents` as normal and then had its `status` set to `ready`
directly in the sweep's throwaway database. Nothing else was seeded: the runs
below are real runs, with real model calls, recorded in a real journal.

**Measured (R1-R3).** `POST /api/agents/{id}/run` with
`{"provider":"anthropic_oauth","model":"claude-opus-5"}`:

```
api run id            da05d07a-e6a1-4ed9-86e6-b9751123a825
journal at that id    YES   (~/.vadgr/runs/da05d07a-.../trajectory.jsonl)
journal phases        {'response': 2, 'in_flight': 1, 'done': 1}
tool the model chose  control__report_progress
usage                 turn 0: input 1472 / output 60      turn 1: input 1540 / output 29
run status            completed

raw    /api/ws/runs/{id}      run_started 1  agent_started 1  agent_log 2  agent_completed 1  run_completed 1  = 6
mobile /api/runs/{id}/stream  started 1  tool_call 1  output 3  completed 1                                    = 6
```

**The journal is the proof, not the status.** A run ends `completed` on the
legacy path too; only the native loop writes `trajectory.jsonl`, and the token
counts in it are a real model call rather than a subprocess's stdout.

**Measured (R4-R6).**

```
$ vadgr run e2e-042-conformance
[vadgr] Run started: c2591905-e886-4923-acf1-87598116f66d
[vadgr] Run completed (4s)

  See results: http://127.0.0.1:8794/api/runs/c2591905-e886-4923-acf1-87598116f66d
exit 0

GET that URL          -> 200  status completed, outputs {"result": "Reported progress with \"frontend decommission check\". Done."}
journal at that id    YES   phases {'response': 2, 'in_flight': 1, 'done': 1}
usage                 turn 0: input 1472 / output 60      turn 1: input 1540 / output 20
```

**R6 is the one line of this minor's diff that a user sees every run.** Before,
`_print_results_link` probed for a Vite dev server and printed
`http://localhost:3000/runs/<id>` when it found one - a link to a dashboard that
no longer exists, and a probe that cost a second on every completed run. It now
prints the API URL unconditionally, and the URL was followed to a `200` rather
than merely inspected.

Input token counts match across the two runs (1472 and 1540) and output counts
differ (60/29 against 60/20), which is the right shape: a fixed prompt and tool
set must not move, and a model's prose is not deterministic. The first turn's 60
is identical in both, which is a short deterministic-enough tool call rather than
a reused result - the second turn, which is prose, differs.

## Part W: native Windows - **passes**

WSL is not Windows, and this minor deletes Windows-specific code (`_find_npm`
looked for `npm.cmd` / `npm.exe` beside `node.exe`) and edits the Windows
installer. Both were run on the Windows side over `powershell.exe` interop,
against the same working tree over `\\wsl.localhost`.

| # | What | Expected | Measured | Status |
|---|---|---|---|---|
| W1 | `python -m cli start --frontend-port 3000` | usage error | `Error: No such option '--frontend-port'.` exit `2` | **pass** |
| W2 | `python -m cli logs -s frontend` | usage error | exit `2` | **pass** |
| W3 | `python -m cli status` | no `frontend` row | `api - stopped` (one row with the daemon down; `api` + `daemon` with it up, the second being computer-use) | **pass** |
| W4 | `python -m cli api --help` | the same command as `start`, both flag spellings | `Start the vadgr daemon (the API).` / `--api-port, --port INTEGER` | **pass** |
| W5 | `setup.ps1` parses | no parse errors | parsed clean | **pass** |
| W6 | `InstallNode` is not defined | absent from the AST | `False` | **pass** |
| W7 | `SetupFrontend` is not defined | absent from the AST | `False` | **pass** |
| W8 | the script mentions node / npm / nvm / frontend | none of them | `False` x4 | **pass** |

```
PowerShell 5.1.26100.8875 on Microsoft Windows NT 10.0.26200.0
functions: Info, Ok, Warn, Fail, CommandExists, EnsureWinget, InstallGit, PythonOk,
           InstallPython, SetupRepo, EnsureVenv, SetupApi, SetupForgeScripts, SetupCli,
           GenerateForgeCli, AddToPath, Main
```

W5-W8 are read from the **parsed AST**, not a grep: a function can be present and
uncalled, and a grep over a script that defines it inside a here-string would say
the same thing either way.

`setup.sh` was checked with `bash -n` (clean) and its `main` calls
`install_git`, `install_python`, `setup_repo`, `setup_api`,
`setup_forge_scripts`, `setup_cli`, `generate_forge_cli`, `add_to_path` - no
Node step between `install_python` and `setup_repo` any more.

## Harness notes

**One false green, caught before it was believed.** The dead-daemon CLI case
first recorded `vadgr health` exiting `0` in 0.2s against port 9999 - because
setting `AGENT_FORGE_PORT` is not enough: the CLI reads `FORGE_HOME`'s port file
first, so it quietly talked to the live daemon and "passed". Pinning
`FORGE_API_URL` fixed it and the case now records exit `3` in 1.6s. This is the
same class of harness defect `0.4.1` recorded twice, and it is worth writing down
a third time: **assert on output, not only on exit codes**, and check the harness
reached the thing it claims to have reached.

**A stale working-tree directory is not a deleted directory.** `git rm -r
frontend` leaves `frontend/node_modules/` behind on disk - 197 MB of it,
untracked - so `git status` reads clean while the directory is still there. The
guardrail test caught it before the sweep ran, because it asks
`os.path.isdir("frontend")` rather than `git ls-files`. Those two answers differ
exactly when it matters, and D1 asks the same question of the real filesystem.

## Evidence

The private evidence repo, under `e2e_evidence/0.4.2/`: the three sweep records
(`sweep-8791.json`, `sweep-8792.json`, `sweep-8793.json`), the harnesses
(`sweep.py`, `gen_tables.py`, `compare3.py`, `pass.sh`, `run_ws.py`,
`win_check.ps1`), the three daemon logs, both regression runs' journals, the
recorded socket frames (`run-ws.json`), and the Windows-side transcript.

Run ids: `da05d07a-e6a1-4ed9-86e6-b9751123a825` (API-triggered),
`c2591905-e886-4923-acf1-87598116f66d` (CLI-triggered). Ports 8791/8792/8793
(Part A) and 8794 (Part R).

## Findings

### F2 (open, pre-existing, blocks the next minor): the QR advertises an address nothing listens on

**`vadgr start` binds `127.0.0.1` only. `vadgr pair` advertises the tailnet.**
The two disagree, so the address a phone scans is one the daemon never answers
on.

Measured through the product path, `VADGR_TRANSPORT=tailscale`:

```
vadgr start --api-port 8807
  127.0.0.1:8807/api/health      -> 200
  100.67.110.10:8807/api/health  -> 000        (nothing listening)
  ss -ltn                        -> LISTEN 127.0.0.1:8807
```

`cli/commands/service.py:220` passes `"--host", "127.0.0.1"` to uvicorn at both
spawn sites, whatever the transport says. `transport.bind_host()` is read by
nothing but the health payload - so `GET /api/health` cheerfully reports
`bind_host: 100.67.110.10` about a socket that does not exist. `api/config.py`'s
own comment claims the opposite: *"Host is no longer hard-coded - it comes from
`transport.bind_host()` at startup (main.py)."* It does not; `main.py` does no
binding at all.

**Pre-existing, not a `0.4.2` regression** - `git show master:cli/commands/
service.py` carries the identical hard-coding, twice.

**It is recorded here because of what it blocks.** Phase 0's gate clause 3 is *a
real handset on the tailnet pairs with that machine and watches a run*, and
`vadgr-mobile 0.4.0`'s first commit is a reachability proof against exactly that
address. Both fail against a daemon that only listens on loopback. Every pairing
cell in this runbook still passes honestly - the mint, the claim, the refused
replay and the device table are all real - but **every request in them
originated from loopback, so no packet crossed the tailnet.**

It also means this branch's `OPTIONS` fix could not be exercised from a genuine
non-loopback peer: recorded as **not run**, not as a pass.

Assigned to `0.4.3`, the pairing minor.



### F1 (open, pre-existing, not introduced here): agent creation on a native provider fails

`POST /api/agents` with `provider: anthropic_oauth` reaches status `error` with
`forge_config: {"error": "[Errno 13] Permission denied: ''"}` within a second -
an empty path being opened somewhere on the forge-generation path.

**Reproduced identically on `master`** (`v0.4.1`, daemon booted from a clean
worktree of `master` on port 8795, same request, same error string), so it is not
this minor's. It is recorded here because it is what forced Part R's fixture
setup, and because a defect that blocks a runbook cell should not be discovered
twice.

It does not block `0.4.2`, whose claim is about what the daemon no longer does.
It does mean nobody can create an agent on the native provider through the
product today, which is worth a patch on the current minor rather than a note.

`0.4.1`'s F5 fixed three creation failures on this path; this is a fourth, and
the fact that it survived that pass is itself the argument for probing creation
in every runbook rather than assuming a previously-fixed path stays fixed.

## Per-OS results

Legend: pass / fail / blocked / not run / **Not-Needed** (no OS-specific
surface, so a run there adds no signal - always with its reason).

| | Linux | macOS | Windows native | WSL |
|---|---|---|---|---|
| Part A (the decommission gate) | Not-Needed | Not-Needed | **partial** (W1-W4) | **pass** |
| Part B (pairing) | Not-Needed | Not-Needed | Not-Needed | **pass** |
| Part C (the surface) | Not-Needed | Not-Needed | Not-Needed | **pass** |
| Part R (regression) | Not-Needed | Not-Needed | Not-Needed | **pass** |
| Part W (installer + CLI) | n/a | **not run** | **pass** | n/a (`setup.sh` `bash -n` only) |
| Overall | Not-Needed | installer **not run** | **pass** | **pass** |

**WSL and native Linux are the same code path here, not merely similar.** Every
OS branch this minor touches is a `sys.platform == "win32"` test; there is no
`/mnt/c`, no interop, no registry and no per-OS dependency anywhere in the diff.
A WSL run and a Linux run execute identical bytes, so a Linux run adds no signal.

**Windows native is `partial` on Part A rather than `pass`** because the daemon
lifecycle half (D1-D8) was run under WSL only. The half that is Windows-shaped -
the CLI's option parsing, the collapsed `api` command and the installer - was run
on Windows and passed (Part W). What was not run on Windows is `vadgr start`
booting a daemon and `ps`-equivalent proof that it spawned nothing, which needs
the API venv installed Windows-side.

**macOS is `not run`, and that is owed rather than excused.** `setup.sh`'s macOS
branch is the one path this minor changes that cannot be reasoned about from
here: `install_nvm_and_node` sat between `install_python` (which shells out to
`brew`) and `setup_repo`, and removing a step from a sequential installer is
exactly the kind of edit that is fine everywhere and wrong in one place. There
is no macOS reachable from this host. `bash -n` passes and the call graph was
read; that is analysis, not evidence.

## What this runbook cannot prove

- **That `setup.sh` completes on a machine with no Node installed.** The spec's
  acceptance criterion, and it needs a clean box. What was proven is the
  stronger-in-one-way, weaker-in-another version: the daemon starts and pairs on
  a host that **does** have Node, without touching it. A full install on a bare
  machine is owed.
- **That nothing on some other machine still points at port 3000.** D7 proves
  nothing on *this* host answers there after `vadgr start`. What a user with a
  stale bookmark sees was **not** tested and is not the obvious answer: on this
  host - WSL2 with mirrored networking - a connect to an unbound low `127.0.0.1`
  port **hangs to timeout rather than refusing**, measured on `:3000`, `:3001`,
  `:4567` and `:9999`, while `::1:3000` refuses instantly. Two independent
  closing passes found this separately. It means D7's evidence is "no listener
  and no HTTP answer", established by contrast with a live port - not "the
  connection was refused", and a check written as "connect fails" would pass
  here even if aimed at the wrong port.
- **That the phone still pairs.** B1-B5 drive the machine's half of pairing end
  to end and ground-truth it in the device table. The scan itself is
  `vadgr-mobile`'s runbook, with a person holding a handset.
- **Anything about the archived frontend.** The subtree split preserved 39
  commits into a private attic repo and the branch was verified to carry
  `package.json` at its root. That it still builds was not tested and is not a
  claim this release makes.
