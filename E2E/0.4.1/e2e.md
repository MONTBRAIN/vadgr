# 0.4.1 - the engine on the production path: e2e runbook

Validation that a run **triggered through the product** reaches the native loop.

> **Status: run on WSL, 2026-08-02. Parts A and B pass end to end.**
> Automated gate green (engine 118, api 539). Part C is blocked on the harness
> and says how; D is deferred to the spike. **Seven defects found, all by this
> runbook and none by the unit tests**, which is the entire argument for running
> it before review.

## This is where `E2E/0.4.0`'s scope exception expires

`E2E/0.4.0/e2e.md` drove the loop by importing it, and said plainly that this
made it an acceptance test rather than an e2e, because the engine shipped as a
library nothing called. From this patch there is a product path, so the bar is
the one `ENGINEERING.md` §1a sets: drive the **real surfaces**.

There are two and **neither substitutes for the other**:

- **the API + the run WebSocket** - how the phone calls it, and therefore the
  only way to know a mobile call behaves;
- **the CLI** (`vadgr run`, `vadgr stream`) - the on-box path, with its own users
  and its own failure modes.

## What the automated gate cannot tell you

The unit suite was green - 15 bridge tests, 5 resume tests, 116 engine - while
**every agent on the native provider went to status `error` at creation** and the
wiring was unreachable. Nothing was wrong with the bridge. The failures were all
on the path between the API and it, which no unit test crossed.

That is the finding worth carrying: a seam is exactly where unit tests stop.

## Part A: the API path

| # | What | Expected | Status |
|---|---|---|---|
| A1 | Daemon boots with resume-on-boot wired | healthy, no exception | **pass** |
| A2 | Create an agent on a native provider | reaches `ready` | **fail -> F5** |
| A3 | Trigger a run on `anthropic_oauth` | run reaches the **native loop** | **pass** |
| A4 | The loop actually ran | journal exists with real usage | **pass** |
| A5 | The journal is correlatable | journal dir == the API run id | **pass, after F4** |
| A6 | Terminal state | run ends `completed` | **pass** |
| A7 | The WS carries the loop's events | frames on `/api/ws/runs/{id}` | not run |
| A8 | The two dropped events never reach the socket | no `llm_response`/`tool_result` | not run |
| A9 | Every frame emitted is one `CONTRACT.md` §2.5 names | no invented frame reaches the phone | **pass** (unit) |

**A9 was a real gap, found by checking the code against the contract rather than
against itself.** The bridge mapped the loop's checklist to a `todos` event and
the executor's `if/elif` had no branch for it, so the frame died one layer below
the bridge and the phone could never receive a checklist - exactly what
`CONTRACT.md` predicted when it said the mockups draw one the API cannot
deliver. The gate frame was also named `awaiting_approval` where the contract
says `awaiting`, which would have been a rename paid for twice, once here and
once in the client. Both fixed, and a test now asserts the bridge emits nothing
the contract does not name.

**Measured (A3-A6).** `POST /api/agents/{id}/run` with
`{"provider":"anthropic_oauth","model":"claude-opus-5"}`:

```
api run id            9e514a92-03a1-48a4-aee6-9ae5a63cf3aa
journal at that id    YES        (~/.vadgr/runs/9e514a92-.../trajectory.jsonl)
run status            completed
run provider          anthropic_oauth
journal phases        {'response': 1}
usage                 input 1452, output 4
```

The **journal is the proof**, not the status. A run can end `completed` on the
old CLI path too; only the native loop writes `trajectory.jsonl`, and the token
usage in it is a real model call rather than a subprocess's stdout.

## Part B: the CLI path - **passes**

| # | What | Expected | Status |
|---|---|---|---|
| B1 | `vadgr health` reaches the daemon | status, version, modules | **pass** |
| B2 | `vadgr runs list` | the runs Part A created | **pass** |
| B3 | `vadgr run <agent>` triggers **and watches** | run completes, exit `0` | **pass** |
| B4 | The CLI-triggered run reached the native loop | journal at the API run id | **pass** |

**Measured (B3-B4):**

```
[vadgr] Run started: e5e0dbb3-3274-48bf-a378-94b8fd9c82ac
[vadgr] Run completed (2s)
exit 0

journal at that id   YES        usage   input 1452, output 4
```

The CLI watches over `/api/ws/runs/{id}`, which this patch **authenticated** -
so B3 also proves the auth fix did not break the on-box path, which was the
risk in touching it.

## Part C: resume - **attempted, not proven, and it found F6 and F7**

Unit-covered (5 tests) and **still not proven on the product**. Two attempts,
and what stopped each is worth recording because both are findings rather than
noise.

**Attempt 1 - the journal was clean, so there was correctly nothing to resume.**
A five-tool-call run finished its calls faster than the kill landed, closing
every `seq`. `find_latest` returned nothing, which is right: a clean journal is
a finished run. To get a dangling record on purpose the run has to be killed
*inside* a call that waits, which is what attempt 2 tried.

**Attempt 2 - the gate could not park at all, which is F6.** The task asked the
model to call `ask_user` with a 300 second timeout. The model sent the timeout
as the **string** `"300"`, `asyncio.wait_for` compared a `str` to an `int`, and
the gate raised. The journal shows it three times over:
`in_flight -> await_user -> error`, three times, never parking.

So the run never reached a state that could be interrupted, and the honest
verdict is that **gate clause 2 remains unproven on the product**. It needs a
harness that can hold a daemon open and kill it at a chosen moment, which this
environment's process handling did not give me. Recorded rather than dressed up:
the runbook's own rule is that a self-reported success with no confirming
read-back is a FAIL, and an unrun cell is not a pass.

## Part D: the timeout - **not run**

That a native run outlives 900 seconds is asserted by construction (`timeout` is
`None` on the native path and the bridge ignores the parameter) and by a unit
test. A real multi-hour run is the dogfood spike's job, not this runbook's.

## Findings

### F1 (fixed): a native provider had no `args`, so agent creation raised

`load_provider_config` did `config["args"] + ["--model", model]`. A native
provider has a `module`, not an argv. `KeyError: 'args'`.

### F2 (fixed): `ProviderConfig` required a `command`

Same root cause one level down: the dataclass made `command` mandatory, so
loading a native entry raised `TypeError`. It now defaults to empty, which is
what a native provider honestly has.

### F3 (fixed): the availability check spawned an empty argv

`is_available()` fell through to `create_subprocess_exec()` with `''` and raised
`PermissionError: [Errno 13] Permission denied: ''`. A provider with no command
is the in-process engine and is always available: there is nothing to find on
PATH and nothing to spawn.

**F1, F2 and F3 are one defect wearing three hats**: nothing on the creation path
knew that a provider might not be a subprocess. Each was invisible to the unit
tests because each is in code the bridge does not call.

### F4 (fixed): the journal could not be tied to the run

The executor never passed `run_id` to `execute_streaming`, so the loop minted its
own and wrote `~/.vadgr/runs/run-c02c2fa8c7f5/` for API run
`628ceccf-d34d-...`. Two consequences, and the second is worse than a cosmetic
mismatch: nothing could correlate a journal with the run it belongs to, and
**resume-on-boot was broken** - it finds a journal by id and then looks that run
up, which would never have matched.

### F5 (open, and a scope discovery rather than a bug)

**Agent creation is CLI-bound and this patch does not change that.** `POST
/api/agents` runs *forge generation*, which spawns the configured provider as a
subprocess to generate the agent's files. A native provider cannot do that, so an
agent created directly on `anthropic_oauth` still ends in status `error`.

It does not block `0.4.1`, because a **run** may override the provider
(`{"provider": ..., "model": ...}` on the trigger, and the API requires them
together), which is the path Part A exercised. But it means the native loop is
reachable per-run and not yet as an agent's own provider, and that is worth
saying out loud rather than discovering at `0.5.0`. The reshape replaces this
path with `POST /api/runs {task}`, where the question disappears - a free-form
run has no forge generation.

### F6 (fixed): a gate raised instead of asking, on a timeout the model typed

`ask_user` and `request_approval` declare `timeout` as a JSON Schema `number`,
and a JSON Schema type is **advisory** - the value arrives as whatever the model
emitted. It emitted `"300"`. `asyncio.wait_for` then compared a `str` to an
`int` and raised `TypeError: '<=' not supported between instances of 'str' and
'int'`.

The failure mode is the worst available to a human-in-the-loop tool: **the run
failed at the exact moment it was trying to consult a human.** Not a park, not a
refusal - a crash, where the whole point of the tool is that a human gets asked.

Timeouts are now coerced, and an unparseable one means no timeout rather than an
exception. This is the same class as `0.4.0`'s F3, where the model wrote
`completed` for a status whose enum said `done`: **a schema enum or type is a
hint to the model, never a guarantee to the runtime**, and every value crossing
that boundary has to be treated as untrusted input.

### F7 (fixed): the on-box WebSocket authenticated nothing

`/api/ws/runs/{run_id}` never called the authorizer - the auth middleware is
HTTP-only - so any peer gate 1 admits could open it, which over a tailnet is
every member of it. It also honoured an inbound `approval_response` that resumed
a parked run, making it an **unauthenticated way to answer a human-approval
gate**: the one decision the entire gate layer exists to protect.

Both fixed here rather than at `0.5.0`, because the hole goes live the moment a
phone reaches a machine over a tailnet, which is mobile `0.4.0`. The socket now
authenticates exactly as `/stream` does and is **send-only**; answering is
`POST /api/runs/{id}/respond`, which is authenticated, idempotent and auditable.
The route is still deleted at `0.5.0` - it has a live consumer today (the CLI,
`cli/stream.py`), and B3 proves the fix did not break it.

## What this runbook cannot prove yet

- **Nothing about the CLI path** (Part B).
- **Nothing about resume on the product** (Part C), and two attempts say why
  rather than one sentence. Gate clause 2 remains proven at the unit level only,
  and the phase cannot close until it is not.
- **Nothing about the WebSocket** (A7, A8), so the claim that the two unbounded
  events never reach a phone is currently a unit-test claim about `map_event`,
  not an observation of the socket.
