# 0.4.3 - a code a person can type, at an address that answers: e2e runbook

Two things are now demonstrably true that were not: the pairing secret is eight
characters someone can read off a terminal and thumb into a phone, with a
five-attempt cap that kills the code rather than the attempt - and the daemon
**listens on the address the pairing QR advertises**, so that code is for a
socket that exists.

> **Status: run on Linux (WSL2), 2026-08-05.** Automated gate green (engine 122,
> api 596, cli 201). Parts N, C, S and R all pass; **69 cells, 69 run, 0 open**.
> **2 findings**, both fixed on the branch and both re-run live. Nothing is
> marked pass that was not executed and read back.

## The approach

The gate for this minor is not model-shaped - it is about what a socket does and
what an error code says - so Parts N, C and S are a **recorded sweep** driven
through the product's own surfaces (`vadgr start`, `vadgr pair`, `vadgr stop`,
`curl`, `ss`), never an import. Part R, the regression, is driven the way the
engineering standard requires: a real run whose verdict comes from
`trajectory.jsonl`, not from the run's status.

Both surfaces are exercised and neither substitutes for the other:

- **the API** - how the phone claims a code, and the only proof a mobile call
  behaves;
- **the CLI** - the on-box path, which is where the code is printed and where
  the daemon is started.

The CLI is driven through the **shim entry point** (`PYTHONPATH=$REPO
cli/.venv/bin/python -m cli`), the same form the installed `vadgr` binary uses,
pointed at the branch under test. Not `python -m cli.main`, which exits `0`
having printed nothing.

## Prerequisites

```bash
export FORGE_HOME=$SCRATCH/forge8891          # a throwaway home, so pid/port/log files are this run's
export AGENT_FORGE_PORT=8891
export AGENT_FORGE_DATABASE_PATH=$SCRATCH/db8891.db
export VADGR_TRANSPORT=tailscale              # pairing 503s on loopback by design
vadgr start
```

Tailscale must be up **inside WSL** (the Linux `tailscaled` socket), not only on
the Windows side, or the transport reports unavailable and `vadgr pair` refuses
to hand out a QR the phone cannot reach. This host's tailnet address during the
run was `100.67.110.10`, MagicDNS `santiago-casa-1.tail323b9e.ts.net`.

## Automated gate (necessary, never sufficient)

- `PYTHONPATH=. python3 -m pytest engine/tests/ -q` -> **122 passed**
- `python3 -m pytest api/tests/ -q` -> **596 passed**
- `python3 -m pytest cli/tests/ -q` -> **201 passed**

Counts moved: `api` 555 -> 596 (the code's format and normalisation, the cap,
the burn, supersede, the claim mapping in both directions, and the launcher's
address arithmetic; the two pairing-token tests the code replaces are gone),
`cli` 192 -> 201 (the bind argv, the loopback fallback, and the request-body
tests behind F2).

**What the gate cannot tell you, and this is the whole point of Part N.** Every
one of those tests reads a fake. Not one of them opens a socket the daemon is
serving on. "The daemon listens where pairing advertises" is a claim about a
running process's socket table, and only a request arriving over the advertised
address can make it - which is exactly why a unit test asserting the argv would
have been decoration. See N4.

## Coverage

Axes, multiplied, with the count written down.

| Part | Axes | Cells | Run | Open |
|---|---|---|---|---|
| N - the bind | 6 observations of a live daemon + 2 negative-control runs (master, branch) + 5 tailscale-down | 13 | 13 | 0 |
| C - the pairing code | {mint, claim} x {verbatim, normalised, confusable, malformed, replay, unknown, expired, capped, burned, superseded, printed-then-typed, shape} = 17, + 2 loopback-transport | 19 | 19 | 0 |
| S - surface | 14 shipped endpoint responses + 10 not-yet-built probes + 7 CLI commands | 31 | 31 | 0 |
| R - regression | 2 trigger paths (API, CLI) x (journal, sockets, outputs) | 6 | 6 | 0 |
| | | **69** | **69** | **0** |

Nothing is deferred out of this runbook. The one check that belongs elsewhere is
named: **a real handset scanning the QR and typing the code** is `vadgr-mobile
0.4.0`'s runbook, because there is no phone half in this repo. What is proven
here is the machine half of it - that the address in the QR answers, and that a
code taken from the terminal claims.

## Part N: the daemon listens where pairing advertises - **passes**

### N4 first, because it is what makes the rest mean anything

The defect passed two of the three passes that closed `0.4.2`: they spoke to
loopback, and a loopback-bound daemon answers everything asked of loopback. So
the check has to be shown **failing** against a daemon that has the defect
before its passing is worth reading.

Same harness, same host, same tailnet, run against `master` and then against the
branch.

**Against `master` (`v0.4.2`) - the check fails, as it must:**

```
=== bindcheck [master (v0.4.2, before the fix)] port=8841 tailnet=100.67.110.10 ===
[vadgr] Starting API server (port 8841)...
[vadgr] vadgr is running!
start exit=0
--- N2: ss -ltn, the socket itself
LISTEN 0      2048       127.0.0.1:8841      0.0.0.0:*
--- N1: GET http://100.67.110.10:8841/api/health over the ADVERTISED address
advertised-address status=000
body:
--- loopback control (must always answer)
loopback status=200
--- N3: health.bind_host vs what ss shows
health bind_host=100.67.110.10
ss listen addr=127.0.0.1
--- N6: the address vadgr pair advertises
  Address:      santiago-casa-1.tail323b9e.ts.net:8841
  Pairing token: -2QMEUX6DI49iunofN-CzREph_OTh27b
=== verdict [master (v0.4.2, before the fix)] ===
BINDCHECK FAIL (advertised=000 ss=127.0.0.1 health=100.67.110.10 expected=100.67.110.10)
exit 1
```

Read the third and fourth lines from the bottom together: **`/api/health`
reported a `bind_host` of `100.67.110.10` about a socket bound to `127.0.0.1`.**
The field was not merely useless, it was wrong, and it was wrong in the
direction that reassures.

**Against the branch - the same check passes:**

```
=== bindcheck [branch feat/0.4.3-pairing-code] port=8842 tailnet=100.67.110.10 ===
[vadgr] Starting API server (100.67.110.10, 127.0.0.1 on port 8842)...
[vadgr] vadgr is running!
start exit=0
--- N2: ss -ltn, the socket itself
LISTEN 0      2048   100.67.110.10:8842      0.0.0.0:*
LISTEN 0      2048       127.0.0.1:8842      0.0.0.0:*
--- N1: GET http://100.67.110.10:8842/api/health over the ADVERTISED address
advertised-address status=200
body: {"status":"healthy",...,"transport":{"name":"tailscale","available":true,
       "advertise_host":"santiago-casa-1.tail323b9e.ts.net","bind_host":"100.67.110.10"}}
--- loopback control (must always answer)
loopback status=200
--- N3: health.bind_host vs what ss shows
health bind_host=100.67.110.10
ss listen addr=100.67.110.10,127.0.0.1
--- N6: the address vadgr pair advertises
  Address:      santiago-casa-1.tail323b9e.ts.net:8842
  Pairing code: VD8K-R2W8
=== verdict [branch feat/0.4.3-pairing-code] ===
BINDCHECK PASS
exit 0
```

### The recorded observations

#### The bind - does anything answer where pairing points?

| # | check | expected | as measured | |
|---|---|---|---|---|
| N1 | the advertised tailnet address answers | `200` | `200` | **pass** |
| N2 | the socket table carries the tailnet address | `True` | `True` | **pass** |
| N2b | loopback is bound too, so gate 0 keeps the on-box CLI tokenless | `True` | `True` | **pass** |
| N2c | nothing is bound to every interface | `False` | `False` | **pass** |
| N3 | health's bind_host is an address that is actually bound | `True` | `True` | **pass** |
| N6 | the MagicDNS name the QR carries answers | `200` | `200` | **pass** |

Sockets open on the daemon's port: `['100.67.110.10', '127.0.0.1']`. The tailnet address is `100.67.110.10`, the name in the QR is `santiago-casa-1.tail323b9e.ts.net`, and `GET /api/health` reports `bind_host = 100.67.110.10`.

#### The two boots the main sweep cannot make

| # | check | expected | as measured | |
|---|---|---|---|---|
| A1 | cell 3: loopback transport binds loopback only | `['127.0.0.1']` | `['127.0.0.1']` | **pass** |
| A2 | cell 3: loopback transport refuses to mint a code | `(503, 'TRANSPORT_UNREACHABLE')` | `(503, 'TRANSPORT_UNREACHABLE')` | **pass** |
| A3 | N5: the daemon still starts with tailscaled unreachable | `0` | `0` | **pass** |
| A4 | N5: start says so on stdout | `True` | `True` | **pass** |
| A5 | N5: it binds loopback only | `['127.0.0.1']` | `['127.0.0.1']` | **pass** |
| A6 | N5: health reports the transport unavailable | `False` | `False` | **pass** |
| A7 | N5: no code is minted for an address nobody can reach | `(503, 'TRANSPORT_UNREACHABLE')` | `(503, 'TRANSPORT_UNREACHABLE')` | **pass** |

`cell 3: the loopback transport refuses to mint` - `vadgr start` exit `0`, printed: `[vadgr] Starting API server (127.0.0.1 on port 8881)... / [vadgr] vadgr is running! / [vadgr] API: http://localhost:8881 / [vadgr] Run 'vadgr pair' to pair your phone, 'vadgr stop' to stop, 'vadgr logs' for the log.`

`N5: tailscale configured but tailscaled unreachable` - `vadgr start` exit `0`, printed: `[vadgr] Tailscale transport unavailable: tailscaled not running or logged out. Binding 127.0.0.1 only; pairing will refuse. / [vadgr] Starting API server (127.0.0.1 on port 8882)... / [vadgr] vadgr is running! / [vadgr]  ...`


**Why two sockets and not one.** The transport's address is what the QR carries,
so a phone must reach it. Loopback is what gate 0 recognises, so the on-box CLI
reaches the daemon without a device token. Binding only the first was measured
during this work and it costs the second: every gated CLI command answers
`401 MISSING_TOKEN` on the machine's own console. Binding `0.0.0.0` would cover
both and is refused outright - this process runs with the owner's credentials,
and "reachable by authenticated tailnet peers" and "reachable by whoever is on
the same cafe wifi" are not two settings of one knob.

## Part C: the pairing code - **passes**

`0.4.1` shipped a ~32-character `secrets.token_urlsafe(24)` in a field a person
was expected to retype, and its `429 RATE_LIMITED` was written in the reference
and implemented nowhere. Both are now what the reference says.

#### The pairing code, cell by cell

| # | cell | expected | as measured | |
|---|---|---|---|---|
| 1 | pair returns a grouped Crockford code | `True` | `True` | **pass** |
| 1b | the pair body has exactly the four shipped fields | `True` | `True` | **pass** |
| 2 | pair twice in quick succession - the mint-side 429 is target, not shipped | `[200, 200]` | `[200, 200]` | **pass** |
| 4 | claim, code verbatim | `200` | `200` | **pass** |
| 4b | ground truth: the claimed device row exists | `True` | `True` | **pass** |
| 5 | claim, lowercase and ungrouped | `200` | `200` | **pass** |
| 6 | claim with the confusables typed: 6CV0-PX5A typed as 6CVO-PX5A, after 1 mint(s) | `200` | `200` | **pass** |
| 7 | claim, malformed - seven characters, then a U | `[(401, 'PAIRING_CODE_INVALID'), (401, 'PAIRING_CODE_INVALID')]` | `[(401, 'PAIRING_CODE_INVALID'), (401, 'PAIRING_CODE_INVALID')]` | **pass** |
| 8 | claim, reuse after success | `(401, 'PAIRING_CODE_INVALID')` | `(401, 'PAIRING_CODE_INVALID')` | **pass** |
| 9 | claim, a never-minted well-formed code | `(401, 'PAIRING_CODE_INVALID')` | `(401, 'PAIRING_CODE_INVALID')` | **pass** |
| 10 | claim, expired - the RIGHT code 297s after minting | `(410, 'PAIRING_CODE_EXPIRED')` | `(410, 'PAIRING_CODE_EXPIRED')` | **pass** |
| 11 | the cap, attempts 1-4 wrong | `[(401, 'PAIRING_CODE_INVALID'), (401, 'PAIRING_CODE_INVALID'), (401, 'PAIRING_CODE_INVALID ...` | `[(401, 'PAIRING_CODE_INVALID'), (401, 'PAIRING_CODE_INVALID'), (401, 'PAIRING_CODE_INVALID ...` | **pass** |
| 12 | the cap, attempt 5 wrong | `(429, 'RATE_LIMITED')` | `(429, 'RATE_LIMITED')` | **pass** |
| 12b | the 429 carries empty details - the recovery is a new code, not waiting | `{}` | `{}` | **pass** |
| 13 | the burn: attempt 6 wrong, then the TRUE code, which paired nothing | `[(401, 'PAIRING_CODE_INVALID'), (401, 'PAIRING_CODE_INVALID')]` | `[(401, 'PAIRING_CODE_INVALID'), (401, 'PAIRING_CODE_INVALID')]` | **pass** |
| 14 | supersede - mint A, mint B, claim A then B | `[(401, 'PAIRING_CODE_INVALID'), (200, '')]` | `[(401, 'PAIRING_CODE_INVALID'), (200, '')]` | **pass** |
| 15 | `vadgr pair` printed 'Q0SP-GJVV' plus a 22-row QR, and that code was then typed back to claim | `(0, True, True, 200)` | `(0, True, True, 200)` | **pass** |

#### The seven-attempt trace, as the wire carried it

| attempt | claimed | status | code |
|---|---|---|---|
| 1 | `AAAA-AAAA` | `401` | `PAIRING_CODE_INVALID` |
| 2 | `BBBB-BBBB` | `401` | `PAIRING_CODE_INVALID` |
| 3 | `CCCC-CCCC` | `401` | `PAIRING_CODE_INVALID` |
| 4 | `DDDD-DDDD` | `401` | `PAIRING_CODE_INVALID` |
| 5 | `EEEE-EEEE` | `429` | `RATE_LIMITED` |
| 6 | `FFFF-FFFF` | `401` | `PAIRING_CODE_INVALID` |
| 7 | `0C0D-Z8BG (the true code)` | `401` | `PAIRING_CODE_INVALID` |


**Cell 13 is the one that proves the cap rather than asserting it.** The failure
arrives as response data: the code that was correct all along comes back `401`
after the fifth wrong guess burned it. Nothing here reads a counter or a log
line.

**Cell 6 is the one that could not have been written from the spec alone.** The
sweep mints until a code contains a `0` or a `1`, then types the confusable in
its place - this run drew `6CV0-PX5A` on the first mint and claimed it as
`6CVO-PX5A`.

## Part S: surface coverage - every published endpoint, with what it returned

**Generated, not written.** One sweep drives every surface and records the
request, the status, the error code and the body; the tables below are emitted
from that record by `gen_tables.py`, so no row was typed. Device ids and the
device token are substituted; nothing else is.

#### Shipped endpoints

| endpoint | what was asked | status | code | response, as returned |
|---|---|---|---|---|
| `GET /api/health` | N3: health's own bind_host | `200` | - | `{"status":"healthy","modules":{"forge":true,"computer_use":true},"platform":"wsl2","version":"0.4.3","transpor ...` |
| `POST /api/auth/pair` | cell 1: pair on tailscale transport | `200` | - | `{"host":"santiago-casa-1.tail323b9e.ts.net","port":8891,"pairing_token":"DZJ2-9NM7","machine_name":"Santiago-C ...` |
| `POST /api/auth/claim` | claim 'AET2-10TS' | `200` | - | `{"token":"{device_token}","device_id":"{device}"}` |
| `GET /api/devices` | ground truth: the device rows | `200` | - | `[{"id":"{device}","machine_name":"cell-4-phone","paired_at":"2026-08-05T16:19:26.676572Z","last_seen":"2026-08 ...` |
| `DELETE /api/devices/{device}` | clean up cell 4's device | `200` | - | `{"status":"revoked","device_id":"{device}"}` |
| `POST /api/auth/claim` | claim '7QK4-M2X' | `401` | `PAIRING_CODE_INVALID` | `{"error":{"code":"PAIRING_CODE_INVALID","message":"That pairing code is wrong or has already been used.","deta ...` |
| `POST /api/auth/claim` | claim 'EEEE-EEEE' | `429` | `RATE_LIMITED` | `{"error":{"code":"RATE_LIMITED","message":"Too many failed attempts. That pairing code is no longer valid; gen ...` |
| `GET /api/providers` | the provider catalogue | `200` | - | `[{"id":"anthropic_oauth","name":"Anthropic (OAuth, subscription)","available":true,"models":[{"id":"claude-opu ...` |
| `DELETE /api/devices/no-such-device` | negative: unknown device | `404` | `DEVICE_NOT_FOUND` | `{"error":{"code":"DEVICE_NOT_FOUND","message":"Device 'no-such-device' not found.","details":{}}}` |
| `GET /api/runs` | run list | `200` | - | `[]` |
| `GET /api/runs/no-such-run` | negative: unknown run | `404` | `RUN_NOT_FOUND` | `{"error":{"code":"RUN_NOT_FOUND","message":"Run with id 'no-such-run' not found","details":{}}}` |
| `GET /api/agents` | agent list | `200` | - | `[]` |
| `GET /api/settings/computer-use` | computer-use settings | `200` | - | `{"enabled":true,"venv_ready":true,"daemon":"running","platform":"wsl2"}` |
| `POST /api/auth/claim` | claim 'BD43-EC1B' | `410` | `PAIRING_CODE_EXPIRED` | `{"error":{"code":"PAIRING_CODE_EXPIRED","message":"That pairing code has expired. Generate a new one on the ma ...` |

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

#### The CLI

| command | exit | seconds | output, as printed |
|---|---|---|---|
| `vadgr pair` | `0` | 0.1 | `[terminal QR, 22 rows] / Machine: Santiago-Casa / Address: santiago-casa-1.tail323b9e.ts.net:8891 / Pairing code: Q0SP-GJVV / [vad ...` |
| `vadgr health` | `0` | 0.1 | `Status: healthy / Version: 0.4.3 / Platform: wsl2 / Modules:` |
| `vadgr status` | `0` | 0.7 | `Service PID Status / api 1515946 running / daemon - running` |
| `vadgr runs list` | `0` | 0.1 | `[vadgr] No runs found.` |
| `vadgr providers` | `0` | 0.7 | `Anthropic (OAuth, subscription) (anthropic_oauth) -- available / - Claude Opus 5 (claude-opus-5) / - Claude Sonnet 5 (claude-sonne ...` |
| `vadgr agents list` | `0` | 0.1 | `[vadgr] No agents found. Create one with: vadgr agents create` |
| `vadgr health` | `3` | 1.6 | `Error: API is not running at http://127.0.0.1:9999. Start it with: vadgr start` |


## Part R: regression - the native loop still runs - **passes**

`0.4.1`'s gate re-run on this branch. The diff does not touch the loop, but it
changes how the daemon is launched and what the CLI puts on the wire, so both
trigger paths are where collateral damage would show.

| # | What | Expected | Status |
|---|---|---|---|
| R1 | Trigger through the API | run reaches the native loop | **pass** |
| R2 | The loop actually ran | journal at the API run id, real usage | **pass** |
| R3 | Both sockets carry the run | frames on `/api/ws/runs/{id}` and `/api/runs/{id}/stream` | **pass** |
| R4 | Trigger through the CLI | `vadgr run <agent>` completes, exit `0` | **pass** |
| R5 | The CLI-triggered run reached the loop too | journal at that run id | **pass** |
| R6 | The results link resolves | `GET` the printed URL -> `200` | **pass** |

**Fixture setup, stated where it happens.** Agent creation on a native provider
leaves the agent in `error` on this branch **and identically on `master`** - the
same pre-existing defect `E2E/0.4.2` recorded - so no agent can be brought to
`ready` through the product path. The agent below was created through
`POST /api/agents` as normal and then had its `status` set to `ready` directly
in the sweep's throwaway database. Nothing else was seeded: these are real runs,
with real model calls, in a real journal.

**Measured (R1-R3).**

```
api run id            f81d941b-349f-4cd7-8f2f-b0014ac1f323
journal at that id    YES   (~/.vadgr/runs/f81d941b-.../trajectory.jsonl)
journal phases        {'response': 2, 'in_flight': 1, 'done': 1}
tool the model chose  control__report_progress
usage                 turn 0: input 1495 / output 68      turn 1: input 1571 / output 27
run status            completed
outputs               {"result": "Progress reported with the note \"pairing code check\". ..."}

second run, watched:  ebce7968-b3ed-459e-b6b8-359eb60f1425
raw    /api/ws/runs/{id}      run_started 1  agent_started 1  agent_log 2  agent_completed 1  run_completed 1  = 6
mobile /api/runs/{id}/stream  started 1  tool_call 1  output 3  completed 1                                    = 6
```

**Measured (R4-R6).**

```
$ vadgr run e2e-043-conformance
[vadgr] Run started: ffa5104b-3cb0-4e6a-97dd-099d15ecb646
[vadgr] Run completed (4s)

  See results: http://127.0.0.1:8894/api/runs/ffa5104b-3cb0-4e6a-97dd-099d15ecb646
exit 0

journal at that id    YES   phases {'response': 2, 'in_flight': 1, 'done': 1}
usage                 turn 0: input 1495 / output 68      turn 1: input 1571 / output 27
GET the printed link  -> 200
```

**The journal is the proof, not the status.** A run ends `completed` on the
legacy path too; only the native loop writes `trajectory.jsonl`, and the token
counts in it are a real model call rather than a subprocess's stdout.

## Repeatability - **three independent passes**

**Not yet run.** This runbook records one honest pass. The closing sweep - three
agents, concurrently, each with its own port, database and daemon, compared
structurally on status, error code, exit code and frame counts - is owed before
`0.4.3` is tagged. The harness already takes the port as its argument and each
pass stops only its own daemon by pid, which is what makes that safe.

## Evidence

The private evidence repo, under `e2e_evidence/vadgr-0.4.3/`: the sweep records
(`sweep-8891.json`, `alt.json`), the harnesses (`bindcheck.sh`, `sweep.py`,
`alt_transports.py`, `run_ws.py`, `gen_tables.py`, `pass.sh`), both N4 runs
(`N4-before-master.txt`, `N4-after-branch.txt`), the daemon logs, and the three
run journals by run id. The failing sweep from before F2 was fixed is kept
beside the passing one.

## Findings

### F1 (fixed): the daemon bound loopback while the QR advertised the tailnet

`cli/commands/service.py` passed a literal `--host 127.0.0.1` to uvicorn at its
one spawn site, while `POST /api/auth/pair` advertised `transport.advertise_host()`
and `GET /api/health` reported `transport.bind_host()`. Nothing read the
transport on the way to the socket, so the two could not agree and did not: a
phone scanning the QR dialled an address with nothing behind it, and health
reported a `bind_host` that had never been bound.

Why the tests did not catch it: no unit test starts a process. The suites fake
the transport and assert on what the fakes were asked, and a fake is never
bound to anything. `E2E/0.4.2`'s closing passes missed it because two of the
three spoke only to loopback.

Fixed by resolving the address from `create_transport()` in the parent - so
`vadgr start` knows before it writes a pid file and reports success - and
opening both that address and loopback. `TailscaleTransport.bind_host()` raises
when tailscaled is down or logged out, and that is caught: the daemon falls back
to loopback alone, **says so on stdout**, and pairing then refuses with
`503 TRANSPORT_UNREACHABLE` rather than minting a code for an address nobody can
reach (A3-A7).

The tests that now fail without it: `TestStartBindsWhereTheTransportSays` in
`cli/tests/test_service.py` (six), and `api/tests/test_serve.py`. They are argv
and socket-arithmetic tests and they are **not** the proof - N4 is.

### F2 (fixed): `vadgr pair` lost one code in twenty, and blamed the daemon

Found by cell 15, which failed on the first recorded sweep: `vadgr pair` exited
`3` with `Error: API is not running at http://127.0.0.1:8851` against a daemon
that was running and answering every other command in the same sweep.

Root cause at `cli/client.py:29`. The client sent `b"{}"` as the body of every
non-`GET` request, including to routes that declare no body parameter -
`POST /api/auth/pair` among them. The app never reads those bytes, so the server
cannot reuse the connection and closes it abruptly; on WSL2 loopback that close
races the client's read and surfaces as `ConnectionResetError`, which
`_request`'s `except OSError` reports as "API is not running". The daemon had
already answered `200` and minted a code - **the access log shows all 40 of 40
requests served `200` while 5 of them never reached the client** - so the
failure was silent on the server and misleading on the client.

Measured, 120 fresh CLI invocations per row against one daemon:

| what was sent | failures / 120 |
|---|---|
| `GET /api/health` | 0 |
| `POST /api/auth/pair`, no body | 0 |
| `POST /api/auth/pair`, body `{}` | 5 |
| `vadgr pair` before the fix | 5-9 |
| `vadgr pair` after the fix | **0** |

Pre-existing: `master`'s client and `master`'s spawn reproduce it identically,
so `0.4.3` did not introduce it. It is fixed here because it lands on this
minor's headline surface - the command that shows the code - and because a
retry would have been the wrong fix: the server has already acted, so retrying
a claim would burn a one-time code and lose the device token.

Fixed by sending no body when there is none (`cli/client.py`), which is also
what the routes actually expect. Test that fails without it:
`test_a_bodyless_post_sends_no_body_at_all` in `cli/tests/test_client.py`.

## Per-OS results

Legend: pass / fail / blocked / not run / **Not-Needed** (no OS-specific
surface, so a run there adds no signal - always with its reason).

| | Linux | macOS | Windows native | WSL |
|---|---|---|---|---|
| Part N - the bind | not run | not run | not run | **pass** |
| Part C - the pairing code | Not-Needed | Not-Needed | Not-Needed | **pass** |
| Part S - surface | not run | not run | not run | **pass** |
| Part R - regression | not run | not run | not run | **pass** |
| Overall | not run | not run | not run | **pass** |

**Part C is `Not-Needed` elsewhere and the reason is specific**: the code, its
normalisation, the store and the claim mapping are pure Python over strings and
an in-memory dataclass - no socket, pipe, path, registry or process branching,
and no per-OS dependency - so another OS cannot answer differently, and the
API suite covers them identically on any of the four.

**Parts N, S and R are owed, not excused.** Part N binds ports and spawns a
process, which is exactly the surface that differs per OS, and this run only
covers WSL2. Two per-OS risks are known and handled in code rather than
observed:

- `SO_REUSEADDR` means "rebind through `TIME_WAIT`" on POSIX and "let another
  process take this address" on Windows. `api/serve.py` sets it only off
  Windows, with a test asserting the branch - but the *behaviour* on a native
  Windows host has not been watched.
- macOS and Windows resolve the tailnet address through the same LocalAPI the
  transport already abstracts, and Windows uses the named pipe rather than the
  unix socket. That path is `0.3.0`'s and unchanged here, but the bind that
  consumes it is new.

## What this runbook cannot prove

- **That a phone pairs.** No handset is involved. What is proven is that the
  address in the QR answers and that a code read off the terminal claims
  successfully. The scan, the keyboard and the phone's own view of the
  handshake are `vadgr-mobile 0.4.0`'s runbook.
- **That 40 bits is enough.** That is a ruling with its reasoning recorded
  elsewhere; this runbook only shows the cap it depends on is real.
- **Stability.** One pass. The three concurrent passes that close a runbook have
  not been run, and until they are, ordering effects and cross-run interference
  are unexcluded.
- **Any OS but WSL2**, for anything that binds a port or starts a process. See
  the table above.
- **That `POST /api/auth/pair` resists a mint flood.** Its `429` is a target,
  not shipped, and cell 2 records the current answer (`200`, twice) so the gap
  is documented rather than discovered.
